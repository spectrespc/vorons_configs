#!/usr/bin/env python3
"""Plan and apply the nominal TMC settings of every driver (bringup stage S2).

The live, merged Klipper config is the source of the section inventory:
``check_config.py --merged <live-dir>`` lists every ``[tmc2209 ...]`` /
``[tmc5160 ...]`` section with the values Klipper will actually use, including
``sense_resistor`` overrides and toolhead pin prefixes.  For each section the
script finds the repository module that defines it, resolves the motor and the
supply rail, and calls ``tmc_calc.py --update-module`` for the whole file:

* ``stepper_x``/``stepper_y`` -> ``xy_motor``, rail ``vm_xy``;
* ``stepper_z*`` -> ``z_motor``, rail ``vm_ze``;
* ``extruder``/``extruder_stepper <name>`` -> ``e_motor``, rail ``vm_ze``.

The ``motor_by_module`` table is not used here: machine.conf names the motor
explicitly, so the module name no longer has to be parsed.

The current is ``--i-factor 1.0`` (motor nominal) for X/Y and Z; the extruders
keep the current of their live section (0.55/0.60 A) and are calculated with
``--run-current``.  The TBL/TOFF chopper inputs come from the profile
(``xy_tbl/xy_toff``, ``z_tbl/z_toff``, ``e_tbl/e_toff``).  Only the velocity
pair is searched later, by ``tmc_tune.py``.

Usage:
  bringup_tmc.py plan --profile voron-t
  bringup_tmc.py plan --profile voron-t --json
  bringup_tmc.py apply --profile voron-t [--dest ~/printer_data/config]

Exit status: 0 plan/apply ok, 2 invalid input (unknown motor, missing module,
invalid machine.conf), 1 apply refused/failed by tmc_calc.py.
"""

from __future__ import annotations

import argparse
import configparser
import glob
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DEFAULT_DEST = os.path.join(os.path.expanduser("~"), "printer_data", "config")
SECTION_RE = re.compile(r"^\[(tmc2209|tmc5160)\s+([^\]]+?)\]\s*$")
INCLUDE_RE = re.compile(r"^\[include\s+(.+?)\]\s*$")
DEFAULT_RSENSE = {"tmc2209": 0.110, "tmc5160": 0.075}
VM_RANGE = {"tmc2209": (4.75, 29.0), "tmc5160": (8.0, 60.0)}


class PlanError(Exception):
    """Invalid input; reported with exit status 2."""


# --- Include graph --------------------------------------------------------


def parse_includes(path: str) -> list[str]:
    """``[include ...]`` values of one file, in order (glob patterns kept)."""
    includes: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                match = INCLUDE_RE.match(stripped)
                if match:
                    includes.append(match.group(1).strip())
    except OSError:
        return []
    return includes


