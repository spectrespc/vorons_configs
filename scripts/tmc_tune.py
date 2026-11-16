#!/usr/bin/env python3
"""Find max_velocity/max_accel at the nominal motor current (TEST_SPEED runner).

The script does not invent currents: for every X/Y driver it asks
scripts/tmc_calc.py for the nominal value (``--i-factor 1.0``) and applies it
with ``SET_TMC_CURRENT`` plus the calculated SpreadCycle registers with
``SET_TMC_FIELD``.  Only the velocity/acceleration pair is searched.

Search: a ladder from the configured pair, both values scaled by 1.25, up to
``--max-velocity``/``--max-accel`` (default 2x the configured pair), then a
bisection of the first failed interval.  One run is one ``TEST_SPEED`` macro
call; skipped steps are detected by comparing the MCU stepper positions of the
two ``GET_POSITION`` outputs (delta above one full step = microsteps counts).

Usage:
  tmc_tune.py --profile printers/voron-t --dry-plan
  tmc_tune.py --profile printers/voron-t --run
  tmc_tune.py --profile printers/voron-t --run --apply
  tmc_tune.py --profile printers/voron-t --run --heat --iterations 2
  tmc_tune.py --profile printers/voron-t --run --offline-result 800,12000 --apply
  tmc_tune.py --selftest

Safety:
* the printer must be idle and cool (< 40 C) unless ``--heat`` is given;
  ``--heat`` preheats to 150/110 C, which is still below the probe guard limit
  (strictly greater than 150 C);
* Z is never tested: a Z skip rams the nozzle into the bed.  Z drivers are only
  regenerated at nominal current by bringup.sh/tmc_calc.py;
* every abort path restores the configured currents and velocity limits in a
  ``finally`` block, and a Klipper shutdown stops the series immediately.

Exit status: 0 finished (recommendations may still say "no change"), 1 unsafe
abort (Klipper shutdown, apply failure), 2 input/validation error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from bringup_api import Moonraker, MoonrakerError  # noqa: E402

TMC_CALC = os.path.join(SCRIPT_DIR, "tmc_calc.py")
DEPLOY = os.path.join(SCRIPT_DIR, "deploy_configs.sh")
MOTORS_DB = os.path.join(REPO_ROOT, "docs", "tmc", "motors.json")
DEFAULT_URL = "http://127.0.0.1:7125"
STEPPERS = ("stepper_x", "stepper_y")
LADDER_FACTOR = 1.25
APPROVE_MARKER = "# tmc_tune.py: подобранные лимиты (не удаляйте строку-маркер)"


class TuneError(Exception):
    """Input or safety error; reported with exit status 2."""


# --- Parsing --------------------------------------------------------------


def parse_mcu_positions(messages: list[str]) -> dict[str, int]:
    """MCU step positions from GET_POSITION output lines.

    Klipper answers GET_POSITION with several ``// ...`` lines; the first one
    starts with ``mcu:`` and holds the step counters reported by the MCUs.
    Only ``stepper_x``/``stepper_y`` are interesting for a speed test.

    >>> lines = ["// mcu: stepper_x:1200 stepper_y:-80 stepper_z:0",
    ...          "// stepper: stepper_x:37.5 stepper_y:-2.5"]
    >>> parse_mcu_positions(lines)
    {'stepper_x': 1200, 'stepper_y': -80}
    >>> parse_mcu_positions(["// unknown"]) == {}
    True

    >>> parse_mcu_positions(["// mcu: stepper_x:100 stepper_y:200",
    ...                      "// mcu: stepper_x:104 stepper_y:200"])
    {'stepper_x': 104, 'stepper_y': 200}
    """
    positions: dict[str, int] = {}
    for message in messages:
        text = message.strip()
        if text.startswith("//"):
            text = text[2:].strip()
        if not text.startswith("mcu:"):
            continue
        for name, value in re.findall(r"(stepper_[a-z0-9]+):(-?\d+)", text):
            if name in STEPPERS:
                positions[name] = int(value)
    return positions


def microsteps_threshold(microsteps: int) -> tuple[int, int]:
    """(pass limit, ambiguity limit) in MCU step counts.

    >>> microsteps_threshold(32)
    (16, 32)
    """
    return microsteps // 2, microsteps


def verdict(delta: int, microsteps: int) -> str:
    """Classify one run: pass, repeat (ambiguous) or skip.

    >>> [verdict(0, 32), verdict(16, 32), verdict(17, 32), verdict(-33, 32)]
    ['pass', 'pass', 'repeat', 'skip']
    """
    low, high = microsteps_threshold(microsteps)
    magnitude = abs(delta)
    if magnitude <= low:
        return "pass"
    if magnitude <= high:
        return "repeat"
    return "skip"


def plan_ladder(
    velocity: float,
    accel: float,
    max_velocity: float | None,
    max_accel: float | None,
    max_runs: int,
) -> list[tuple[float, float]]:
    """Ladder of (velocity, accel) pairs from the configured one.

    >>> plan_ladder(700, 10000, 1400, 20000, 10)
    [(700, 10000), (875, 12500), (1094, 15625), (1368, 19531), (1400, 20000)]
    >>> plan_ladder(300, 3000, None, None, 3)
    [(300, 3000), (375, 3750), (469, 4688)]
    """
    limit_v = int(round(max_velocity if max_velocity is not None else velocity * 2))
    limit_a = int(round(max_accel if max_accel is not None else accel * 2))
    points = [(int(round(velocity)), int(round(accel)))]
    while len(points) < max_runs:
        current_v, current_a = points[-1]
        next_v = min(int(round(current_v * LADDER_FACTOR)), limit_v)
        next_a = min(int(round(current_a * LADDER_FACTOR)), limit_a)
        if (next_v, next_a) == (current_v, current_a):
            break
        points.append((next_v, next_a))
    return points


def bisect_pair(
    low: tuple[float, float], high: tuple[float, float]
) -> tuple[float, float] | None:
    """Midpoint of a failed interval, or None when it is already tight.

    >>> bisect_pair((700, 10000), (1400, 20000))
    (1050, 15000)
    >>> bisect_pair((1000, 10000), (1010, 10100)) is None
    True
    """
    low_v, low_a = low
    high_v, high_a = high
    if high_v - low_v <= max(2.0, low_v * 0.01) and high_a - low_a <= max(
        20.0, low_a * 0.01
    ):
        return None
    return (round((low_v + high_v) / 2), round((low_a + high_a) / 2))


def patch_machine_extras(text: str, velocity: float, accel: float) -> tuple[str, bool]:
    """Insert/replace [printer] max_velocity/max_accel (idempotent).

    >>> example = "[idle_timeout]\\ntimeout: 60\\n"
    >>> new, changed = patch_machine_extras(example, 800, 12000)
    >>> changed, "max_velocity: 800" in new, new.count("[printer]")
    (True, True, 1)
    >>> again, changed_again = patch_machine_extras(new, 800, 12000)
    >>> changed_again, again == new
    (False, True)
    >>> updated, _ = patch_machine_extras(new, 900, 13000)
    >>> "max_velocity: 900" in updated and "max_velocity: 800" not in updated
    True
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "[printer]":
            start = index
            break
    if start is None:
        block = [
            "",
            APPROVE_MARKER,
            "[printer]",
            "max_velocity: %g" % velocity,
            "max_accel: %g" % accel,
        ]
        return text.rstrip("\n") + "\n" + "\n".join(block) + "\n", True
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip().startswith("["):
            end = index
            break
    body = lines[start + 1:end]
    wanted = {
        "max_velocity": "max_velocity: %g" % velocity,
        "max_accel": "max_accel: %g" % accel,
    }
    seen: set[str] = set()
    new_body: list[str] = []
    for line in body:
        stripped = line.strip()
        key = stripped.split(":", 1)[0] if ":" in stripped else ""
        if key in wanted and not stripped.startswith("#"):
            new_body.append(wanted[key])
            seen.add(key)
        else:
            new_body.append(line)
    missing = [key for key in wanted if key not in seen]
    if missing:
        while new_body and not new_body[-1].strip():
            new_body.pop()
        new_body.extend(wanted[key] for key in missing)
    new_lines = lines[:start + 1] + new_body + lines[end:]
    new_text = "\n".join(new_lines) + "\n"
    return new_text, new_text != text


