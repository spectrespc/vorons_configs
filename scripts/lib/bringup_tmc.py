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

The current is always ``--i-factor 1.0`` (motor nominal, clamped by the IC
limit); only the velocity pair is searched later, by ``tmc_tune.py``.

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
    machine["board"] = str(checked["board"])
    machine["xy_motor"] = str(checked["xy_motor"])
    machine["xy_driver"] = str(checked["xy_driver"])
    machine["z_motor"] = str(checked["z_motor"])
    machine["z_driver"] = str(checked["z_driver"])
    machine["e_motor"] = str(checked["e_motor"])
    machine["vm_xy"] = str(checked["vm_xy"])
    machine["vm_ze"] = str(checked["vm_ze"])

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
        rows.append({
            "module": os.path.relpath(module, repo),
            "module_abs": module,
            "section": stepper,
            "driver": driver,
            "motor": motor_for(stepper, machine),
            "vm": rail,
            "sense_resistor": rsense,
        })
    if not rows:
        raise PlanError("the merged config has no [tmc2209]/[tmc5160] sections")
    return rows


def group_rows(rows: list[dict]) -> list[list[dict]]:
    """Rows that can share one tmc_calc --update-module call."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["module"], row["driver"], row["motor"], row["vm"],
               row["sense_resistor"])
        groups.setdefault(key, []).append(row)
    return list(groups.values())


def calc_current(row: dict, repo: str) -> dict:
    """Nominal current reported by tmc_calc.py for one section (JSON mode)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(repo, "scripts", "tmc_calc.py"),
         "--driver", row["driver"], "--motor", row["motor"],
         "--vm", str(row["vm"]), "--rsense", "%.3f" % row["sense_resistor"],
         "--i-factor", "1.0", "--section", row["section"], "--json"],
        capture_output=True, text=True,
    )
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
        for row in group:
            row["run_current"] = payload["run_current"]
            row["warnings"] = payload["warnings"]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print("%-58s %-30s %-26s %4s %7s %8s"
          % ("модуль", "секция", "мотор", "В", "Rшунт", "A RMS"))
    for row in rows:
        print("%-58s %-30s %-26s %4d %7.3f %8.3f"
              % (row["module"], row["section"], row["motor"], row["vm"],
                 row["sense_resistor"], row["run_current"]))
        for warning in row.get("warnings", []):
            print("  ВНИМАНИЕ: %s" % warning)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    rows = build_plan(args.repo, args.profile, args.dest)
    failures = 0
    for group in group_rows(rows):
        first = group[0]
        sections = [row["section"] for row in group]
        command = [
            sys.executable, os.path.join(args.repo, "scripts", "tmc_calc.py"),
            "--update-module", first["module_abs"],
            "--vm", str(first["vm"]),
            "--motor", first["motor"],
            "--rsense", "%.3f" % first["sense_resistor"],
            "--i-factor", "1.0",
            "--sections", ",".join(sections),
            "--force",
        ]
        proc = subprocess.run(command, capture_output=True, text=True)
        status = "ok" if proc.returncode == 0 else "FAILED"
        changed = sum(
            1 for line in proc.stdout.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        print("%-14s %-60s %s (%d строк diff)"
              % (status, first["module"], ",".join(sections), changed))
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
    print("bringup_tmc selftest: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())