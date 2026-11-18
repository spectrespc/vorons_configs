#!/usr/bin/env python3
"""Offline Klipper config checker.

Emulates Klipper's own config reader (klippy/configfile.py):

* every line is cut at the first ``#`` before parsing;
* ``RawConfigParser(strict=False, inline_comment_prefixes=(';', '#'))``
  is used, so same-named sections silently merge and a repeated option
  is last-wins;
* ``[include ...]`` paths are resolved relative to the *including*
  file's directory, wildcards are sorted and a direct (non-glob)
  missing include is an error;
* recursive includes are detected with a visited set.

Usage:
  check_config.py --config-dir DIR   validate a deployed config tree
  check_config.py --merged DIR       dump the merged config to stdout
  check_config.py --machine DIR      validate one printers/<id> profile
  check_config.py --stale-check      verify committed profile.cfg files

Exit status: 1 if at least one error was found, otherwise 0.

Diagnostics:
  ERROR    missing/recursive include, parse error, two probe objects
           ([probe] + [probe_eddy_current ...]), physical [stepper_z]
           endstop without position_endstop, active stealthchop_threshold
           >= 1000 (the fleet invariant is SpreadCycle)
  WARNING  duplicate section name, repeated option (last-wins), TMC section
           without an explicit stealthchop_threshold
  NOTICE   module .cfg under std.configs/ or std.macros/ that is not
           included by any profile and is not a known fleet alternative
"""

from __future__ import annotations

import argparse
import configparser
import glob
import io
import math
import os
import re
import sys

SECTCRE = configparser.RawConfigParser.SECTCRE
OPTCRE = configparser.RawConfigParser.OPTCRE

# Modules that are deliberately kept in the repository as fleet alternatives
# and are therefore not expected to be included by the reference profile.
ALT_MODULES = {
    "std.configs/display/mini12864-swspi.cfg",
    "std.configs/extruder/heads/BMG.8T.cfg",
    "std.configs/extruder/tc/104-gt2.cfg",
    # The physical probe module is the alternative of the eddy modules: the
    # renderer includes exactly one of them, so an eddy-only tree legitimately
    # leaves probe.cfg out.
    "std.configs/probe.cfg",
    "std.configs/sht36-v3.eddy.cfg",
    "std.configs/sht36-v3.eddy-f.cfg",
    "std.macros/homing.cfg",
    "std.macros/actions_filament.cfg",
    "std.macros/filament_load_unload.cfg",
}

# Entire catalogs are fleet alternatives: every board, mechanic, motor module
# and geometry variant is a valid target for some machine.conf combination and
# is therefore never reported as an orphan.
CATALOG_PREFIXES = (
    "std.configs/boards/",
    "std.configs/mechanics/",
    "std.configs/motors/",
    "std.configs/geometry/",
)

# Layers that intentionally reopen sections to override earlier values. Their
# duplicate-section and repeated-option diagnostics are expected noise.
OVERRIDE_FILES = (
    "anchors.cfg",
    "machine-extras.cfg",
    "mini12864-swspi.cfg",
    # The seed printer.cfg is the machine-local layer on top of the generated
    # profile: it carries per-machine sections such as [stepper_z]
    # position_endstop, which must live outside the includes for SAVE_CONFIG.
    "printer.cfg",
)

# Options whose value names an MCU (or a board_pins alias that maps to one).
# They are not pin references, so they are resolved as plain names.
MCU_NAME_OPTIONS = ("mcu", "sensor_mcu", "i2c_mcu", "spi_mcu")

# A Klipper pin reference is "chip:PIN" and may carry !, ^ or ~ modifiers.
# The chip part can be an MCU name or a board_pins alias; in this repository an
# alias is always named after the MCU it belongs to, so a single check on the
# original option text covers both. "<GND>"-style aliases contain no colon.
PIN_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_-]*):([A-Za-z][A-Za-z0-9_]*)"
)

# Klipper virtual pins look like a chip reference but are provided by the
# probe/TMC module itself, not by an MCU.
VIRTUAL_PIN_SUFFIXES = ("virtual_endstop", "z_virtual_endstop")

# MCU names that are valid even without an explicit reference: the implicit
# motherboard and the host micro-controller (its GPIO and host sensors may be
# unused on a particular machine).
IMPLICIT_MCUS = ("mcu", "host")


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def _norm(path: str) -> str:
    return path.replace(os.sep, "/")