# --- Config helpers -------------------------------------------------------


def read_machine_conf(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError as exc:
        raise TuneError("cannot read %s: %s" % (path, exc))
    return values


def driver_of_module(module: str) -> str:
    """TMC IC name from a module stem.

    >>> [driver_of_module(item) for item in ("tmc5160-LDO", "tmc2209-x", "x")]
    ['tmc5160', 'tmc2209', '']
    """
    for name in ("tmc5160", "tmc2209"):
        if module.lower().startswith(name):
            return name
    return ""


def railway_values(machine: dict[str, str]) -> tuple[int, str, str]:
    """(vm_xy, xy_driver IC, board family)."""
    import render_profile

    board = machine.get("board") or render_profile.DEFAULT_BOARD.get(
        machine.get("model", "")
    )
    if not board:
        raise TuneError("machine.conf has no board")
    vm = machine.get("vm_xy")
    if not vm:
        raise TuneError("machine.conf has no vm_xy")
    driver = machine.get("xy_driver") or render_profile.DEFAULT_XY_DRIVER
    return int(vm), driver, render_profile.board_family(board)


def module_path(machine: dict[str, str]) -> str:
    _vm, driver, family = railway_values(machine)
    motor = machine.get("xy_motor")
    if not motor:
        raise TuneError("machine.conf has no xy_motor")
    return os.path.join(
        REPO_ROOT, "std.configs", "mechanics", "tmc", family,
        "xy-%s-%s.cfg" % (driver, motor),
    )


def tmc_calc_settings(motor: str, driver: str, vm: int) -> dict[str, object]:
    """Nominal current and registers from tmc_calc.py (single source)."""
    command = [
        sys.executable, TMC_CALC, "--driver", driver, "--motor", motor,
        "--vm", str(vm), "--i-factor", "1.0", "--json",
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TuneError(
            "tmc_calc.py failed (%d): %s"
            % (proc.returncode, (proc.stderr or proc.stdout).strip())
        )
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise TuneError("tmc_calc.py returned invalid JSON: %s" % exc)
    section = payload.get("sections", [{}])[0].get("config", {})
    return {
        "run_current": float(payload["run_current"]),
        "hold_current": payload.get("hold_current"),
        "stealthchop_threshold": float(payload["stealthchop_threshold"]),
        "tbl": section.get("driver_TBL"),
        "toff": section.get("driver_TOFF"),
        "hstrt": section.get("driver_HSTRT"),
        "hend": section.get("driver_HEND"),
        "warnings": payload.get("warnings", []),
        "notes": payload.get("notes", []),
    }


def motor_for_driver(machine: dict[str, str]) -> str:
    """X/Y motor named by machine.conf.

    >>> motor_for_driver({"xy_motor": "LDO-42STH48-2804AC"})
    'LDO-42STH48-2804AC'
    """
    motor = machine.get("xy_motor")
    if not motor:
        raise TuneError("machine.conf has no xy_motor (docs/PROFILES.md)")
    return motor


# --- Moonraker stages -----------------------------------------------------


def gcode_macro_exists(config: dict, name: str) -> bool:
    return any(key.startswith("gcode_macro") and key.split()[-1] == name
               for key in config)


def wait_for_position(api: Moonraker, since: float, timeout: float) -> list[str]:
    """Wait for both GET_POSITION answers (before and after the pattern).

    TEST_SPEED emits GET_POSITION twice: right after homing and after the
    pattern plus another G28.  The second ``mcu:`` line is the completion
    barrier, so no fixed sleep is needed.
    """
    deadline = time.time() + timeout
    cursor = since
    collected: list[str] = []
    while time.time() < deadline:
        entries, cursor = api.store_since(cursor)
        collected.extend(str(entry.get("message", "")) for entry in entries)
        mcu_lines = [line for line in collected
                     if line.lstrip().startswith("// mcu:")]
        if len(mcu_lines) >= 2:
            return mcu_lines
        state = api.klipper_state()
        if state in ("shutdown", "error"):
            info = api.printer_info()
            raise MoonrakerError(
                "Klipper state=%s during TEST_SPEED: %s"
                % (state, info.get("state_message", "no message"))
            )
        time.sleep(0.5)
    raise MoonrakerError("GET_POSITION did not appear in %.0f s" % timeout)


def wait_for_marker(api: Moonraker, since: float, marker: str, timeout: float) -> list[str]:
    """Wait for a ``RESPOND MSG=`` sentinel queued after a macro.

    The gcode queue is sequential, so the sentinel only appears once the macro
    before it has finished.
    """
    deadline = time.time() + timeout
    cursor = since
    collected: list[str] = []
    while time.time() < deadline:
        entries, cursor = api.store_since(cursor)
        collected.extend(str(entry.get("message", "")) for entry in entries)
        if any(marker in line for line in collected):
            return collected
        if api.klipper_state() in ("shutdown", "error"):
            raise MoonrakerError("Klipper stopped while waiting for %s" % marker)
        time.sleep(0.5)
    raise MoonrakerError("marker %s not seen in %.0f s" % (marker, timeout))


def run_test(
    api: Moonraker, velocity: float, accel: float, iterations: int,
    heat: bool, timeout: float, microsteps: int,
) -> dict[str, object]:
    """Run one TEST_SPEED and classify it by the MCU position delta."""
    cursor = api.store_since(None)[1]
    script = "TEST_SPEED SPEED=%d ACCEL=%d ITERATIONS=%d BOUND=20%s" % (
        round(velocity), round(accel), max(1, iterations), " HEAT=1" if heat else ""
    )
    api.gcode(script, timeout=timeout)
    lines = wait_for_position(api, cursor, timeout)
    before = parse_mcu_positions([lines[0]])
    after = parse_mcu_positions([lines[-1]])
    if not before or not after:
        raise MoonrakerError("could not parse both MCU positions (got %r)" % lines)
    deltas = {name: after.get(name, 0) - before.get(name, 0) for name in STEPPERS}
    results = {name: verdict(deltas[name], microsteps) for name in STEPPERS}
    overall = "skip" if "skip" in results.values() else (
        "repeat" if "repeat" in results.values() else "pass"
    )
    return {
        "velocity": float(velocity),
        "accel": float(accel),
        "delta_x": deltas["stepper_x"],
        "delta_y": deltas["stepper_y"],
        "verdict": overall,
    }


class Applier:
    """Baseline TMC/velocity state with a guaranteed restore path."""

    def __init__(self, api: Moonraker, config: dict, warn):
        self.api = api
        self.config = config
        self.warn = warn
        self.applied = False

    def _config_current(self, stepper: str) -> float | None:
        for key, section in self.config.items():
            if key.startswith("tmc") and key.split()[-1] == stepper:
                try:
                    return float(section.get("run_current", 0))
                except (TypeError, ValueError):
                    return None
        return None

    def apply(self, settings: dict[str, object], steppers=STEPPERS) -> None:
        run = float(settings["run_current"])
        hold = settings.get("hold_current")
        for stepper in steppers:
            limit = self._config_current(stepper)
            current = run
            if limit is not None and run > limit + 1e-9:
                self.warn(
                    "%s: конфиг ограничивает ток %.3f A, применено %.3f A "
                    "(сначала разверните модуль TMC)" % (stepper, limit, limit)
                )
                current = limit
            script = "SET_TMC_CURRENT STEPPER=%s CURRENT=%.4f" % (stepper, current)
            if hold:
                hold_value = min(float(hold), current)
                script += " HOLDCURRENT=%.4f" % hold_value
            self.api.gcode(script)
            if float(settings["stealthchop_threshold"]) < 1000:
                for field in ("tbl", "toff", "hstrt", "hend"):
                    value = settings.get(field)
                    if value is None or value == "":
                        continue
                    self.api.gcode(
                        "SET_TMC_FIELD STEPPER=%s FIELD=%s VALUE=%s"
                        % (stepper, field, value)
                    )
        self.applied = True

    def restore(self) -> None:
        """Put back the configured currents and velocity limits."""
        for stepper in STEPPERS:
            limit = self._config_current(stepper)
            if limit is None:
                continue
            try:
                self.api.gcode(
                    "SET_TMC_CURRENT STEPPER=%s CURRENT=%.4f" % (stepper, limit)
                )
            except MoonrakerError as exc:
                self.warn("restore %s: %s" % (stepper, exc))
        printer = self.config.get("printer", {})
        if "max_velocity" in printer and "max_accel" in printer:
            try:
                self.api.gcode(
                    "SET_VELOCITY_LIMIT VELOCITY=%s ACCEL=%s"
                    % (printer["max_velocity"], printer["max_accel"])
                )
            except MoonrakerError as exc:
                self.warn("restore velocity limits: %s" % exc)


# --- Search ---------------------------------------------------------------


def search(
    api: Moonraker,
    args: argparse.Namespace,
    microsteps: int,
    printer_conf: dict,
) -> tuple[tuple[float, float], list[dict[str, object]], list[str]]:
    """Ladder + bisection; returns the best pair, run log and notes."""
    notes: list[str] = []
    current = (
        float(printer_conf.get("max_velocity", 0) or 0),
        float(printer_conf.get("max_accel", 0) or 0),
    )
    if not current[0] or not current[1]:
        raise TuneError("configfile has no printer.max_velocity/max_accel")
    ladder = plan_ladder(
        current[0], current[1], args.max_velocity, args.max_accel, args.max_runs
    )
    log: list[dict[str, object]] = []
    best: tuple[float, float] | None = None
    failed: tuple[float, float] | None = None

    def attempt(pair: tuple[float, float]) -> str:
        result = run_test(
            api, pair[0], pair[1], args.iterations, args.heat,
            args.run_timeout, microsteps,
        )
        log.append(result)
        if args.cooldown:
            time.sleep(args.cooldown)
        return str(result["verdict"])

    for pair in ladder:
        if len(log) >= args.max_runs:
            break
        outcome = attempt(pair)
        if outcome == "repeat":
            # Ambiguous (half step .. one full step): one repeat decides.
            outcome = attempt(pair)
        if outcome == "pass":
            best = pair
            continue
        failed = pair
        notes.append(
            "Провал на %.0f мм/с / %.0f мм/с²: %s" % (pair[0], pair[1], outcome)
        )
        break
    if best is None:
        # The configured pair already fails: search downwards, never up.
        notes.append(
            "Текущие лимиты уже агрессивны: %.0f/%.0f не прошли, поиск вниз"
            % (current[0], current[1])
        )
        pair = current
        for _ in range(3):
            if len(log) >= args.max_runs:
                break
            pair = (round(pair[0] * 0.9), round(pair[1] * 0.9))
            outcome = attempt(pair)
            if outcome == "repeat":
                outcome = attempt(pair)
            if outcome == "pass":
                best = pair
                break
        if best is None:
            raise TuneError(
                "ни одна пара не прошла TEST_SPEED; проверьте ремни/токи вручную"
            )
        return best, log, notes
    if failed is not None:
        low, high = best, failed
        for _ in range(3):
            if len(log) >= args.max_runs:
                break
            middle = bisect_pair(low, high)
            if middle is None:
                break
            outcome = attempt(middle)
            if outcome == "repeat":
                outcome = attempt(middle)
            if outcome == "pass":
                low = middle
            else:
                high = middle
        best = low
    return best, log, notes


# --- Reporting ------------------------------------------------------------


def render_report(
    profile: str, best: tuple[float, float], log: list[dict[str, object]],
    notes: list[str], settings: dict[str, object], apply_note: str | None,
) -> str:
    lines = [
        "# tmc_tune: %s" % profile,
        "",
        "| скорость, мм/с | ускорение, мм/с² | ΔX, шаги | ΔY, шаги | вердикт |",
        "|---:|---:|---:|---:|---|",
    ]
    for row in log:
        lines.append(
            "| %.0f | %.0f | %+d | %+d | %s |"
            % (row["velocity"], row["accel"], row["delta_x"], row["delta_y"],
               row["verdict"])
        )
    lines.extend([
        "",
        "Итог: max_velocity=%.0f max_accel=%.0f (номинал %.3f A RMS)"
        % (best[0], best[1], float(settings["run_current"])),
    ])
    for note in notes:
        lines.append("Примечание: %s" % note)
    if apply_note:
        lines.append(apply_note)
    return "\n".join(lines)


# --- Main -----------------------------------------------------------------


def read_printer_section(path: str) -> dict[str, str]:
    """Options of the [printer] section of a Klipper file (no includes)."""
    values: dict[str, str] = {}
    inside = False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("["):
                    inside = stripped == "[printer]"
                    continue
                if not inside or not stripped or stripped.startswith("#"):
                    continue
                if ":" not in stripped:
                    continue
                key, value = stripped.split(":", 1)
                values[key.strip()] = value.split("#", 1)[0].strip()
    except OSError as exc:
        raise TuneError("cannot read %s: %s" % (path, exc))
    return values


def effective_limits(profile_dir: str, model: str) -> tuple[float, float]:
    """Configured max_velocity/max_accel of a profile (mechanic + extras).

    >>> import tempfile, os as _os
    >>> folder = tempfile.mkdtemp()
    >>> _ = open(_os.path.join(folder, "machine-extras.cfg"), "w").write(
    ...     "[printer]\\nmax_velocity: 900\\nmax_accel: 13000\\n")
    >>> effective_limits(folder, "trident")
    (900.0, 13000.0)
    """
    mechanic = os.path.join(REPO_ROOT, "std.configs", "mechanics",
                            "%s.cfg" % model)
    limits = read_printer_section(mechanic)
    extras = os.path.join(profile_dir, "machine-extras.cfg")
    if os.path.isfile(extras):
        limits.update(read_printer_section(extras))
    try:
        return float(limits["max_velocity"]), float(limits["max_accel"])
    except KeyError as exc:
        raise TuneError("no %s in [printer] of %s" % (exc, mechanic))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Подбор max_velocity/max_accel на номинальном токе (TEST_SPEED).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  tmc_tune.py --profile printers/voron-t --dry-plan\n"
            "  tmc_tune.py --profile printers/voron-t --run --apply\n"
            "  tmc_tune.py --profile printers/voron-t --run --heat --iterations 2\n"
        ),
    )
    parser.add_argument("--profile", metavar="DIR",
                        help="каталог профиля printers/<id>")
    parser.add_argument("--url", default=DEFAULT_URL, help="Moonraker URL")
    parser.add_argument("--dry-plan", action="store_true",
                        help="напечатать лестницу прогонов и выйти")
    parser.add_argument("--run", action="store_true", help="выполнить поиск")
    parser.add_argument("--apply", action="store_true",
                        help="записать TMC-модуль, max_velocity/max_accel и проверить deploy")
    parser.add_argument("--yes", action="store_true",
                        help="не спрашивать подтверждение оператора")
    parser.add_argument("--max-velocity", type=float, help="потолок поиска, мм/с")
    parser.add_argument("--max-accel", type=float, help="потолок поиска, мм/с²")
    parser.add_argument("--max-runs", type=int, default=10,
                        help="потолок прогонов TEST_SPEED (по умолчанию 10)")
    parser.add_argument("--iterations", type=int, default=2,
                        help="ITERATIONS одного TEST_SPEED (по умолчанию 2)")
    parser.add_argument("--cooldown", type=float, default=20.0,
                        help="пауза между прогонами, с (по умолчанию 20)")
    parser.add_argument("--run-timeout", type=float, default=300.0,
                        help="ожидание GET_POSITION одного прогона, с")
    parser.add_argument("--heat", action="store_true",
                        help="прогрев 150/110 C перед тестами")
    parser.add_argument("--offline-result", metavar="V,A",
                        help="тестовый режим: принять пару без принтера")
    parser.add_argument("--selftest", action="store_true",
                        help="офлайн-проверки парсинга, лестницы и патча")
    return parser


