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

Exit status: 1 if at least one error was found, otherwise 0.

Diagnostics:
  ERROR    missing/recursive include, parse error
  WARNING  duplicate section name, repeated option (last-wins)
  NOTICE   module .cfg under std.configs/ or std.macros/ that is not
           included by any profile and is not a known fleet alternative
"""

from __future__ import annotations

import argparse
import configparser
import glob
import io
import os
import sys

SECTCRE = configparser.RawConfigParser.SECTCRE
OPTCRE = configparser.RawConfigParser.OPTCRE

# Modules that are deliberately kept in the repository as fleet alternatives
# and are therefore not expected to be included by the reference profile.
# Both pre- and post-rename spellings are listed so the checker works on the
# tree before and after restructure.
ALT_MODULES = {
    "std.configs/pinout/ebb36-v1.2.cfg",
    "std.configs/pinout/fly-sb2040.cfg",
    "std.configs/gantry/TMC/xy-tmc5160-LDO-42SHT48-2804AC.cfg",
    "std.configs/extruder/extruder/BMG.8T.cfg",
    "std.configs/extruder/heads/BMG.8T.cfg",
    "std.configs/extruder/tc/104-gt2.cfg",
    "std.configs/sht36-v3.eddy.cfg",
    "std.configs/tc.ext/y.frame.cfg",
    "std.macros/homing.cfg",
    "std.macros/actions_filament.cfg",
    "std.macros/filamen_load_unload.cfg",
    "std.macros/filament_load_unload.cfg",
}


def _rel(path: str, root: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


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
        bases = include_dirs or [os.path.dirname(os.path.abspath(source_filename))]
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
            self._parse_config(data, filename, None, local_dir)

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
                if rel.replace(os.sep, "/") in ALT_MODULES:
                    continue
                self.notice(
                    "%s is not included by any profile and is not a known "
                    "fleet alternative" % rel
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
) -> list[tuple[str, list[str] | None, str | None]]:
    """Return (printer.cfg path, include_base dirs, local override dir) tuples.

    A deployed tree has printer.cfg at its root and includes resolve
    relative to it, exactly like Klipper. In the repository the profile
    files live under printers/<name>/ but their include paths are written
    for the flattened deploy layout, so the profile directory and the
    repository root are both tried. No include name is ambiguous between
    the two locations. Local overrides are mapped from std.config.local/
    onto printers/<name>/local/.
    """
    root_printer = os.path.join(config_dir, "printer.cfg")
    if os.path.isfile(root_printer):
        return [
            (
                root_printer,
                None,
                os.path.join(config_dir, "std.config.local"),
            )
        ]
    profiles = sorted(
        glob.glob(os.path.join(config_dir, "printers", "*", "printer.cfg"))
    )
    return [
        (
            path,
            [os.path.dirname(path), config_dir],
            os.path.join(os.path.dirname(path), "local"),
        )
        for path in profiles
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
    args = parser.parse_args(argv)
    if not args.config_dir and not args.merged:
        args.config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    dump_mode = args.merged is not None
    config_dir = os.path.abspath(args.merged or args.config_dir)
    if not os.path.isdir(config_dir):
        print("ERROR: config directory not found: %s" % config_dir, file=sys.stderr)
        return 1

    roots = discover_roots(config_dir)
    if not roots:
        print(
            "ERROR: no printer.cfg found in %s or %s/printers/*/printer.cfg"
            % (config_dir, config_dir),
            file=sys.stderr,
        )
        return 1

    checker = Checker()
    for filename, include_dirs, local_dir in roots:
        checker.parse_file(filename, include_dirs, local_dir)
    checker.check_unused_modules(config_dir)

    if dump_mode:
        sys.stdout.write(checker.merged_text())
        checker.emit(stream=sys.stderr)
    else:
        checker.emit(stream=sys.stdout)

    return 1 if checker.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())