def _render_profile_module():
    """Import the sibling renderer (single source of the machine.conf rules)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        import render_profile  # noqa: PLC0415 - same-directory helper
    except ImportError:
        # A deployed copy of this checker may live without the renderer next to
        # it; the voltage check is then skipped instead of crashing.
        return None
    return render_profile


def is_catalog_module(path: str) -> bool:
    norm = _norm(os.path.abspath(path))
    return any("/%s" % prefix in norm + "/" for prefix in CATALOG_PREFIXES)


def is_merge_layer(path: str) -> bool:
    """True when a file is expected to reopen/override earlier sections."""
    norm = _norm(os.path.abspath(path))
    if is_catalog_module(path):
        return True
    if norm.endswith("/std.configs/probe.cfg"):
        return True
    if "/std.configs/extruder/" in norm:
        # tc/, heads/ and main.cfg deliberately reopen [extruder].
        return True
    if "/std.config.local/" in norm:
        return True
    if os.path.basename(os.path.dirname(norm)) == "local":
        return True
    return os.path.basename(norm) in OVERRIDE_FILES


def parse_float_list(value: str) -> list[float]:
    return [float(item) for item in value.replace(",", " ").split()]


def parse_points(value: str) -> list[tuple[float, float]]:
    numbers = parse_float_list(value)
    if len(numbers) % 2:
        raise ValueError("odd number of coordinates")
    return [(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)]


# --- SpreadCycle invariant -------------------------------------------------

TMC_HEADER_RE = re.compile(r"^tmc\d+$")


def tmc_axis(stepper: str) -> str:
    """Axis group of a TMC section target.

    >>> [tmc_axis(name) for name in ("stepper_x", "stepper_z2", "extruder")]
    ['xy', 'z', 'e']
    """
    if stepper in ("stepper_x", "stepper_y"):
        return "xy"
    if stepper.startswith("stepper_z"):
        return "z"
    return "e"


def scan_tmc_sections(text: str) -> list[dict[str, object]]:
    """Active ``[tmc<ic> ...]`` sections of one file and their options.

    Commented options are not active, exactly like in Klipper's parser.

    >>> found = scan_tmc_sections(
    ...     "[tmc2209 stepper_z]\\nrun_current: 0.6\\n#stealthchop_threshold: 0\\n"
    ...     "stealthchop_threshold: 999999  # park\\n\\n[mcu]\\nserial: /dev/x\\n")
    >>> len(found), found[0]["header"], found[0]["options"]
    (1, 'tmc2209 stepper_z', {'run_current': '0.6', 'stealthchop_threshold': '999999'})
    """
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped[0] in "#;":
            continue
        if raw[:1].isspace():
            # Continuation of a multi-line value; it never starts a section.
            continue
        match = SECTCRE.match(stripped)
        if match:
            header = match.group("header").strip()
            parts = header.split(None, 1)
            if len(parts) >= 2 and TMC_HEADER_RE.match(parts[0].lower()):
                current = {"header": header, "options": {}}
                sections.append(current)
            else:
                current = None
            continue
        if current is None:
            continue
        match = OPTCRE.match(stripped)
        if not match:
            continue
        value = match.group("value")
        for marker in ("#", ";"):
            value = value.split(marker, 1)[0]
        options = current["options"]
        assert isinstance(options, dict)
        options[match.group("option").strip().lower()] = value.strip()
    return sections


def is_partial_layer(path: str) -> bool:
    """True for a file that only reopens sections defined elsewhere.

    ``machine-extras.cfg`` adds ``uart_pin`` to an existing Z stanza; the mode
    key legitimately lives in the catalog module, so a missing
    ``stealthchop_threshold`` here is not a diagnostic.
    """
    norm = _norm(os.path.abspath(path))
    if "/std.config.local/" in norm or "/local/" in norm:
        return True
    return os.path.basename(norm) in OVERRIDE_FILES


def tmc_mode_severity(
    options: dict[str, str], partial: bool = False
) -> str | None:
    """Severity of one TMC section's ``stealthchop_threshold``.

    ``partial`` is True for a merge layer that only reopens the section (the
    mode key legitimately lives in the catalog module).

    >>> tmc_mode_severity({"stealthchop_threshold": "999999"})
    'error'
    >>> tmc_mode_severity({"stealthchop_threshold": "0"}) is None
    True
    >>> tmc_mode_severity({})
    'warning'
    >>> tmc_mode_severity({}, partial=True) is None
    True
    >>> tmc_mode_severity({"stealthchop_threshold": "fast"})
    'error'
    """
    raw = options.get("stealthchop_threshold")
    if raw is None:
        return None if partial else "warning"
    try:
        value = float(raw.split("#", 1)[0].strip())
    except ValueError:
        return "error"
    return "error" if value >= 1000 else None


def tmc_audit_paths(root: str) -> list[str]:
    """Every source file that may declare a TMC section under ``root``.

    The deployed tree flattens ``std.config.local`` next to ``printer.cfg``;
    the repository keeps the local layer under ``printers/<id>/local``.  Both
    layouts are covered, plus the profile override files that may reopen a TMC
    section (machine-extras, anchors).
    """
    patterns = (
        ("std.configs", "**", "*.cfg"),
        ("std.config.local", "**", "*.cfg"),
        ("printers", "*", "local", "**", "*.cfg"),
        ("printers", "*", "machine-extras.cfg"),
        ("printers", "*", "anchors.cfg"),
    )
    paths: list[str] = []
    for parts in patterns:
        paths.extend(glob.glob(os.path.join(root, *parts), recursive=True))
    for name in ("machine-extras.cfg", "anchors.cfg"):
        candidate = os.path.join(root, name)
        if os.path.isfile(candidate):
            paths.append(candidate)
    return sorted(set(paths))


def tmc_fix_command(
    relative_file: str, section: dict[str, object], machine: dict[str, str]
) -> str:
    """Ready-to-run ``tmc_calc.py --update-module`` command for one section.

    >>> section = {
    ...     "header": "tmc2209 stepper_z",
    ...     "options": {"run_current": "1.7"},
    ... }
    >>> tmc_fix_command(
    ...     "std.configs/mechanics/tmc/4z-tmc2209-17hs4401s.cfg", section,
    ...     {"z_motor": "17HS4401S", "z_tbl": "2", "z_toff": "3"})
    'scripts/tmc_calc.py --update-module std.configs/mechanics/tmc/4z-tmc2209-17hs4401s.cfg --mode spreadcycle --vm 24 --sections stepper_z --motor 17HS4401S --i-factor 1.0 --tbl 2 --toff 3 --force'
    """
    header = str(section["header"])
    stepper = header.split()[-1]
    axis = tmc_axis(stepper)
    vm = str(machine.get("vm_xy") or "48") if axis == "xy" else "24"
    parts = [
        "scripts/tmc_calc.py", "--update-module", relative_file,
        "--mode", "spreadcycle", "--vm", vm, "--sections", stepper,
    ]
    motor = machine.get({"xy": "xy_motor", "z": "z_motor", "e": "e_motor"}[axis])
    if motor:
        parts += ["--motor", motor]
    options = section["options"]
    assert isinstance(options, dict)
    if axis == "e":
        current = options.get("run_current")
        if current:
            parts += ["--run-current", str(current)]
        else:
            parts += ["--i-factor", "1.0"]
    else:
        parts += ["--i-factor", "1.0"]
    parts += [
        "--tbl", str(machine.get("%s_tbl" % axis) or "2"),
        "--toff", str(machine.get("%s_toff" % axis) or "3"),
        "--force",
    ]
    return " ".join(parts)


class Checker:
    def __init__(self) -> None:
        self.fileconfig = configparser.RawConfigParser(
            strict=False, inline_comment_prefixes=(";", "#")
        )
        self.section_first: dict[str, tuple[str, int]] = {}
        self.option_first: dict[tuple[str, str], tuple[str, int]] = {}
        self.visited: set[str] = set()
        self.included: set[str] = set()
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notices: list[str] = []

    # -- diagnostics ---------------------------------------------------
    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def notice(self, msg: str) -> None:
        self.notices.append(msg)

    # -- low level -----------------------------------------------------
    @staticmethod
    def read_file(filename: str) -> str:
        with open(filename, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().replace("\r\n", "\n")

    def _append(self, buf: list[tuple[int, str]], filename: str) -> None:
        if not buf:
            return
        data = "\n".join(text for _, text in buf)
        if not data:
            return
        try:
            self.fileconfig.read_file(io.StringIO(data), filename)
        except configparser.Error as exc:
            self.error(f"{filename}: parse error: {exc}")

    def _scan(self, buf: list[tuple[int, str]], filename: str) -> None:
        """Record section/option declarations the way configparser sees them."""
        cur_section: str | None = None
        for lineno, raw in buf:
            stripped = raw.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue
            if raw[:1].isspace() and cur_section is not None:
                # continuation of the previous option's value
                continue
            mo = SECTCRE.match(stripped)
            if mo:
                cur_section = mo.group("header")
                first = self.section_first.get(cur_section)
                if first is not None:
                    if not is_merge_layer(filename):
                        self.warning(
                            "duplicate section [%s] at %s:%d (first defined at %s:%d); "
                            "sections are merged by Klipper"
                            % (
                                cur_section,
                                filename,
                                lineno,
                                first[0],
                                first[1],
                            )
                        )
                else:
                    self.section_first[cur_section] = (filename, lineno)
                continue
            mo = OPTCRE.match(stripped)
            if not mo:
                continue
            if cur_section is None:
                # configparser reports this as MissingSectionHeaderError itself
                continue
            option = mo.group("option").strip().lower()
            key = (cur_section, option)
            first = self.option_first.get(key)
            if first is not None:
                if not is_merge_layer(filename):
                    self.warning(
                        "repeated option '%s' in section [%s] at %s:%d "
                        "(previous at %s:%d); last value wins"
                        % (
                            option,
                            cur_section,
                            filename,
                            lineno,
                            first[0],
                            first[1],
                        )
                    )
            else:
                self.option_first[key] = (filename, lineno)

    def _resolve_include(
        self,
        source_filename: str,
        include_spec: str,
        include_dirs: list[str] | None,
        local_dir: str | None,
    ) -> None:
        bases = [os.path.dirname(os.path.abspath(source_filename))]
        for extra in include_dirs or []:
            extra = os.path.abspath(extra)
            if extra not in bases:
                bases.append(extra)
        # In the repository local overrides live under printers/<p>/local/
        # while every profile includes them as std.config.local/<file>.
        local_prefix = "std.config.local/"
        if local_dir and include_spec.replace(os.sep, "/").startswith(local_prefix):
            candidates = [
                os.path.join(local_dir, include_spec[len(local_prefix):])
            ]
        else:
            candidates = [os.path.join(base, include_spec) for base in bases]
        matches: list[str] = []
        for include_glob in candidates:
            matches = sorted(glob.glob(include_glob))
            if matches:
                break
        if not matches:
            include_glob = candidates[0]
            if not glob.has_magic(include_glob):
                self.error(
                    "include file '%s' does not exist (included from %s)"
                    % (include_glob, source_filename)
                )
            return
        for filename in matches:
            if os.path.isdir(filename):
                self.error(
                    "include target '%s' is a directory (included from %s)"
                    % (filename, source_filename)
                )
                continue
            try:
                data = self.read_file(filename)
            except OSError as exc:
                self.error(
                    "unable to open config file %s (included from %s): %s"
                    % (filename, source_filename, exc)
                )
                continue
            self._parse_config(data, filename, include_dirs, local_dir)

    def _parse_config(
        self,
        data: str,
        filename: str,
        include_dirs: list[str] | None,
        local_dir: str | None,
    ) -> None:
        path = os.path.abspath(filename)
        if path in self.visited:
            self.error(
                "recursive include of config file '%s'" % (filename,)
            )
            return
        self.visited.add(path)
        self.included.add(path)
        lines = data.split("\n")
        buf: list[tuple[int, str]] = []
        for lineno, line in enumerate(lines, 1):
            pos = line.find("#")
            if pos >= 0:
                line = line[:pos]
            mo = SECTCRE.match(line)
            header = mo.group("header") if mo else None
            if header and header.startswith("include "):
                self._scan(buf, filename)
                self._append(buf, filename)
                buf.clear()
                include_spec = header[8:].strip()
                self._resolve_include(
                    filename, include_spec, include_dirs, local_dir
                )
            else:
                buf.append((lineno, line))
        self._scan(buf, filename)
        self._append(buf, filename)
        self.visited.remove(path)

    # -- drivers -------------------------------------------------------
    def parse_file(
        self,
        filename: str,
        include_dirs: list[str] | None = None,
        local_dir: str | None = None,
    ) -> None:
        try:
            data = self.read_file(filename)
        except OSError as exc:
            self.error("unable to open config file %s: %s" % (filename, exc))
            return
        self._parse_config(data, filename, include_dirs, local_dir)

    def check_unused_modules(self, root: str) -> None:
        included = {os.path.abspath(p) for p in self.included}
        for module_dir in ("std.configs", "std.macros"):
            base = os.path.join(root, module_dir)
            if not os.path.isdir(base):
                continue
            for path in sorted(glob.glob(os.path.join(base, "**", "*.cfg"), recursive=True)):
                if os.path.abspath(path) in included:
                    continue
                rel = _rel(path, root)
                rel_norm = _norm(rel)
                if rel_norm in ALT_MODULES:
                    continue
                if any(rel_norm.startswith(prefix) for prefix in CATALOG_PREFIXES):
                    continue
                self.notice(
                    "%s is not included by any profile and is not a known "
                    "fleet alternative" % rel
                )

    # -- driver mode ---------------------------------------------------
    def check_tmc_mode(self, root: str, machine_conf: str | None = None) -> None:
        """Fleet invariant: every TMC section runs SpreadCycle explicitly.

        An active ``stealthchop_threshold >= 1000`` makes Klipper switch the
        driver to StealthChop, where TBL/TOFF/HSTRT/HEND do nothing.  A missing
        key is SpreadCycle by Klipper default but implicit, so it is a warning.

        The audit walks the source files, not the merged tree: unreachable
        catalog files such as ``boards/fly-sb2040.cfg`` are fleet modules too
        and must not escape the rule.
        """
        machine = self._machine_values(machine_conf)
        seen: set[str] = set()
        for path in tmc_audit_paths(root):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            try:
                text = self.read_file(path)
            except OSError as exc:
                self.warning("tmc-mode: cannot read %s: %s" % (path, exc))
                continue
            rel = _norm(_rel(path, root))
            for section in scan_tmc_sections(text):
                options = section["options"]
                header = "[%s]" % section["header"]
                where = "%s (%s)" % (rel, header)
                raw = options.get("stealthchop_threshold")
                severity = tmc_mode_severity(options, is_partial_layer(path))
                if severity == "warning":
                    self.warning(
                        "tmc-mode: %s does not set stealthchop_threshold; "
                        "Klipper then runs SpreadCycle by default, but the "
                        "invariant wants the mode explicit. Add "
                        "'stealthchop_threshold: 0' and recompute the "
                        "chopper registers" % where
                    )
                elif severity == "error" and raw is not None:
                    try:
                        value = float(raw.split("#", 1)[0].strip())
                    except ValueError:
                        self.error(
                            "tmc-mode: %s has a non-numeric "
                            "stealthchop_threshold=%r" % (where, raw)
                        )
                        continue
                    if value >= 1000:
                        self.error(
                            "tmc-mode: %s sets stealthchop_threshold=%s, so "
                            "Klipper runs StealthChop and the chopper registers "
                            "do nothing. The fleet invariant is SpreadCycle; "
                            "fix it with:\n  %s"
                            % (where, raw, tmc_fix_command(rel, section, machine))
                        )

    @staticmethod
    def _machine_values(machine_conf: str | None) -> dict[str, str]:
        values: dict[str, str] = {}
        if not machine_conf or not os.path.isfile(machine_conf):
            return values
        try:
            with open(machine_conf, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
        except OSError:
            return values
        return values

    # -- object registration -------------------------------------------
    def check_probe_objects(self) -> None:
        """Reject a config that registers two probe objects.

        Klipper's ``probe`` module claims the object name "probe", and a
        ``[probe_eddy_current NAME]`` section registers itself under the same
        name.  The second registration aborts startup with "Registering
        duplicate object 'probe'".  The section scan below is needed because
        the config parser merges same-named sections silently and board
        catalog files are a merge layer, so no other diagnostic covers the
        combination [probe] + [probe_eddy_current ...].
        """
        if not self.fileconfig.has_section("probe"):
            return
        eddy = [
            name
            for name in self.fileconfig.sections()
            if name.split(None, 1)[0].lower() == "probe_eddy_current"
        ]
        if not eddy:
            return
        self.error(
            "probe: [probe]%s and [%s]%s both register the Klipper object "
            "'probe'; Klipper aborts with \"Registering duplicate object "
            "'probe'\". Keep the physical [probe] or the eddy module, not both"
            % (self._location("probe"), eddy[0], self._location(eddy[0]))
        )

    # -- geometry invariants ------------------------------------------
    def _opt(self, section: str, option: str) -> str | None:
        if not self.fileconfig.has_section(section):
            return None
        if not self.fileconfig.has_option(section, option):
            return None
        return self.fileconfig.get(section, option)

    def _float(self, section: str, option: str, default: float | None = None) -> float | None:
        raw = self._opt(section, option)
        if raw is None:
            return default
        try:
            return float(raw.strip())
        except ValueError:
            self.error("geometry: [%s] %s is not a number: %r" % (section, option, raw))
            return None

    def _points(self, section: str, option: str) -> list[tuple[float, float]]:
        raw = self._opt(section, option)
        if raw is None:
            return []
        try:
            return parse_points(raw)
        except ValueError as exc:
            self.error(
                "geometry: [%s] %s is not an X,Y list (%s)"
                % (section, option, exc)
            )
            return []

    def _triples(self, section: str, option: str) -> list[tuple[float, float, float]]:
        raw = self._opt(section, option)
        if raw is None:
            return []
        try:
            numbers = parse_float_list(raw)
        except ValueError as exc:
            self.error(
                "geometry: [%s] %s is not a number list (%s)"
                % (section, option, exc)
            )
            return []
        if len(numbers) % 3:
            self.error(
                "geometry: [%s] %s is not an X,Y,Z list (count %d)"
                % (section, option, len(numbers))
            )
            return []
        return [
            (numbers[i], numbers[i + 1], numbers[i + 2])
            for i in range(0, len(numbers), 3)
        ]

    def _load_machine_conf(self, path: str | None) -> dict[str, float]:
        values: dict[str, float] = {}
        if not path or not os.path.isfile(path):
            return values
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    try:
                        values[key.strip()] = float(value.strip())
                    except ValueError:
                        continue
        except OSError as exc:
            self.warning("geometry: cannot read machine.conf %s: %s" % (path, exc))
        return values

    def check_machine_voltage(self, machine_conf: str | None) -> None:
        """Validate vm_xy/vm_ze from machine.conf with render_profile's rules.

        The machine.conf parser and the board limit table live in
        render_profile.py, so this check cannot drift from the renderer.
        """
        if not machine_conf or not os.path.isfile(machine_conf):
            return
        values: dict[str, str] = {}
        try:
            with open(machine_conf, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
        except OSError as exc:
            self.warning("voltage: cannot read machine.conf %s: %s" % (machine_conf, exc))
            return
        render_profile = _render_profile_module()
        if render_profile is None:
            return
        model = values.get("model")
        board = values.get("board") or (
            render_profile.DEFAULT_BOARD.get(model) if model else None
        )
        if not board:
            return
        try:
            render_profile.check_voltage(values, board)
        except render_profile.ProfileError as exc:
            self.error("voltage: %s" % exc)

    def check_geometry(self, machine_conf: str | None) -> None:
        cfg = self.fileconfig
        if not cfg.has_section("stepper_x") or not cfg.has_section("stepper_y"):
            return

        def bound(section: str, option: str, default: float) -> float:
            value = self._float(section, option, default)
            return default if value is None else value

        limits = {
            "x": (bound("stepper_x", "position_min", 0.0),
                  bound("stepper_x", "position_max", 0.0)),
            "y": (bound("stepper_y", "position_min", 0.0),
                  bound("stepper_y", "position_max", 0.0)),
            "z": (bound("stepper_z", "position_min", -9999.0),
                  bound("stepper_z", "position_max", 9999.0)),
        }
        for axis, (low, high) in limits.items():
            if high <= low:
                self.error("geometry: %s position_max must be above position_min" % axis)
                continue
        off_x = self._float("probe", "x_offset", None)
        off_y = self._float("probe", "y_offset", None)
        if off_x is None or off_y is None:
            # An eddy probe registers as "probe" but has no [probe] section:
            # the offsets live in [probe_eddy_current NAME] (Klipper merges
            # them into the probe it exposes).
            eddy_section = next(
                (
                    name
                    for name in cfg.sections()
                    if name.split(None, 1)[0].lower() == "probe_eddy_current"
                ),
                None,
            )
            if eddy_section is not None:
                if off_x is None:
                    off_x = self._float(eddy_section, "x_offset", 0.0)
                if off_y is None:
                    off_y = self._float(eddy_section, "y_offset", 0.0)
        off_x = off_x or 0.0
        off_y = off_y or 0.0

        def check_xy(x: float, y: float, label: str, apply_offset: bool) -> None:
            tool_x = x - off_x if apply_offset else x
            tool_y = y - off_y if apply_offset else y
            low_x, high_x = limits["x"]
            low_y, high_y = limits["y"]
            if not (low_x - 1e-6 <= tool_x <= high_x + 1e-6):
                self.error(
                    "geometry: %s X=%.3f is outside [%.3f, %.3f]"
                    % (label, tool_x, low_x, high_x)
                )
            if not (low_y - 1e-6 <= tool_y <= high_y + 1e-6):
                self.error(
                    "geometry: %s Y=%.3f is outside [%.3f, %.3f]"
                    % (label, tool_y, low_y, high_y)
                )

        mesh_min = self._points("bed_mesh", "mesh_min")
        mesh_max = self._points("bed_mesh", "mesh_max")
        if mesh_min and mesh_max:
            (min_x, min_y), (max_x, max_y) = mesh_min[0], mesh_max[0]
            if max_x <= min_x or max_y <= min_y:
                self.error("geometry: bed_mesh mesh_max must be above mesh_min")
            check_xy(min_x, min_y, "bed_mesh mesh_min", True)
            check_xy(max_x, max_y, "bed_mesh mesh_max", True)
            raw_count = self._opt("bed_mesh", "probe_count")
            if raw_count is not None:
                try:
                    counts = [int(item) for item in parse_float_list(raw_count)]
                except ValueError:
                    counts = []
                    self.error("geometry: bed_mesh probe_count is not a number pair")
                if counts and (len(counts) != 2 or min(counts) < 3):
                    self.error(
                        "geometry: bed_mesh probe_count must be two integers >= 3"
                    )

        zero_ref = self._points("bed_mesh", "zero_reference_position")
        if zero_ref:
            x, y = zero_ref[0]
            check_xy(x, y, "bed_mesh zero_reference_position", True)
            if mesh_min and mesh_max:
                (min_x, min_y), (max_x, max_y) = mesh_min[0], mesh_max[0]
                if not (min_x <= x <= max_x and min_y <= y <= max_y):
                    # Outside the mesh it becomes an extra physical probe point.
                    tool_x, tool_y = x - off_x, y - off_y
                    self.notice(
                        "bed_mesh zero_reference_position %.3f,%.3f is outside "
                        "the mesh and will be probed at the nozzle position "
                        "%.3f,%.3f" % (x, y, tool_x, tool_y)
                    )

        home = self._points("safe_z_home", "home_xy_position")
        if home:
            check_xy(home[0][0], home[0][1], "safe_z_home home_xy_position", False)

        for section in ("z_tilt", "quad_gantry_level"):
            points = self._points(section, "points")
            for index, (x, y) in enumerate(points, 1):
                check_xy(x, y, "%s points[%d]" % (section, index), False)
            if section == "quad_gantry_level" and points and len(points) != 4:
                self.error("geometry: quad_gantry_level needs exactly 4 points")
            if section == "z_tilt" and points and len(points) < 3:
                self.warning("geometry: z_tilt has fewer than 3 points")

        resonance = self._triples("resonance_tester", "probe_points")
        low_z, high_z = limits["z"]
        for x, y, z in resonance:
            check_xy(x, y, "resonance_tester probe_points", False)
            if not (low_z - 1e-6 <= z <= high_z + 1e-6):
                self.error(
                    "geometry: resonance_tester Z=%.3f is outside [%.3f, %.3f]"
                    % (z, low_z, high_z)
                )

        z_positions = self._points("z_tilt", "z_positions")
        machine = self._load_machine_conf(machine_conf)
        if z_positions and "frame_w" in machine and "frame_d" in machine:
            xs = [x for x, _ in z_positions]
            ys = [y for _, y in z_positions]
            span_x = max(xs) - min(xs)
            span_y = max(ys) - min(ys)
            if span_x > machine["frame_w"] + 1e-6:
                self.error(
                    "geometry: z_tilt z_positions span %.1f mm exceeds the "
                    "%.1f mm frame width" % (span_x, machine["frame_w"])
                )
            if span_y > machine["frame_d"] + 1e-6:
                self.error(
                    "geometry: z_tilt z_positions span %.1f mm exceeds the "
                    "%.1f mm frame depth" % (span_y, machine["frame_d"])
                )
            # The bed need not be centred in the frame, so only reject points
            # that cannot physically sit inside one frame length of the travel.
            ext_x = (limits["x"][0] - machine["frame_w"] / 2.0,
                     limits["x"][1] + machine["frame_w"] / 2.0)
            ext_y = (limits["y"][0] - machine["frame_d"] / 2.0,
                     limits["y"][1] + machine["frame_d"] / 2.0)
            for index, (x, y) in enumerate(z_positions, 1):
                if not (ext_x[0] - 1e-6 <= x <= ext_x[1] + 1e-6):
                    self.error(
                        "geometry: z_tilt z_positions[%d] X=%.3f is far outside "
                        "the %.1f mm frame" % (index, x, machine["frame_w"])
                    )
                if not (ext_y[0] - 1e-6 <= y <= ext_y[1] + 1e-6):
                    self.error(
                        "geometry: z_tilt z_positions[%d] Y=%.3f is far outside "
                        "the %.1f mm frame" % (index, y, machine["frame_d"])
                    )

        if len(z_positions) == 3 and (
            "z_base_measured" in machine or "z_leg_measured" in machine
        ):
            ordered = sorted(z_positions, key=lambda point: point[1])
            (ax, ay), (bx, by) = ordered[0], ordered[1]
            cx, cy = max(z_positions, key=lambda point: point[1])
            base = math.hypot(bx - ax, by - ay)
            legs = (math.hypot(cx - ax, cy - ay), math.hypot(cx - bx, cy - by))
            if "z_base_measured" in machine:
                self._compare_measurement(
                    "z_positions front base", base, machine["z_base_measured"]
                )
            if "z_leg_measured" in machine:
                for index, leg in enumerate(legs, 1):
                    self._compare_measurement(
                        "z_positions leg %d" % index, leg, machine["z_leg_measured"]
                    )

        if machine_conf:
            anchors = os.path.join(os.path.dirname(machine_conf), "anchors.cfg")
            if os.path.isfile(anchors):
                with open(anchors, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                if not re.search(r"#\s*замер\s+\d{4}-\d{2}-\d{2}", text):
                    self.warning(
                        "geometry: %s has no '# замер YYYY-MM-DD' measurement date"
                        % anchors
                    )

    # -- Z endstop -----------------------------------------------------
    def check_z_endstop(self) -> None:
        """Require position_endstop when [stepper_z] homes on a physical pin.

        Klipper accepts a missing position_endstop only when Z homes through
        the probe ("probe:z_virtual_endstop"). A machine that parks Z on a
        hardware switch - the hybrid eddy setup, or an eddy machine whose
        toolhead has its own endstop - must therefore carry the calibrated
        value in [stepper_z]; without it Klipper refuses to load the section.
        """
        raw = self._opt("stepper_z", "endstop_pin")
        if raw is None:
            return
        endstop = raw.strip()
        if not endstop or endstop.lstrip("!^~").startswith("probe:"):
            return
        if self._opt("stepper_z", "position_endstop") is not None:
            return
        self.error(
            "stepper_z: endstop_pin %r is a physical endstop but "
            "position_endstop is not set; Klipper needs it (run "
            "Z_ENDSTOP_CALIBRATE, or home Z through the probe with "
            "probe:z_virtual_endstop)" % endstop
        )

    # -- MCU references ------------------------------------------------
    def _location(self, section: str, option: str | None = None) -> str:
        key = (section, option) if option is not None else None
        first = self.option_first.get(key) if key is not None else None
        if first is None:
            first = self.section_first.get(section)
        if first is None:
            return ""
        return " (%s:%d)" % first

    def declared_mcus(self) -> set[str]:
        declared = {"mcu"}
        for section in self.fileconfig.sections():
            parts = section.split(None, 1)
            if parts[0].lower() == "mcu":
                declared.add(parts[1].strip() if len(parts) > 1 else "mcu")
        return declared

    def check_mcu_references(self) -> None:
        """Verify that every MCU is declared and every declaration is used.

        Klipper resolves a pin as ``[mcu NAME]`` + ``NAME:PIN`` (or through a
        ``[board_pins]`` alias of that MCU). A prefix without a matching
        ``[mcu NAME]`` aborts Klipper at startup, and a declared MCU with no
        references makes Klipper wait forever for a node that is not wired.
        """
        declared = self.declared_mcus()
        referenced: set[str] = set()
        reported: set[str] = set()

        def report_undeclared(name: str, where: str) -> None:
            if name in declared or name in reported:
                return
            reported.add(name)
            self.error(
                "MCU %r is referenced%s but not declared; add [mcu %s] to "
                "local/uuids.cfg or disable the feature that uses it"
                % (name, where, name)
            )

        for section in self.fileconfig.sections():
            for option in self.fileconfig.options(section):
                value = self.fileconfig.get(section, option).strip()
                if not value:
                    continue
                if option.lower() in MCU_NAME_OPTIONS:
                    # Plain MCU name; never a path such as a host serial device.
                    if not value.startswith(("/", "~")) and " " not in value:
                        referenced.add(value)
                        report_undeclared(
                            value,
                            " by [%s] %s%s"
                            % (section, option, self._location(section, option)),
                        )
                for match in PIN_REFERENCE_RE.finditer(value):
                    if match.group(2) in VIRTUAL_PIN_SUFFIXES:
                        continue
                    name = match.group(1)
                    referenced.add(name)
                    report_undeclared(
                        name,
                        " by %r in [%s] %s%s"
                        % (
                            match.group(0),
                            section,
                            option,
                            self._location(section, option),
                        ),
                    )

        for name in sorted(declared):
            if name in IMPLICIT_MCUS or name in referenced:
                continue
            self.warning(
                "[mcu %s] is declared%s but nothing references it; remove the "
                "section (and the CAN node behind it) when the machine has no "
                "such board" % (name, self._location("mcu " + name))
            )

    def _compare_measurement(self, label: str, computed: float, measured: float) -> None:
        if abs(computed - measured) > 2.0:
            self.warning(
                "geometry: %s from anchors is %.2f mm, measured %.2f mm "
                "(difference > 2 mm)" % (label, computed, measured)
            )

    def merged_text(self) -> str:
        dump = configparser.RawConfigParser(strict=False)
        for section in sorted(self.fileconfig.sections()):
            dump.add_section(section)
            for option in sorted(self.fileconfig.options(section)):
                dump.set(section, option, self.fileconfig.get(section, option))
        out = io.StringIO()
        dump.write(out)
        return out.getvalue()

    def emit(self, stream=sys.stdout) -> None:
        for msg in self.errors:
            print("ERROR: " + msg, file=stream)
        for msg in self.warnings:
            print("WARNING: " + msg, file=stream)
        for msg in self.notices:
            print("NOTICE: " + msg, file=stream)
        print(
            "Summary: %d error(s), %d warning(s), %d notice(s)"
            % (len(self.errors), len(self.warnings), len(self.notices)),
            file=stream,
        )


def discover_roots(
    config_dir: str,
) -> list[tuple[str, list[str] | None, str | None, str | None]]:
    """Return (printer.cfg, include_base dirs, local override dir, machine.conf).

    A deployed tree has printer.cfg at its root and includes resolve
    relative to it, exactly like Klipper. In the repository the profile
    files live under printers/<name>/ but their include paths are written
    for the flattened deploy layout, so the profile directory and the
    repository root are both tried. Local overrides are mapped from
    std.config.local/ onto printers/<name>/local/.
    """
    root_printer = os.path.join(config_dir, "printer.cfg")
    if os.path.isfile(root_printer):
        machine_conf = os.path.join(config_dir, "machine.conf")
        return [
            (
                root_printer,
                None,
                os.path.join(config_dir, "std.config.local"),
                machine_conf if os.path.isfile(machine_conf) else None,
            )
        ]
    profiles = sorted(
        glob.glob(os.path.join(config_dir, "printers", "*", "printer.cfg"))
    )
    roots = []
    for path in profiles:
        profile_dir = os.path.dirname(path)
        machine_conf = os.path.join(profile_dir, "machine.conf")
        roots.append(
            (
                path,
                [profile_dir, config_dir],
                os.path.join(profile_dir, "local"),
                machine_conf if os.path.isfile(machine_conf) else None,
            )
        )
    return roots


def discover_machine(profile_dir: str) -> list[tuple[str, list[str] | None, str | None, str | None]]:
    """Return a single root for printers/<id> inside the repository."""
    profile_dir = os.path.abspath(profile_dir)
    printer = os.path.join(profile_dir, "printer.cfg")
    machine_conf = os.path.join(profile_dir, "machine.conf")
    repo_root = os.path.dirname(os.path.dirname(profile_dir))
    return [
        (
            printer,
            [profile_dir, repo_root],
            os.path.join(profile_dir, "local"),
            machine_conf if os.path.isfile(machine_conf) else None,
        )
    ]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Klipper config tree or dump the merged config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--config-dir",
        metavar="DIR",
        help="validate the config tree rooted at DIR",
    )
    group.add_argument(
        "--merged",
        metavar="DIR",
        help="print the merged configuration of the tree rooted at DIR to stdout",
    )
    group.add_argument(
        "--machine",
        metavar="DIR",
        help="validate one repository profile directory (printers/<id>)",
    )
    parser.add_argument(
        "--stale-check",
        action="store_true",
        help="compare every committed profile.cfg with machine.conf",
    )
    args = parser.parse_args(argv)
    if not args.config_dir and not args.merged and not args.machine and not args.stale_check:
        args.config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return args


def run_checks(
    config_dir: str,
    roots: list[tuple[str, list[str] | None, str | None, str | None]],
    dump_mode: bool,
) -> int:
    if dump_mode:
        checker = Checker()
        for filename, include_dirs, local_dir, _machine in roots:
            checker.parse_file(filename, include_dirs, local_dir)
        checker.check_unused_modules(config_dir)
        checker.check_tmc_mode(
            config_dir, next((root[3] for root in roots if root[3]), None)
        )
        sys.stdout.write(checker.merged_text())
        checker.emit(stream=sys.stderr)
        return 1 if checker.errors else 0

    had_errors = False
    all_included: set[str] = set()
    for filename, include_dirs, local_dir, machine_conf in roots:
        checker = Checker()
        checker.parse_file(filename, include_dirs, local_dir)
        checker.check_probe_objects()
        checker.check_geometry(machine_conf)
        checker.check_z_endstop()
        checker.check_machine_voltage(machine_conf)
        checker.check_mcu_references()
        checker.emit(stream=sys.stdout)
        had_errors = had_errors or bool(checker.errors)
        all_included |= checker.included

    orphan = Checker()
    orphan.included = all_included
    orphan.check_unused_modules(config_dir)
    orphan.check_tmc_mode(
        config_dir, next((root[3] for root in roots if root[3]), None)
    )
    orphan.emit(stream=sys.stdout)
    return 1 if (had_errors or orphan.errors) else 0


def stale_check(target: str | None) -> int:
    """Check that every committed profile.cfg matches its machine.conf."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import render_profile  # noqa: PLC0415 - same-directory helper

    if target:
        profile_dirs = [os.path.abspath(target)]
    else:
        repo_root = os.path.dirname(script_dir)
        profile_dirs = sorted(
            os.path.dirname(path)
            for path in glob.glob(
                os.path.join(repo_root, "printers", "*", "machine.conf")
            )
        )
    if not profile_dirs:
        print("ERROR: no printer profiles with machine.conf found", file=sys.stderr)
        return 1

    failed = False
    for profile_dir in profile_dirs:
        conf_path = os.path.join(profile_dir, "machine.conf")
        committed = os.path.join(profile_dir, "profile.cfg")
        try:
            values = render_profile.parse_machine_conf(conf_path)
            checked = render_profile.validate(values)
            includes = render_profile.build_includes(values, checked)
            expected = render_profile.render(values, checked, includes)
        except (OSError, render_profile.ProfileError, ValueError) as exc:
            print("ERROR: %s: %s" % (conf_path, exc), file=sys.stderr)
            failed = True
            continue
        try:
            with open(committed, "r", encoding="utf-8", errors="replace") as fh:
                actual = fh.read().replace("\r\n", "\n")
        except OSError as exc:
            print("ERROR: %s: %s" % (committed, exc), file=sys.stderr)
            failed = True
            continue
        if actual != expected:
            print(
                "ERROR: %s is stale; run scripts/deploy_configs.sh -p %s --render"
                % (committed, os.path.basename(profile_dir)),
                file=sys.stderr,
            )
            failed = True
        else:
            print("OK: %s" % committed)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    dump_mode = args.merged is not None

    if args.stale_check:
        return stale_check(args.machine)

    if args.machine:
        profile_dir = os.path.abspath(args.machine)
        if not os.path.isdir(profile_dir):
            print(
                "ERROR: profile directory not found: %s" % profile_dir,
                file=sys.stderr,
            )
            return 1
        if not os.path.isfile(os.path.join(profile_dir, "printer.cfg")):
            print(
                "ERROR: no printer.cfg in %s" % profile_dir, file=sys.stderr
            )
            return 1
        config_dir = os.path.dirname(os.path.dirname(profile_dir))
        roots = discover_machine(profile_dir)
    else:
        config_dir = os.path.abspath(args.merged or args.config_dir)
        if not os.path.isdir(config_dir):
            print(
                "ERROR: config directory not found: %s" % config_dir,
                file=sys.stderr,
            )
            return 1
        roots = discover_roots(config_dir)
        if not roots:
            print(
                "ERROR: no printer.cfg found in %s or %s/printers/*/printer.cfg"
                % (config_dir, config_dir),
                file=sys.stderr,
            )
            return 1

    return run_checks(config_dir, roots, dump_mode)


if __name__ == "__main__":
    raise SystemExit(main())