def confirm(args: argparse.Namespace) -> bool:
    if args.yes or args.offline_result:
        return True
    print(
        "ВНИМАНИЕ: принтер будет двигаться на предельных скоростях.\n"
        "Оператор должен стоять у E-stop. Продолжить? [y/N] ",
        end="", flush=True,
    )
    answer = sys.stdin.readline().strip().lower()
    return answer in ("y", "yes", "да", "д")


def apply_result(profile_dir: str, machine: dict[str, str],
                 best: tuple[float, float], settings: dict[str, object]) -> str:
    """Write the TMC module and machine-extras pair, then deploy --check."""
    module = module_path(machine)
    command = [
        sys.executable, TMC_CALC, "--update-module", module,
        "--vm", str(railway_values(machine)[0]),
        "--motor", motor_for_driver(machine),
        "--i-factor", "1.0", "--sections", "stepper_x,stepper_y", "--force",
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        raise TuneError(
            "tmc_calc.py --update-module failed: %s"
            % (proc.stderr or proc.stdout).strip()
        )
    extras = os.path.join(profile_dir, "machine-extras.cfg")
    try:
        with open(extras, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise TuneError("cannot read %s: %s" % (extras, exc))
    new_text, changed = patch_machine_extras(text, best[0], best[1])
    if changed:
        with open(extras + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_text)
        os.replace(extras + ".tmp", extras)
    check = subprocess.run(
        [DEPLOY, "-p", os.path.basename(profile_dir), "--check"],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        raise TuneError(
            "deploy_configs.sh --check failed:\n%s"
            % (check.stdout + check.stderr).strip()
        )
    return (
        "Применено: %s (run_current=%.3f A) и [printer] в %s; deploy --check ok"
        % (os.path.relpath(module, REPO_ROOT), float(settings["run_current"]),
           os.path.relpath(extras, REPO_ROOT))
    )


def run(args: argparse.Namespace) -> int:
    profile_dir = os.path.abspath(args.profile)
    if not os.path.isfile(os.path.join(profile_dir, "machine.conf")):
        raise TuneError("no machine.conf in %s" % profile_dir)
    machine = read_machine_conf(os.path.join(profile_dir, "machine.conf"))
    vm, driver_name, _family = railway_values(machine)
    ic = driver_of_module(driver_name)
    motor = motor_for_driver(machine)
    settings = tmc_calc_settings(motor, ic, vm)

    if args.offline_result:
        try:
            velocity, accel = (
                float(item) for item in args.offline_result.split(",")
            )
        except ValueError:
            raise TuneError("--offline-result expects V,A")
        log = [{"velocity": velocity, "accel": accel, "delta_x": 0,
                "delta_y": 0, "verdict": "pass"}]
        notes = ["офлайн-режим: принтер не опрашивался"]
        best = (velocity, accel)
        apply_note = None
        if args.apply:
            apply_note = apply_result(profile_dir, machine, best, settings)
        print(render_report(os.path.relpath(profile_dir, REPO_ROOT), best, log,
                            notes, settings, apply_note))
        return 0

    api = Moonraker(args.url)
    api.wait_ready(60)
    if api.print_state() not in ("idle", "standby", "complete", "cancelled"):
        raise TuneError("принтер занят (print_stats.state=%s)" % api.print_state())
    temps = api.temperatures()
    if not args.heat and (temps["extruder"] >= 40 or temps["heater_bed"] >= 40):
        raise TuneError(
            "нагреватели горячие (%.0f/%.0f C): остудите или используйте --heat"
            % (temps["extruder"], temps["heater_bed"])
        )
    config = api.config()
    printer_conf = config.get("printer", {})
    if printer_conf.get("kinematics") != "corexy":
        raise TuneError(
            "профиль не corexy (kinematics=%s): тест не поддерживается"
            % printer_conf.get("kinematics")
        )
    microsteps = int(float(config.get("stepper_x", {}).get("microsteps", 16)))
    baseline_velocity = printer_conf.get("max_velocity")

    if not confirm(args):
        print("Отменено оператором.")
        return 1
    warnings: list[str] = []
    applier = Applier(api, config, warnings.append)
    best = (0.0, 0.0)
    log: list[dict[str, object]] = []
    notes: list[str] = []
    applied = False
    try:
        if args.heat:
            api.gcode("M104 S150")
            api.gcode("M140 S110")
            deadline = time.time() + 900
            while time.time() < deadline:
                temps = api.temperatures()
                if temps["extruder"] >= 145 and temps["heater_bed"] >= 105:
                    break
                time.sleep(3)
            else:
                raise TuneError("нагрев до 150/110 C не завершился за 15 мин")
        applier.apply(settings)
        applied = True
        best, log, notes = search(api, args, microsteps, printer_conf)
        # Smoke test at the winning pair, then the kinematics sweep.
        smoke = run_test(api, best[0], best[1], 3, args.heat,
                         args.run_timeout, microsteps)
        log.append(smoke)
        if smoke["verdict"] != "pass":
            notes.append("дымовой прогон не прошёл: рекомендация требует запаса")
        if gcode_macro_exists(config, "TEST_KINEMATICS"):
            marker = "TMC_TUNE_KINEMATICS_DONE"
            cursor = api.store_since(None)[1]
            api.gcode('TEST_KINEMATICS\nRESPOND MSG="%s"' % marker,
                      timeout=args.run_timeout)
            wait_for_marker(api, cursor, marker, args.run_timeout)
            notes.append("TEST_KINEMATICS выполнен на подобранной паре")
        else:
            notes.append("TEST_KINEMATICS отсутствует в конфиге: пропущен")
        marker = "TMC_TUNE_QUERY_DONE"
        cursor = api.store_since(None)[1]
        script = "\n".join(
            ["QUERY_TMC STEPPER=%s" % stepper for stepper in STEPPERS]
            + ['RESPOND MSG="%s"' % marker]
        )
        api.gcode(script)
        entries = wait_for_marker(api, cursor, marker, 60)
        for entry in entries:
            message = str(entry.get("message", ""))
            if message.startswith("//") and any(
                token in message for token in ("Run Current", "run_current",
                                               "TMC", "tmc")
            ):
                notes.append("TMC: %s" % message[2:].strip())
    except (MoonrakerError, TuneError):
        raise
    finally:
        if applied:
            applier.restore()
        if args.heat:
            try:
                api.gcode("M104 S0")
                api.gcode("M140 S0")
                api.gcode("M107")
            except MoonrakerError as exc:
                warnings.append("cool down: %s" % exc)

    apply_note = None
    if args.apply:
        apply_note = apply_result(profile_dir, machine, best, settings)
    report = render_report(
        os.path.relpath(profile_dir, REPO_ROOT), best, log,
        notes + warnings, settings, apply_note,
    )
    print(report)
    previous = float(baseline_velocity or 0)
    if previous and best[0] < previous:
        print(
            "ВНИМАНИЕ: подобранная скорость ниже текущей конфигурации; "
            "решение за владельцем.", file=sys.stderr
        )
    return 0


def selftest() -> int:
    import doctest
    import tempfile

    failures = doctest.testmod(
        sys.modules[__name__], verbose=False, optionflags=doctest.ELLIPSIS
    )
    print("doctest: %d failed, %d run" % (failures.failed, failures.attempted))
    bad = failures.failed
    ladder = plan_ladder(700, 10000, 1400, 20000, 10)
    if ladder[0] != (700, 10000) or ladder[-1] != (1400, 20000):
        bad += 1
        print("MISMATCH: ladder endpoints %r" % (ladder,))
    with tempfile.TemporaryDirectory() as temp:
        profile = os.path.join(temp, "machine-extras.cfg")
        with open(profile, "w", encoding="utf-8") as fh:
            fh.write("[idle_timeout]\ntimeout: 60\n")
        first, changed = patch_machine_extras(
            open(profile, encoding="utf-8").read(), 800, 12000)
        second, changed_again = patch_machine_extras(first, 800, 12000)
        if not changed or changed_again or first != second:
            bad += 1
            print("MISMATCH: machine-extras patch is not idempotent")
    print("tmc_tune selftest: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.selftest:
        return selftest()
    if not args.profile:
        print("ERROR: --profile is required", file=sys.stderr)
        return 2
    if not (args.dry_plan or args.run or args.offline_result):
        print("ERROR: choose --dry-plan or --run", file=sys.stderr)
        return 2
    try:
        if args.dry_plan:
            machine = read_machine_conf(
                os.path.join(os.path.abspath(args.profile), "machine.conf"))
            vm, driver_name, _family = railway_values(machine)
            motor = motor_for_driver(machine)
            settings = tmc_calc_settings(motor, driver_of_module(driver_name), vm)
            velocity, accel = effective_limits(
                os.path.abspath(args.profile), machine.get("model", "trident"))
            points = plan_ladder(velocity, accel, args.max_velocity,
                                 args.max_accel, args.max_runs)
            print("План для %s: vm_xy=%d, %s (%s), %.3f A RMS"
                  % (args.profile, vm, driver_name, motor,
                     float(settings["run_current"])))
            for index, (speed, accel_value) in enumerate(points, 1):
                print("  %2d. %6.0f мм/с  %7.0f мм/с²" % (index, speed, accel_value))
            print("Потолок: %d прогонов, ITERATIONS=%d, cooldown=%.0f s"
                  % (args.max_runs, args.iterations, args.cooldown))
            return 0
        return run(args)
    except TuneError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2
    except MoonrakerError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())