def include_order(
    manifest: str, root: str, local_dir: str | None = None
) -> list[str]:
    """Absolute config paths of one profile, in Klipper's include order.

    ``manifest`` is ``profile.cfg``.  Its own includes are resolved against
    ``root`` (the deployed tree layout: profile.cfg sits next to std.configs/),
    while includes inside a nested file are resolved against that file's
    directory, exactly like Klipper.  The repository copy is also searched as a
    fallback for profile-local files (macros.cfg, anchors.cfg, machine-extras.cfg
    live in printers/<id>/ in git but next to the manifest when deployed).

    Missing files are skipped: the live tree stays the authority for the merged
    values, this list only locates the repository module of a section.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    manifest = os.path.abspath(manifest)
    profile_dir = os.path.dirname(manifest)

    def resolve(pattern: str, bases: list[str]) -> list[str]:
        matches: list[str] = []
        if os.path.isabs(pattern):
            return sorted(glob.glob(pattern))
        for base in bases:
            matches = sorted(glob.glob(os.path.join(base, pattern)))
            if matches:
                break
        return matches

    def walk(path: str, bases: list[str]) -> None:
        real = os.path.realpath(path)
        if real in seen:
            return
        seen.add(real)
        ordered.append(real)
        nested_bases = [os.path.dirname(real)] + bases
        for pattern in parse_includes(real):
            for match in resolve(pattern, nested_bases):
                walk(match, nested_bases)

    walk(manifest, [root, profile_dir])
    if local_dir:
        for path in sorted(glob.glob(os.path.join(local_dir, "*.cfg"))):
            if os.path.realpath(path) not in seen:
                seen.add(os.path.realpath(path))
                ordered.append(os.path.realpath(path))
    return ordered


def section_files(paths: list[str]) -> dict[str, str]:
    """Map section header text -> first file that defines it (include order)."""
    found: dict[str, str] = {}
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    match = SECTION_RE.match(stripped)
                    if match:
                        key = "%s %s" % (match.group(1), match.group(2).strip())
                        found.setdefault(key, path)
        except OSError:
            continue
    return found


# --- Motor/rail resolution ------------------------------------------------


def normalize_module(stem: str) -> str:
    """Module stem without its size prefix, lower case.

    >>> [normalize_module(item) for item in
    ...  ("xy-tmc5160-LDO", "3z-tmc2109-17hs4401s", "4z-tmc2209-x", "tmc2209-y")]
    ['tmc5160-ldo', 'tmc2109-17hs4401s', 'tmc2209-x', 'tmc2209-y']
    """
    name = os.path.splitext(os.path.basename(stem))[0].lower()
    for prefix in ("xy-", "3z-", "4z-"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def motor_for(section: str, machine: dict[str, str]) -> str:
    """Motor of a section, named explicitly by machine.conf.

    >>> motor_for("stepper_x", {"xy_motor": "LDO", "z_motor": "Z", "e_motor": "E"})
    'LDO'
    >>> motor_for("stepper_z2", {"xy_motor": "LDO", "z_motor": "Z", "e_motor": "E"})
    'Z'
    >>> motor_for("extruder", {"xy_motor": "LDO", "z_motor": "Z", "e_motor": "E"})
    'E'
    """
    stepper = section.split()[-1]
    if stepper in ("stepper_x", "stepper_y"):
        key = "xy_motor"
    elif stepper.startswith("stepper_z"):
        key = "z_motor"
    else:
        key = "e_motor"
    motor = machine.get(key)
    if not motor:
        raise PlanError(
            "machine.conf has no %s: add it before bringup tmc (docs/PROFILES.md)"
            % key
        )
    return motor


def rail_for(stepper: str, machine: dict[str, str]) -> int:
    """Supply rail of a stepper: vm_xy for X/Y, vm_ze (always 24) otherwise.

    >>> rail_for("stepper_x", {"vm_xy": "48", "vm_ze": "24"})
    48
    >>> rail_for("stepper_z1", {"vm_xy": "55", "vm_ze": "24"})
    24
    """
    if stepper in ("stepper_x", "stepper_y"):
        try:
            return int(machine["vm_xy"])
        except (KeyError, ValueError):
            raise PlanError("machine.conf has no usable vm_xy")
    try:
        return int(machine.get("vm_ze", "24"))
    except ValueError:
        raise PlanError("machine.conf vm_ze is not a number")


def axis_for(stepper: str) -> str:
    """Axis group of a TMC section target.

    >>> [axis_for(name) for name in ("stepper_y", "stepper_z3", "extruder")]
    ['xy', 'z', 'e']
    """
    if stepper in ("stepper_x", "stepper_y"):
        return "xy"
    if stepper.startswith("stepper_z"):
        return "z"
    return "e"


def section_mode(threshold: str | None) -> str:
    """Klipper semantics: a large stealthchop_threshold means StealthChop.

    >>> section_mode("999999"), section_mode("0"), section_mode(None)
    ('stealthchop', 'spreadcycle', 'spreadcycle')
    """
    try:
        value = float(threshold) if threshold is not None else 0.0
    except ValueError:
        return "spreadcycle"
    return "stealthchop" if value >= 1000 else "spreadcycle"


def chopper_inputs(machine: dict[str, str], axis: str) -> tuple[int, int]:
    """(TBL, TOFF) of an axis group from the resolved machine.conf.

    ``build_plan`` copies the values from ``render_profile.validate()``, which
    already applied the canonical defaults, so there is no second default here.

    >>> chopper_inputs({"xy_tbl": "0", "xy_toff": "3"}, "xy")
    (0, 3)
    >>> try:
    ...     chopper_inputs({}, "z")
    ... except PlanError as exc:
    ...     print(str(exc))
    machine.conf has no resolved z_tbl/z_toff
    """
    try:
        return int(machine["%s_tbl" % axis]), int(machine["%s_toff" % axis])
    except (KeyError, ValueError):
        raise PlanError(
            "machine.conf has no resolved %s_tbl/%s_toff" % (axis, axis)
        )


# --- Merged config --------------------------------------------------------


def merged_config(dest: str, repo: str = DEFAULT_REPO) -> configparser.RawConfigParser:
    if not os.path.isdir(dest):
        raise PlanError("live config directory not found: %s" % dest)
    proc = subprocess.run(
        [sys.executable, os.path.join(repo, "scripts", "check_config.py"),
         "--merged", dest],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-8:])
        raise PlanError("check_config.py --merged failed:\n%s" % tail)
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read_string(proc.stdout)
    except configparser.Error as exc:
        raise PlanError("cannot parse the merged config: %s" % exc)
    return parser


def build_plan(repo: str, profile: str, dest: str) -> list[dict]:
    sys.path.insert(0, os.path.join(repo, "scripts"))
    import render_profile

    profile_dir = os.path.join(repo, "printers", profile)
    conf_path = os.path.join(profile_dir, "machine.conf")
    if not os.path.isfile(conf_path):
        raise PlanError("profile not found: %s" % profile_dir)
    try:
        values = render_profile.parse_machine_conf(conf_path)
        checked = render_profile.validate(values)
    except (render_profile.ProfileError, ValueError) as exc:
        raise PlanError(str(exc))
    # Use the effective values: board/vm defaults are resolved by
    # render_profile.validate, not stored in machine.conf.
    machine = dict(values)
    for key in (
        "board", "xy_motor", "xy_driver", "z_motor", "z_driver", "e_motor",
        "vm_xy", "vm_ze", "xy_tbl", "xy_toff", "z_tbl", "z_toff", "e_tbl", "e_toff",
    ):
        machine[key] = str(checked[key])

    merged = merged_config(dest, repo)
    located = section_files(
        include_order(
            os.path.join(profile_dir, "profile.cfg"), repo,
            os.path.join(profile_dir, "local"),
        )
    )
    rows: list[dict] = []
    for section in merged.sections():
        match = SECTION_RE.match("[%s]" % section)
        if not match:
            continue
        driver, stepper = match.group(1), match.group(2).strip()
        module = located.get("%s %s" % (driver, stepper))
        if not module:
            raise PlanError(
                "no repository module defines [%s %s]: run "
                "deploy_configs.sh so the live tree and the repository match"
                % (driver, stepper)
            )
        if not module.startswith(os.path.join(repo, "std.configs")):
            raise PlanError(
                "[%s %s] is defined by %s, which is not a std.configs module"
                % (driver, stepper, os.path.relpath(module, repo))
            )
        rsense_raw = merged.get(section, "sense_resistor", fallback=None)
        try:
            rsense = float(rsense_raw) if rsense_raw is not None else DEFAULT_RSENSE[driver]
        except ValueError:
            raise PlanError("[%s %s] sense_resistor=%r is not a number"
                            % (driver, stepper, rsense_raw))
        rail = rail_for(stepper, machine)
        low, high = VM_RANGE[driver]
        if not (low <= rail <= high):
            raise PlanError(
                "[%s %s] rail %d V is outside the %s range %.2f..%.0f V"
                % (driver, stepper, rail, driver.upper(), low, high)
            )
        mode = section_mode(merged.get(section, "stealthchop_threshold", fallback=None))
        axis = axis_for(stepper)
        tbl, toff = chopper_inputs(machine, axis)
        run_current_raw = merged.get(section, "run_current", fallback=None)
        try:
            run_current_active = (
                float(run_current_raw) if run_current_raw is not None else None
            )
        except ValueError:
            raise PlanError(
                "[%s %s] run_current=%r is not a number"
                % (driver, stepper, run_current_raw)
            )
        row = {
            "module": os.path.relpath(module, repo),
            "module_abs": module,
            "section": stepper,
            "driver": driver,
            "motor": motor_for(stepper, machine),
            "vm": rail,
            "sense_resistor": rsense,
            "axis": axis,
            "tbl": tbl,
            "toff": toff,
            "mode": mode,
            "run_current_active": run_current_active,
        }
        if mode == "stealthchop":
            raise PlanError(
                "[%s %s] runs StealthChop (stealthchop_threshold=%s): the "
                "chopper registers would be silently dropped. The fleet "
                "invariant is SpreadCycle; fix it with:\n  %s"
                % (driver, stepper,
                   merged.get(section, "stealthchop_threshold", fallback=""),
                   " ".join(apply_args(row, repo, [stepper])))
            )
        if axis == "e" and run_current_active is None:
            raise PlanError(
                "[%s %s] has no run_current in the merged config: the extruder "
                "register calculation needs the section current" % (driver, stepper)
            )
        rows.append(row)
    if not rows:
        raise PlanError("the merged config has no [tmc2209]/[tmc5160] sections")
    return rows


def current_args(row: dict) -> list[str]:
    """Explicit E current, or the nominal factor for X/Y and Z.

    X/Y and Z are recomputed at ``--i-factor 1.0`` (the fleet rule); the
    extruders keep their section current, because 0.55/0.60 A are deliberate
    limits, not a fraction of the motor rating.
    """
    if row["axis"] == "e" and row.get("run_current_active") is not None:
        return ["--run-current", "%.4g" % float(row["run_current_active"])]
    return ["--i-factor", "1.0"]


def chopper_args(row: dict) -> list[str]:
    """TBL/TOFF and their source for the report."""
    return [
        "--tbl", str(row["tbl"]), "--toff", str(row["toff"]),
        "--tbl-source", "profile", "--toff-source", "profile",
    ]


def apply_args(row: dict, repo: str, sections: list[str]) -> list[str]:
    """``tmc_calc.py --update-module`` command for one group."""
    return [
        sys.executable, os.path.join(repo, "scripts", "tmc_calc.py"),
        "--update-module", row["module_abs"],
        "--driver", row["driver"],
        "--vm", str(row["vm"]),
        "--motor", row["motor"],
        "--rsense", "%.3f" % row["sense_resistor"],
        *chopper_args(row),
        *current_args(row),
        "--sections", ",".join(sections),
        "--force",
    ]


def group_rows(rows: list[dict]) -> list[list[dict]]:
    """Rows that can share one tmc_calc --update-module call.

    The axis, the chopper inputs and (for E) the active current are part of the
    key: ``extruder`` at 0.55 A and ``ext-extruder`` at 0.60 A must not collapse
    into one call with one current.

    >>> base = {"module": "m", "driver": "tmc2209", "motor": "E", "vm": 24,
    ...         "sense_resistor": 0.11, "axis": "e", "tbl": 0, "toff": 3}
    >>> rows = [dict(base, run_current_active=0.55),
    ...         dict(base, run_current_active=0.60)]
    >>> [len(group) for group in group_rows(rows)]
    [1, 1]
    """
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        current = row["run_current_active"] if row["axis"] == "e" else None
        key = (row["module"], row["driver"], row["motor"], row["vm"],
               row["sense_resistor"], row["axis"], row["tbl"], row["toff"], current)
        groups.setdefault(key, []).append(row)
    return list(groups.values())


def calc_current(row: dict, repo: str) -> dict:
    """Current and chopper registers reported by tmc_calc.py (JSON mode)."""
    command = [
        sys.executable, os.path.join(repo, "scripts", "tmc_calc.py"),
        "--driver", row["driver"], "--motor", row["motor"],
        "--vm", str(row["vm"]), "--rsense", "%.3f" % row["sense_resistor"],
        *chopper_args(row), *current_args(row),
        "--section", row["section"], "--json",
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PlanError(
            "tmc_calc.py failed for [%s %s]: %s"
            % (row["driver"], row["section"], (proc.stderr or proc.stdout).strip())
        )
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise PlanError("tmc_calc.py returned invalid JSON: %s" % exc)
    payload["warnings"] = payload.get("warnings", [])
    return payload


def cmd_plan(args: argparse.Namespace) -> int:
    rows = build_plan(args.repo, args.profile, args.dest)
    for group in group_rows(rows):
        payload = calc_current(group[0], args.repo)
        chopper = payload.get("chopper") or {}
        for row in group:
            row["run_current"] = payload["run_current"]
            row["tbl"] = payload["tbl"]
            row["toff"] = payload["toff"]
            row["tbl_source"] = payload["tbl_source"]
            row["toff_source"] = payload["toff_source"]
            row["hstrt"] = chopper.get("hstrt")
            row["hend"] = chopper.get("hend")
            row["current_source"] = (
                "run_current %.4g A" % float(row["run_current_active"])
                if row["axis"] == "e" else "i-factor 1.0"
            )
            row["warnings"] = payload["warnings"]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print("%-52s %-30s %-24s %3s %7s %8s %9s %10s %s"
          % ("модуль", "секция", "мотор", "В", "Rшунт", "A RMS",
             "TBL/TOFF", "HSTRT/HEND", "ток; входы"))
    for row in rows:
        print("%-52s %-30s %-24s %3d %7.3f %8.3f %9s %10s %s; %s/%s"
              % (row["module"], row["section"], row["motor"], row["vm"],
                 row["sense_resistor"], row["run_current"],
                 "%s/%s" % (row["tbl"], row["toff"]),
                 "%s/%s" % (row["hstrt"], row["hend"]),
                 row["current_source"], row["tbl_source"], row["toff_source"]))
        for warning in row.get("warnings", []):
            print("  ВНИМАНИЕ: %s" % warning)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    rows = build_plan(args.repo, args.profile, args.dest)
    failures = 0
    for group in group_rows(rows):
        first = group[0]
        sections = [row["section"] for row in group]
        command = apply_args(first, args.repo, sections)
        proc = subprocess.run(command, capture_output=True, text=True)
        status = "ok" if proc.returncode == 0 else "FAILED"
        changed = sum(
            1 for line in proc.stdout.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        print("%-14s %-60s TBL/TOFF=%s/%s %s (%d строк diff)"
              % (status, first["module"], first["tbl"], first["toff"],
                 ",".join(sections), changed))
        for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines():
            stripped = line.strip()
            if stripped.startswith(("ВНИМАНИЕ", "WARNING", "ERROR")):
                print("  %s" % stripped)
        if proc.returncode != 0:
            failures += 1
            for line in (proc.stderr or proc.stdout).splitlines()[-4:]:
                print("  %s" % line)
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Расчёт номинальных TMC-настроек всех драйверов (этап tmc).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  bringup_tmc.py plan --profile voron-t\n"
            "  bringup_tmc.py apply --profile voron-t --dest ~/printer_data/config\n"
        ),
    )
    parser.add_argument("command", choices=("plan", "apply", "selftest"))
    parser.add_argument("--profile", help="id профиля (printers/<id>)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="git-клон конфигов")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="живой каталог Klipper")
    parser.add_argument("--json", action="store_true", help="plan: JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "selftest":
        return selftest()
    if not args.profile:
        print("ERROR: --profile is required", file=sys.stderr)
        return 2
    try:
        if args.command == "plan":
            return cmd_plan(args)
        return cmd_apply(args)
    except PlanError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


def selftest() -> int:
    import doctest

    failures = doctest.testmod(sys.modules[__name__], verbose=False)
    print("doctest: %d failed, %d run" % (failures.failed, failures.attempted))
    bad = failures.failed
    repo = DEFAULT_REPO
    profile_dir = os.path.join(repo, "printers", "voron-t")
    order = include_order(os.path.join(profile_dir, "profile.cfg"), repo,
                          os.path.join(profile_dir, "local"))
    if not order or not order[0].endswith("profile.cfg"):
        bad += 1
        print("MISMATCH: include order does not start with profile.cfg")
    located = section_files(order)
    for key in ("tmc5160 stepper_x", "tmc2209 stepper_z",
                "tmc2209 extruder", "tmc2209 extruder_stepper ext-extruder"):
        if key not in located:
            bad += 1
            print("MISMATCH: section %r not located" % key)

    # Offline: SpreadCycle Z and E sections must produce a non-empty chopper
    # block, and E keeps its section current instead of the motor rating.
    probes = (
        {"driver": "tmc2209", "motor": "17HS4401S", "vm": 24,
         "sense_resistor": 0.110, "section": "stepper_z", "axis": "z",
         "tbl": 2, "toff": 3},
        {"driver": "tmc2209", "motor": "MOONS-CSE14HRA1L410A-01", "vm": 24,
         "sense_resistor": 0.110, "section": "extruder", "axis": "e",
         "tbl": 0, "toff": 3, "run_current_active": 0.55},
    )
    for row in probes:
        try:
            payload = calc_current(row, repo)
        except PlanError as exc:
            bad += 1
            print("MISMATCH: %s" % exc)
            continue
        if not payload.get("chopper"):
            bad += 1
            print("MISMATCH: [%s] has no chopper block" % row["section"])
        if row["axis"] == "e" and abs(payload["run_current"] - 0.55) > 1e-9:
            bad += 1
            print("MISMATCH: E run_current=%r" % payload["run_current"])
        if row["axis"] == "z" and abs(payload["run_current"] - 1.7) > 1e-9:
            bad += 1
            print("MISMATCH: Z run_current=%r" % payload["run_current"])
    print("bringup_tmc selftest: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())