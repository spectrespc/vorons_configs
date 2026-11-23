#!/usr/bin/env python3
"""Pick TMC2209/TMC5160 Klipper settings for a stepper motor.

The chopper formulas are transcribed from the vendor calculation sheets kept in
``docs/tmc/`` (TMC2209_Calculations.xlsx, TMC5160_Calculations.xlsx) and
documented cell by cell in ``docs/tmc/CALCS.md``.  The current registers are
reproduced from Klipper itself (klippy/extras/tmc2130.py, tmc5160.py) so the
printed CS/IRUN values match what the firmware will program from
``run_current``.  Nothing is guessed: every emitted ``driver_*`` key is in
``DRIVER_KEYS`` and was checked against the installed Klipper sources.

Usage:
  tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24
  tmc_calc.py --driver tmc2209 --i-rated 1.7 --l-mh 2.8 --r-ohm 1.5 --vm 24 \\
              --section stepper_z --section stepper_z1
  tmc_calc.py --driver tmc2209 --motor MOONS-CSE14HRA1L410A-01 --vm 24 \\
              --run-current 0.55 --tbl 0 --toff 3
  tmc_calc.py --driver tmc5160 --motor LDO-42STH48-2804AH-R --vm 48 --json
  tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24 --mode stealthchop
  tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24 --sgt -10 --json
  tmc_calc.py --list-motors
  tmc_calc.py --selftest

Exit status: 2 on input/validation errors (unknown motor, current or voltage
outside the driver limits, unsafe --write path), 1 when --selftest fails.

Known limits of this tool:
* StealthChop PWM_OFS/PWM_GRAD are *not* calculated: the approximate formulas
  live in the datasheet as rendered equations, not in the saved spreadsheets,
  and the project rule is "formulas only from CALCS.md".  The generated module
  therefore keeps StealthChop2 automatic tuning (PWM_AUTOSCALE/PWM_AUTOGRAD,
  the Klipper defaults) and accepts measured PWM_AUTO values via --pwm-ofs /
  --pwm-grad.
* StallGuard thresholds are calibrated on the live printer; --sgt only writes
  the value you measured with SET_TMC_FIELD.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import subprocess
import sys

# --- Vendor constants ----------------------------------------------------

# fCLK of both ICs with the internal oscillator (xlsx "Chopper Parameters" C9).
TMC_FREQUENCY = 12_000_000.0
TCLK = 1.0 / TMC_FREQUENCY

# Sense voltage / reference voltage constants.
VREF_2209_VSENSE0 = 0.32   # Klipper tmc2130.py _calc_current_bits, vsense=0
VREF_2209_VSENSE1 = 0.18   # Klipper tmc2130.py _calc_current_bits, vsense=1
RSENSE_OFFSET_2209 = 0.020  # Klipper adds 20 mOhm of internal routing
VREF_5160 = 0.325          # Klipper tmc5160.py VREF

DEFAULT_RSENSE = {"tmc2209": 0.110, "tmc5160": 0.075}
# Datasheet supply ranges; the upper 2209 value is the absolute limit, the
# fleet runs 24 V where the lower warning threshold matters.
VM_RANGE = {"tmc2209": (4.75, 29.0), "tmc5160": (8.0, 60.0)}
VM_WARN_HIGH = {"tmc2209": 28.0, "tmc5160": 56.0}
# Klipper sanity caps on run_current (tmc2130.py MAX_CURRENT, tmc5160.py).
KLIPPER_MAX_CURRENT = {"tmc2209": 2.000, "tmc5160": 10.000}

# Register defaults of the installed Klipper (klippy/extras/tmc2209.py,
# tmc5160.py).  Keys equal to these are not printed.
KLIPPER_DEFAULTS = {
    "tmc2209": {
        "toff": 3, "tbl": 2, "hstrt": 5, "hend": 0,
        "iholddelay": 8, "tpowerdown": 20,
    },
    "tmc5160": {
        "toff": 3, "tbl": 2, "hstrt": 5, "hend": 2,
        "iholddelay": 6, "tpowerdown": 10,
    },
}

# Every key here is read from the config by set_config_field() in the
# installed Klipper (tmc2208.py for tmc2209, tmc5160.py for tmc5160).
DRIVER_KEYS = {
    "tmc2209": frozenset(
        "MULTISTEP_FILT TOFF HSTRT HEND TBL SEMIN SEUP SEMAX SEDN SEIMIN "
        "IHOLDDELAY PWM_OFS PWM_GRAD PWM_FREQ PWM_AUTOSCALE PWM_AUTOGRAD "
        "FREEWHEEL PWM_REG PWM_LIM TPOWERDOWN SGTHRS".split()
    ),
    "tmc5160": frozenset(
        "MULTISTEP_FILT TOFF HSTRT HEND FD3 DISFDCC CHM TBL VHIGHFS VHIGHCHM "
        "TPFD DISS2G DISS2VS SEMIN SEUP SEMAX SEDN SEIMIN SGT SFILT "
        "DRVSTRENGTH BBMCLKS BBMTIME FILT_ISENSE IHOLDDELAY PWM_OFS PWM_GRAD "
        "PWM_FREQ PWM_AUTOSCALE PWM_AUTOGRAD FREEWHEEL PWM_REG PWM_LIM "
        "TPOWERDOWN".split()
    ),
}

DRIVER_LABELS = {"tmc2209": "TMC2209", "tmc5160": "TMC5160"}

# TBL blank-time formulas, seconds (xlsx C13 on both Chopper sheets).
SQRT2 = math.sqrt(2.0)

TBL_CHOICES = {
    "tmc2209": (0, 1, 2, 3),
    "tmc5160": (0, 1, 2, 3),
}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMC_MODULE_DIR = os.path.join("std.configs", "mechanics", "tmc")
MOTORS_DB = os.path.join("docs", "tmc", "motors.json")


class CalcError(Exception):
    """Invalid input; reported on stderr with exit status 2."""


# --- Motor current registers (Klipper compatible) ------------------------


def current_2209(run_current: float, rsense: float) -> dict[str, float]:
    """Reproduce Klipper's TMCCurrentHelper for TMC2209.

    >>> r = current_2209(0.8, 0.110)
    >>> int(r["vsense"]), int(r["cs"])
    (1, 25)
    >>> round(r["i_rms_actual"], 4)
    0.7955
    """
    rs = rsense + RSENSE_OFFSET_2209
    # Klipper tries VSENSE=1 first and falls back to VSENSE=0 only when the
    # low-sensitivity range cannot reach the requested current.
    vsense = 1
    cs = int(32.0 * rs * run_current * math.sqrt(2.0) / VREF_2209_VSENSE1 + 0.5) - 1
    cs = max(0, min(31, cs))
    if cs == 31:
        cur_high = current_bits_to_rms_2209(31, 1, rsense)
        if cur_high < run_current:
            cs_low = int(32.0 * rs * run_current * math.sqrt(2.0) / VREF_2209_VSENSE0 + 0.5) - 1
            cs_low = max(0, min(31, cs_low))
            cur_low = current_bits_to_rms_2209(cs_low, 0, rsense)
            if abs(run_current - cur_low) < abs(run_current - cur_high):
                vsense, cs = 0, cs_low
    return {
        "cs": float(cs),
        "vsense": float(vsense),
        "i_rms_actual": current_bits_to_rms_2209(cs, vsense, rsense),
        "i_peak_actual": current_bits_to_peak_2209(cs, vsense, rsense),
    }


def current_bits_to_peak_2209(cs: int, vsense: int, rsense: float) -> float:
    """Peak coil current for a CS/vsense pair (Klipper _calc_current_from_bits).

    >>> round(current_bits_to_peak_2209(31, 1, 0.110), 4)
    1.3846
    """
    vref = VREF_2209_VSENSE1 if vsense else VREF_2209_VSENSE0
    return (cs + 1) * vref / (32.0 * (rsense + RSENSE_OFFSET_2209))


def current_bits_to_rms_2209(cs: int, vsense: int, rsense: float) -> float:
    """RMS coil current for a CS/vsense pair.

    >>> round(current_bits_to_rms_2209(25, 1, 0.110), 4)
    0.7955
    """
    return current_bits_to_peak_2209(cs, vsense, rsense) / math.sqrt(2.0)


def current_5160(run_current: float, rsense: float) -> dict[str, float]:
    """Reproduce Klipper's TMC5160CurrentHelper.

    >>> r = current_5160(1.697, 0.075)
    >>> int(r["globalscaler"]), int(r["irun"])
    (142, 31)
    >>> round(r["i_rms_actual"], 3)
    1.7
    """
    gscaler = int((run_current * 256.0 * math.sqrt(2.0) * rsense / VREF_5160) + 0.5)
    gscaler = max(32, gscaler)
    if gscaler >= 256:
        gscaler = 0  # 0 means "256" in the register
    gs = gscaler or 256
    irun = int(
        (run_current * 256.0 * 32.0 * math.sqrt(2.0) * rsense) / (gs * VREF_5160)
        - 1.0 + 0.5
    )
    irun = max(0, min(31, irun))
    i_rms = gs * (irun + 1) * VREF_5160 / (256.0 * 32.0 * math.sqrt(2.0) * rsense)
    return {
        "globalscaler": float(gscaler),
        "irun": float(irun),
        "i_rms_actual": i_rms,
        "i_peak_actual": i_rms * math.sqrt(2.0),
    }


def ic_current_limit_rms(driver: str, rsense: float) -> float:
    """Highest RMS current the IC can regulate with this sense resistor.

    >>> round(ic_current_limit_rms("tmc2209", 0.110), 3)
    1.741
    >>> round(ic_current_limit_rms("tmc5160", 0.075), 3)
    3.064
    """
    if driver == "tmc2209":
        # VSENSE=0 is the only range that reaches >1.4 A with a 0.110 resistor.
        limit = VREF_2209_VSENSE0 / ((rsense + RSENSE_OFFSET_2209) * math.sqrt(2.0))
    else:
        limit = VREF_5160 / (rsense * math.sqrt(2.0))
    return min(limit, KLIPPER_MAX_CURRENT[driver])


# --- Chopper (SpreadCycle) ----------------------------------------------


def tblank(driver: str, tbl: int) -> float:
    """Blank time in seconds (xlsx C13).

    TMC2209: tCLK * (16 + 8*TBL); TMC5160: tCLK * 16 * 1.5^TBL.

    >>> round(tblank("tmc2209", 2) * 1e6, 4)
    2.6667
    >>> round(tblank("tmc5160", 2) * 1e6, 4)
    3.0
    >>> round(tblank("tmc5160", 0) * 1e6, 4)
    1.3333
    """
    if driver == "tmc2209":
        return TCLK * (16 + 8 * tbl)
    return TCLK * 16 * (1.5 ** tbl)


def slow_decay_time(driver: str, toff: int) -> float:
    """Duration of one slow-decay phase (xlsx C21).

    TMC2209: tCLK * (24 + 32*TOFF); TMC5160: tCLK * (12 + 32*TOFF).

    >>> round(slow_decay_time("tmc2209", 3) * 1e6, 4)
    10.0
    >>> round(slow_decay_time("tmc5160", 4) * 1e6, 4)
    11.6667
    """
    if driver == "tmc2209":
        return TCLK * (24 + 32 * toff)
    return TCLK * (12 + 32 * toff)


def chopper(
    driver: str,
    vm: float,
    inductance_h: float,
    resistance_ohm: float,
    i_peak: float,
    cs: int,
    tbl: int,
    toff: int,
) -> dict[str, float]:
    """SpreadCycle hysteresis values, straight from the xlsx Chopper sheet.

    The TMC2209 sheet counts the 200 ns bridge dead time (C23) on top of the
    blank and slow-decay drops; the TMC5160 sheet does not.

    >>> c = chopper("tmc2209", 24, 7.5e-3, 4.5, 1.414, 31, 2, 3)
    >>> round(c["hystart_min"], 4)
    1.6698
    >>> c["hstrt"], c["hend"]
    (0, 3)
    >>> round(c["fchop_limit_khz"], 2)
    39.47

    >>> c = chopper("tmc5160", 36, 7.5e-3, 4.5, 2.0, 31, 2, 4)
    >>> round(c["hystart_min"], 4)
    3.0152
    >>> c["hstrt"], c["hend"]
    (2, 3)
    >>> round(c["fchop_limit_khz"], 2)
    34.09
    """
    tb = tblank(driver, tbl)
    tsd = slow_decay_time(driver, toff)
    d_blank = vm * tb / inductance_h
    d_sd = resistance_ohm * i_peak * 2.0 * tsd / inductance_h
    if driver == "tmc2209":
        d_bbm = vm * 200e-9 / inductance_h
        hyst = 0.5 + (d_bbm + d_blank + d_sd) * 2.0 * 248.0 * (cs + 1) / i_peak / 32.0 - 8.0
    else:
        hyst = 0.5 + (d_blank + d_sd) * 2.0 * 248.0 * (cs + 1) / i_peak / 32.0 - 8.0
    hyst = max(hyst, -2.0)
    hstrt_desired = max(min(hyst, 8.0), 1.0)
    hstrt = int(math.floor(hstrt_desired - 1.0))   # xlsx F32 = C32 - 1
    hstrt = max(0, min(7, hstrt))
    hend_desired = min(hyst - hstrt_desired, 12.0)
    hend = int(math.floor(hend_desired + 3.0))     # xlsx F33 = C33 + 3
    hend = max(0, min(15, hend))
    fchop = 1.0 / (2.0 * tsd + 2.0 * tb) / 1000.0
    return {
        "tblank_us": tb * 1e6,
        "tsd_us": tsd * 1e6,
        "hystart_min": hyst,
        "hstrt": hstrt,
        "hend": hend,
        "fchop_limit_khz": fchop,
    }


def motor_voltage_window(resistance_ohm: float, i_peak: float) -> tuple[float, float]:
    """Nominal motor voltage and the xlsx supply-voltage window.

    >>> round(motor_voltage_window(4.5, 1.414)[0], 4)
    4.4993
    >>> [round(v, 2) for v in motor_voltage_window(4.5, 1.414)[1:]]
    [9.0, 89.99]
    """
    nominal = resistance_ohm * i_peak / math.sqrt(2.0)
    return nominal, 2.0 * nominal, 20.0 * nominal


def sense_resistor_for(driver: str, cs: int, i_peak: float) -> dict[str, float]:
    """Rsense that matches a given CS (xlsx C46/C47, informational).

    >>> round(sense_resistor_for("tmc2209", 31, 1.414)["vsense0"], 4)
    0.2063
    >>> round(sense_resistor_for("tmc2209", 31, 1.414)["vsense1"], 4)
    0.1073
    >>> round(sense_resistor_for("tmc5160", 31, 2.0)["vsense0"], 4)
    0.16
    """
    if driver == "tmc2209":
        return {
            "vsense0": (cs + 1) / 32.0 / i_peak * VREF_2209_VSENSE0 - RSENSE_OFFSET_2209,
            "vsense1": (cs + 1) / 32.0 / i_peak * VREF_2209_VSENSE1 - RSENSE_OFFSET_2209,
        }
    return {"vsense0": (cs + 1) / 32.0 / i_peak * VREF_2209_VSENSE0}


# --- XLSX cross-check vectors -------------------------------------------

# Inputs are the values stored in the shipped spreadsheets; expected results
# are the cached values Excel left in the files.
XLSX_VECTORS = (
    {
        "name": "TMC2209 Chopper sheet (fCLK=12, VM=24, L=7.5mH, R=4.5, Ipeak=1.414, TBL=2, TOFF=3, CS=31)",
        "driver": "tmc2209",
        "vm": 24.0, "inductance_h": 7.5e-3, "resistance_ohm": 4.5,
        "i_peak": 1.414, "cs": 31, "tbl": 2, "toff": 3,
        "expect": {
            "tblank_us": 2.6667, "tsd_us": 10.0, "hystart_min": 1.6698,
            "fchop_limit_khz": 39.47,
        },
        "expect_regs": {"hstrt": 0, "hend": 3},
    },
    {
        "name": "TMC5160 Chopper sheet (fCLK=12, VM=36, L=7.5mH, R=4.5, Ipeak=2.0, TBL=2, TOFF=4, CS=31)",
        "driver": "tmc5160",
        "vm": 36.0, "inductance_h": 7.5e-3, "resistance_ohm": 4.5,
        "i_peak": 2.0, "cs": 31, "tbl": 2, "toff": 4,
        "expect": {
            "tblank_us": 3.0, "tsd_us": 11.6667, "hystart_min": 3.0152,
            "fchop_limit_khz": 34.09,
        },
        "expect_regs": {"hstrt": 2, "hend": 3},
    },
)


def selftest() -> int:
    """Compare the implementation with the spreadsheet results."""
    import doctest

    failures = doctest.testmod(
        sys.modules[__name__], verbose=False, optionflags=doctest.ELLIPSIS
    )
    print("doctest: %d failed, %d run" % (failures.failed, failures.attempted))
    bad = failures.failed
    for vector in XLSX_VECTORS:
        got = chopper(
            vector["driver"], vector["vm"], vector["inductance_h"],
            vector["resistance_ohm"], vector["i_peak"], vector["cs"],
            vector["tbl"], vector["toff"],
        )
        print(vector["name"])
        for key, want in vector["expect"].items():
            value = got[key]
            ok = abs(value - want) <= max(abs(want) * 0.002, 0.01)
            print("  %-18s got %-10.4f xlsx %-10.4f %s"
                  % (key, value, want, "ok" if ok else "MISMATCH"))
            bad += 0 if ok else 1
        for key, want in vector["expect_regs"].items():
            value = got[key]
            ok = abs(value - want) <= 1  # one LSB covers Excel rounding
            print("  %-18s got %-10d xlsx %-10d %s"
                  % (key, value, want, "ok" if ok else "MISMATCH"))
            bad += 0 if ok else 1
    print("selftest: %s" % ("FAILED" if bad else "ok"))
    update_failures = selftest_update()
    return 1 if (bad or update_failures) else 0


def selftest_update() -> int:
    """Offline checks for --update-module on in-memory fixtures."""
    bad = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal bad
        print("  %-46s %s%s" % (label, "ok" if ok else "MISMATCH",
                                "" if ok else "  " + detail))
        bad += 0 if ok else 1

    motors = load_motors(os.path.join(REPO_ROOT, MOTORS_DB))
    fixture = (
        "## historical comment: 17HS19-2004S1\n"
        "[tmc2209 stepper_z]\n"
        "uart_pin: UART_2\n"
        "interpolate: False\n"
        "run_current: 0.600\n"
        "#run_current: 0.7\n"
        "stealthchop_threshold: 999999\n"
        "driver_TBL: 0\n"
        "driver_XYZ: 3\n"
        "\n"
        "[tmc2209 stepper_z1]\n"
        "uart_pin: UART_3\n"
        "run_current: 0.600\n"
        "sense_resistor: 0.110\n"
    )
    args = build_parser().parse_args(
        ["--vm", "24", "--motor", "17HS4401S", "--i-factor", "1.0",
         "--update-module", "fixture.cfg"]
    )
    first, report = update_module_text(fixture, args, motors)
    second, report2 = update_module_text(first, args, motors)
    check("idempotent on a second run", first == second)
    check("commented alternative preserved", "#run_current: 0.7" in first)
    check("uart_pin preserved", "uart_pin: UART_2" in first)
    check("stealthchop kept per section", "stealthchop_threshold: 999999" in first)
    check("hand-set driver_TBL preserved in StealthChop", "driver_TBL: 0" in first)
    check("unknown driver key preserved", "driver_XYZ: 3" in first)
    check("unknown driver key warned",
          any("driver_xyz" in item for item in report["warnings"]))
    check("nominal run_current written", "run_current: 1.7" in first)
    check("hold_current not added",
          "hold_current" not in first)
    check("requested sections only",
          len(report["sections"]) == 2 and len(report2["sections"]) == 2)
    check("header appears once", first.count(UPDATE_BEGIN) == 1)

    spreadcycle = (
        "[tmc2209 stepper_z]\n"
        "uart_pin: UART_2\n"
        "run_current: 0.6\n"
        "\n"
        "# trailing note\n"
    )
    third, _ = update_module_text(spreadcycle, args, motors)
    check("spreadcycle adds chopper keys", "driver_TBL: 0" in third)
    check("option order kept",
          third.index("uart_pin: ") < third.index("run_current: ")
          < third.index("driver_TBL: "))
    check("tail comment kept", "# trailing note" in third)

    requested_args = build_parser().parse_args(
        ["--driver", "tmc2209", "--vm", "24",
         "--motor", "MOONS-CSE14HRA1L410A-01", "--mode", "spreadcycle",
         "--run-current", "0.55", "--tbl", "0", "--toff", "3"]
    )
    requested = calculate(requested_args, motors)
    check("--run-current sets run_current", requested["run_current"] == 0.55,
          str(requested["run_current"]))
    check("--run-current derives i_factor",
          abs(float(requested["i_factor_effective"]) - 0.55) < 1e-9,
          str(requested["i_factor_effective"]))

    zero_args = build_parser().parse_args(
        ["--driver", "tmc2209", "--vm", "24", "--i-rated", "0",
         "--l-mh", "2.8", "--r-ohm", "1.5", "--run-current", "0.55"]
    )
    try:
        calculate(zero_args, motors)
        check("zero rated current refused", False, "no exception")
    except CalcError as exc:
        check("zero rated current refused", "positive" in str(exc), str(exc))

    peak_args = build_parser().parse_args(
        ["--driver", "tmc2209", "--vm", "24", "--motor", "17HS4401S",
         "--mode", "spreadcycle", "--current-basis", "peak",
         "--i-factor", "1.0", "--tbl", "0", "--toff", "3"]
    )
    peak = calculate(peak_args, motors)
    check("peak basis converts 1.7 A peak to 1.2021 A RMS",
          abs(float(peak["run_current"]) - 1.2021) < 1e-9,
          str(peak["run_current"]))
    check("peak basis reports the RMS rating",
          abs(float(peak["rated_current_rms"]) - 1.7 / SQRT2) < 1e-9,
          str(peak["rated_current_rms"]))

    held = (
        "[tmc2209 extruder]\n"
        "uart_pin: extruder:EXT_UART\n"
        "run_current: 0.55\n"
        "driver_TBL: 0\n"
        "driver_TOFF: 3\n"
    )
    held_args = build_parser().parse_args(
        ["--vm", "24", "--motor", "MOONS-CSE14HRA1L410A-01",
         "--run-current", "0.55", "--update-module", "fixture.cfg",
         "--sections", "extruder"]
    )
    sixth, held_report = update_module_text(held, held_args, motors)
    check("module TBL kept without --tbl", "driver_TBL: 0" in sixth)
    check("module TBL reported as module source",
          held_report["sections"][0]["tbl_source"] == "module",
          str(held_report["sections"][0]["tbl_source"]))
    explicit_args = build_parser().parse_args(
        ["--vm", "24", "--motor", "MOONS-CSE14HRA1L410A-01",
         "--run-current", "0.55", "--tbl", "1", "--toff", "3",
         "--update-module", "fixture.cfg", "--sections", "extruder"]
    )
    seventh, explicit_report = update_module_text(held, explicit_args, motors)
    check("explicit --tbl wins over the module",
          "driver_TBL: 1" in seventh
          and explicit_report["sections"][0]["tbl_source"] == "cli",
          str(explicit_report["sections"][0]["tbl_source"]))

    # The full-step switch is hand-set: high_velocity_threshold is not a
    # driver_* field (Klipper derives THIGH from it), so it must survive a
    # current recalculation untouched and must not be warned about.
    fullstep = (
        "[tmc5160 stepper_x]\n"
        "cs_pin: UART_0\n"
        "run_current: 1.9799\n"
        "stealthchop_threshold: 0\n"
        "high_velocity_threshold: 700\n"
        "driver_VHIGHFS: 1\n"
        "driver_VHIGHCHM: 1\n"
    )
    fullstep_args = build_parser().parse_args(
        ["--vm", "48", "--motor", "LDO-42STH48-2804AH-R", "--i-factor", "1.0",
         "--update-module", "fixture.cfg", "--sections", "stepper_x"]
    )
    eighth, fullstep_report = update_module_text(fullstep, fullstep_args, motors)
    check("high_velocity_threshold preserved",
          "high_velocity_threshold: 700" in eighth)
    check("driver_VHIGHFS/CHM preserved",
          "driver_VHIGHFS: 1" in eighth and "driver_VHIGHCHM: 1" in eighth)
    check("VHIGH keys not reported unknown",
          not any("vhigh" in item.lower()
                  for item in fullstep_report["warnings"]),
          str(fullstep_report["warnings"]))

    selective = build_parser().parse_args(
        ["--vm", "24", "--motor", "17HS4401S", "--i-factor", "1.0",
         "--update-module", "fixture.cfg", "--sections", "stepper_z1"]
    )
    fourth, report3 = update_module_text(fixture, selective, motors)
    check("--sections limits the update",
          [row["section"] for row in report3["sections"]] == ["[tmc2209 stepper_z1]"])
    check("unselected section untouched", "run_current: 0.600" in fourth)

    # Regression: a stanza followed by a non-TMC section must not absorb it.
    mixed = (
        "[tmc2209 extruder]\n"
        "uart_pin: extruder:EXT_UART\n"
        "run_current: 0.55\n"
        "\n"
        "[fan]\n"
        "pin: extruder:FAN1\n"
        "heater_temp: 50.0\n"
    )
    mixed_args = build_parser().parse_args(
        ["--vm", "24", "--motor", "17HS4401S", "--i-factor", "1.0",
         "--update-module", "fixture.cfg", "--sections", "extruder"]
    )
    fifth, _ = update_module_text(mixed, mixed_args, motors)
    fan_block = fifth.index("[fan]")
    check("added keys stay inside the tmc stanza",
          "stealthchop_threshold: 0" in fifth
          and fifth.index("stealthchop_threshold: 0") < fan_block)
    check("non-TMC section untouched", "heater_temp: 50.0" in fifth)

    print("update-module selftest: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


# --- Motor database ------------------------------------------------------


# Reserved key: maps a driver-module stem (xy-tmc5160-..., 3z-tmc2109-...,
# lower case, prefix stripped) to a motor of this database.  It is data, not a
# motor, so load_motors() validates it separately.
MODULE_MOTOR_KEY = "motor_by_module"


def load_motors(path: str) -> dict[str, dict[str, object]]:
    if not os.path.isfile(path):
        raise CalcError("motor database not found: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CalcError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise CalcError("%s must hold a JSON object" % path)
    module_map = data.pop(MODULE_MOTOR_KEY, {})
    if not isinstance(module_map, dict):
        raise CalcError("%s: %r must be an object" % (path, MODULE_MOTOR_KEY))
    for module, motor in module_map.items():
        if not isinstance(motor, str) or motor not in data:
            raise CalcError(
                "%s: %r maps to unknown motor %r"
                % (path, module, motor)
            )
    for name, entry in data.items():
        if not isinstance(entry, dict):
            raise CalcError("%s: %r must be an object" % (path, name))
        for key in ("rated_current_a", "inductance_mh", "resistance_ohm", "source"):
            if key not in entry:
                raise CalcError("%s: %r is missing %s" % (path, name, key))
        for key in ("rated_current_a", "inductance_mh", "resistance_ohm"):
            try:
                value = float(entry[key])
            except (TypeError, ValueError):
                raise CalcError("%s: %r has a non-numeric %s" % (path, name, key))
            if value <= 0:
                raise CalcError("%s: %r has a non-positive %s" % (path, name, key))
        if not str(entry["source"]).strip():
            raise CalcError("%s: %r needs a datasheet source" % (path, name))
    return data


def load_module_map(path: str) -> dict[str, str]:
    """Read only the motor_by_module table (module stem -> motor name).

    >>> import tempfile, json as _json
    >>> handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    >>> _ = handle.write(_json.dumps({"motor_by_module": {"tmc2109-17hs4401s": "17HS4401S"}}))
    >>> handle.close()
    >>> load_module_map(handle.name)
    {'tmc2109-17hs4401s': '17HS4401S'}
    >>> os.unlink(handle.name)
    """
    if not os.path.isfile(path):
        raise CalcError("motor database not found: %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CalcError("cannot read %s: %s" % (path, exc))
    module_map = data.get(MODULE_MOTOR_KEY, {}) if isinstance(data, dict) else {}
    if not isinstance(module_map, dict):
        raise CalcError("%s: %r must be an object" % (path, MODULE_MOTOR_KEY))
    return {str(module): str(motor) for module, motor in module_map.items()}


def motor_module_name(motor: str) -> str:
    """Conventional file stem for a motor: keep the vendor casing.

    >>> motor_module_name("LDO-42STH48-2804AH-R")
    'LDO-42STH48-2804AH-R'
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", motor).strip("-")


# --- Calculation ---------------------------------------------------------


def resolve_request_current(
    driver: str, i_rated: float, i_factor: float, run_current: float | None
) -> tuple[float, float]:
    """Requested run current and the effective share of the rated current.

    ``--run-current`` is the authoritative input when given: the factor is
    derived from it (and printed in the report), so a 0.55 A request on a 1.0 A
    motor reads as i_factor_effective=0.55 instead of the CLI default.

    >>> resolve_request_current("tmc2209", 1.0, 0.8, 0.55)
    (0.55, 0.55)
    >>> resolve_request_current("tmc2209", 1.7, 0.8, None)
    (1.36, 0.8)
    >>> try:
    ...     resolve_request_current("tmc2209", 1.7, 1.0, 3.0)
    ... except CalcError as exc:
    ...     print(str(exc))
    run_current 3.000 A is above the Klipper limit 2.0 A
    """
    if run_current is not None:
        if not (0 < run_current <= KLIPPER_MAX_CURRENT[driver]):
            raise CalcError(
                "run_current %.3f A is above the Klipper limit %.1f A"
                % (run_current, KLIPPER_MAX_CURRENT[driver])
            )
        return run_current, round(run_current / i_rated, 6)
    if not (0 < i_factor <= 1.0):
        raise CalcError("--i-factor must be in (0, 1]")
    return i_rated * i_factor, i_factor


def resolve_table_input(
    value: int | None, source: str | None, default: int
) -> tuple[int, str]:
    """Resolve one TBL/TOFF input and where it came from.

    >>> resolve_table_input(None, None, 2)
    (2, 'cli')
    >>> resolve_table_input(0, "profile", 2)
    (0, 'profile')
    """
    if value is None:
        return default, "cli"
    return value, source or "cli"


def calculate(args: argparse.Namespace, motors: dict[str, dict[str, object]]) -> dict[str, object]:
    driver = args.driver
    warnings: list[str] = []
    notes: list[str] = []

    motor_name = None
    if args.motor:
        if args.motor not in motors:
            raise CalcError(
                "unknown motor %r (known: %s)"
                % (args.motor, ", ".join(sorted(motors)))
            )
        entry = motors[args.motor]
        motor_name = args.motor
        i_rated = float(entry["rated_current_a"])
        inductance_mh = float(entry["inductance_mh"])
        resistance_ohm = float(entry["resistance_ohm"])
        step_angle = entry.get("step_angle_deg")
        source = entry["source"]
    else:
        i_rated = args.i_rated
        inductance_mh = args.l_mh
        resistance_ohm = args.r_ohm
        step_angle = None
        source = "CLI arguments"

    if i_rated is None or inductance_mh is None or resistance_ohm is None:
        raise CalcError(
            "specify --motor NAME or all of --i-rated/--l-mh/--r-ohm"
        )
    if i_rated <= 0 or inductance_mh <= 0 or resistance_ohm <= 0:
        raise CalcError("--i-rated, --l-mh and --r-ohm must be positive")

    rsense = args.rsense if args.rsense is not None else DEFAULT_RSENSE[driver]
    low, high = VM_RANGE[driver]
    if not (low <= args.vm <= high):
        raise CalcError(
            "%s supports %.2f..%.0f V, got %.2f V"
            % (DRIVER_LABELS[driver], low, high, args.vm)
        )
    if args.vm > VM_WARN_HIGH[driver]:
        warnings.append(
            "%s above %.0f V: check the board capacitors and the motor insulation"
            % ("Supply voltage", VM_WARN_HIGH[driver])
        )

    basis = getattr(args, "current_basis", "rms")
    if basis not in ("rms", "peak"):
        raise CalcError("--current-basis must be rms or peak")
    # Klipper's run_current is RMS.  X/Y and Z datasheets quote the per-phase
    # peak current, so the rails pass --current-basis peak: rated RMS is
    # peak / sqrt(2) (0.707 x peak).  The extruders always run at a measured
    # RMS current and keep the default basis.
    i_rated_rms = i_rated / SQRT2 if basis == "peak" else i_rated

    ic_limit = ic_current_limit_rms(driver, rsense)
    if i_rated_rms > ic_limit + 1e-9:
        raise CalcError(
            "motor rated current %.2f A (%s) is above the %s limit of %.2f A "
            "RMS at Rsense=%.3f Ohm: use a smaller --rsense or a stronger driver"
            % (i_rated, basis, DRIVER_LABELS[driver], ic_limit, rsense)
        )
    requested, i_factor_effective = resolve_request_current(
        driver, i_rated_rms, args.i_factor, args.run_current
    )
    if args.run_current is not None and requested > ic_limit + 1e-9:
        raise CalcError(
            "run_current %.3f A is above the %s limit of %.3f A RMS at "
            "Rsense=%.3f Ohm"
            % (requested, DRIVER_LABELS[driver], ic_limit, rsense)
        )
    run_current = round(min(requested, ic_limit), 4)
    if requested > ic_limit + 1e-9:
        warnings.append(
            "rated current %.2f A RMS x %.2f = %.2f A exceeds the %s limit "
            "for Rsense=%.3f Ohm (%.2f A RMS): run_current clamped"
            % (i_rated_rms, i_factor_effective, requested,
               DRIVER_LABELS[driver], rsense, ic_limit)
        )
    if run_current > KLIPPER_MAX_CURRENT[driver]:
        raise CalcError(
            "run_current %.3f A is above the Klipper limit %.1f A"
            % (run_current, KLIPPER_MAX_CURRENT[driver])
        )

    tbl, tbl_source = resolve_table_input(args.tbl, args.tbl_source, 0)
    toff, toff_source = resolve_table_input(args.toff, args.toff_source, 3)

    if driver == "tmc2209":
        if tbl not in TBL_CHOICES["tmc2209"]:
            raise CalcError("TMC2209 supports --tbl 0..3")
        regs = current_2209(run_current, rsense)
        cs_for_chopper = int(regs["cs"])
    else:
        if tbl not in TBL_CHOICES["tmc5160"]:
            raise CalcError("TMC5160 supports --tbl 0..3")
        regs = current_5160(run_current, rsense)
        cs_for_chopper = int(regs["irun"])

    if toff < 1 or toff > 15:
        raise CalcError("--toff must be 1..15")
    if toff < 3:
        warnings.append("TOFF < 3 is below the vendor recommendation (3..8)")

    nominal_v, vm_lo, vm_hi = motor_voltage_window(resistance_ohm, regs["i_peak_actual"])
    # The xlsx window is a vendor rule of thumb (2x .. 20x the nominal motor
    # voltage).  It is reported as a note: the fleet deliberately runs 48 V on
    # low-inductance motors, where this rule is exceeded by design.
    if args.vm > vm_hi:
        notes.append(
            "%.1f V is above the motor-derived chopper window (%.1f..%.1f V): "
            "chopping losses and motor heating grow" % (args.vm, vm_lo, vm_hi)
        )
    elif args.vm < vm_lo:
        notes.append(
            "%.1f V is below the motor-derived window (%.1f..%.1f V): the driver "
            "may not reach the target current at speed" % (args.vm, vm_lo, vm_hi)
        )

    chopper_values = None
    if args.mode == "spreadcycle":
        chopper_values = chopper(
            driver, args.vm, inductance_mh / 1000.0, resistance_ohm,
            regs["i_peak_actual"], cs_for_chopper, tbl, toff,
        )
        if chopper_values["hystart_min"] > 20.0:
            warnings.append(
                "HystStart %.1f > 20: reduce TBL, the sense resistor or the "
                "supply voltage, or use a lower current" % chopper_values["hystart_min"]
            )
        elif chopper_values["hystart_min"] > 15.0:
            warnings.append(
                "HystStart %.1f > 15: keep CS <= 30 or start from a smaller value"
                % chopper_values["hystart_min"]
            )
        if chopper_values["fchop_limit_khz"] > 50.0:
            warnings.append(
                "chopper frequency limit %.1f kHz is high: raise hysteresis and "
                "measure the real frequency" % chopper_values["fchop_limit_khz"]
            )
        elif chopper_values["fchop_limit_khz"] < 20.0:
            warnings.append(
                "chopper frequency limit %.1f kHz is low and may become audible: "
                "increase TOFF" % chopper_values["fchop_limit_khz"]
            )
        if driver == "tmc2209" and int(regs["cs"]) < 16:
            notes.append(
                "CS=%d is small; values above 16 give better microstepping"
                % int(regs["cs"])
            )

    if args.mode == "stealthchop":
        threshold = 999999 if args.stealthchop_threshold is None else args.stealthchop_threshold
        notes.append(
            "StealthChop2 autotuning (PWM_AUTOSCALE/PWM_AUTOGRAD) derives "
            "PWM_OFS/PWM_GRAD at runtime; see docs/tmc/CALCS.md"
        )
    else:
        threshold = 0 if args.stealthchop_threshold is None else args.stealthchop_threshold

    hold_current = None
    if args.hold_frac > 0:
        hold_current = round(run_current * args.hold_frac, 4)

    if step_angle is not None and args.xy_step is not None:
        if abs(float(step_angle) - float(args.xy_step)) > 0.001:
            warnings.append(
                "motor step angle %s does not match profile xy_step=%s: the "
                "geometry module would be wrong" % (step_angle, args.xy_step)
            )

    if args.sgt == "auto":
        notes.append(
            "StallGuard start value: %s (calibrate with SET_TMC_FIELD on the "
            "printer, then pass --sgt N)"
            % ("SGTHRS 0..255, start around 60-90" if driver == "tmc2209"
               else "SGT -64..63, start around -10..0")
        )
    elif args.sgt is not None:
        try:
            sgt = int(args.sgt)
        except ValueError:
            raise CalcError("--sgt expects an integer or 'auto'")
        if driver == "tmc2209":
            if not (0 <= sgt <= 255):
                raise CalcError("TMC2209 SGTHRS is 0..255")
        else:
            if not (-64 <= sgt <= 63):
                raise CalcError("TMC5160 SGT is -64..63")

    return {
        "driver": driver,
        "mode": args.mode,
        "motor": motor_name,
        "motor_source": source,
        "vm": args.vm,
        "sense_resistor": rsense,
        "rated_current_a": i_rated,
        "rated_current_rms": i_rated_rms,
        "current_basis": basis,
        "step_angle": step_angle,
        "inductance_mh": inductance_mh,
        "resistance_ohm": resistance_ohm,
        "i_factor": i_factor_effective,
        "i_factor_effective": i_factor_effective,
        "run_current": run_current,
        "hold_current": hold_current,
        "stealthchop_threshold": threshold,
        "current_limit_rms": ic_limit,
        "registers": regs,
        "chopper": chopper_values,
        "motor_nominal_v": nominal_v,
        "vm_window": (vm_lo, vm_hi),
        "sense_suggestion": sense_resistor_for(driver, cs_for_chopper, regs["i_peak_actual"]),
        "tbl": tbl,
        "toff": toff,
        "tbl_source": tbl_source,
        "toff_source": toff_source,
        "section_names": list(args.section),
        "warnings": warnings,
        "notes": notes,
    }


# --- Stanza rendering ----------------------------------------------------


def section_pin(section: str, index: int) -> str:
    known = {
        "stepper_x": 0, "stepper_y": 1, "stepper_z": 2,
        "stepper_z1": 3, "stepper_z2": 4, "stepper_z3": 5,
    }
    return "UART_%d" % known.get(section, index)


def build_spi_lines(spi: str, prefix: str) -> list[str]:
    if spi == "software":
        return [
            "spi_software_sclk_pin: %s_SCLK" % prefix,
            "spi_software_mosi_pin: %s_MOSI" % prefix,
            "spi_software_miso_pin: %s_MISO" % prefix,
        ]
    return ["spi_bus: %s" % spi]


def driver_lines(result: dict[str, object], args: argparse.Namespace) -> list[tuple[str, str | None]]:
    """Return (key, comment) pairs for the driver_* section of one stanza."""
    driver = result["driver"]
    out: list[tuple[str, str | None]] = []
    defaults = KLIPPER_DEFAULTS[driver]

    chopper_values = result["chopper"]
    if chopper_values:
        # Chopper values are calculated, so they are always printed even when
        # they happen to equal the Klipper default: the module documents the
        # result of the spreadsheet run.
        for key in ("TBL", "TOFF", "HSTRT", "HEND"):
            out.append((key, None))
    if args.mode == "stealthchop":
        out.append(("PWM_AUTOSCALE", None))
        out.append(("PWM_AUTOGRAD", None))
        if args.pwm_ofs is not None:
            out.append(("PWM_OFS", "измерено в PWM_AUTO после автотюнинга"))
        if args.pwm_grad is not None:
            out.append(("PWM_GRAD", "измерено в PWM_AUTO после автотюнинга"))
    if args.iholddelay is not None and args.iholddelay != defaults["iholddelay"]:
        out.append(("IHOLDDELAY", "Klipper default: %d" % defaults["iholddelay"]))
    if args.tpowerdown is not None and args.tpowerdown != defaults["tpowerdown"]:
        out.append(("TPOWERDOWN", "Klipper default: %d" % defaults["tpowerdown"]))
    if args.sgt not in (None, "auto"):
        out.append(("SGTHRS" if driver == "tmc2209" else "SGT", "калибровано на принтере"))
    for key, _comment in out:
        if key not in DRIVER_KEYS[driver]:
            raise CalcError("internal error: %s is not a %s driver key" % (key, driver))
    return out


def render_sections(result: dict[str, object], args: argparse.Namespace) -> list[dict[str, object]]:
    driver = result["driver"]
    sections = []
    for index, name in enumerate(result["section_names"]):
        pin = args.pins[index] if args.pins else section_pin(name, index)
        lines: list[tuple[str, str | None]] = []
        lines.append(("interpolate", "false"))
        if driver == "tmc2209":
            lines.append(("uart_pin", "%s" % pin))
        else:
            lines.append(("cs_pin", "%s" % pin))
            if not args.no_diag:
                lines.append(("diag1_pin", "DIAG_%d" % index))
            for line in build_spi_lines(args.spi, args.spi_prefix):
                key, value = line.split(": ", 1)
                lines.append((key, value))
        lines.append(("sense_resistor", "%s" % _fmt(result["sense_resistor"])))
        lines.append(("run_current", "%s" % _fmt(result["run_current"])))
        if result["hold_current"] is not None:
            lines.append(("hold_current", "%s" % _fmt(result["hold_current"])))
        lines.append(("stealthchop_threshold", "%s" % result["stealthchop_threshold"]))
        for key, comment in driver_lines(result, args):
            if key in ("TBL", "TOFF", "HSTRT", "HEND"):
                value = str(
                    result["tbl"] if key == "TBL"
                    else result["toff"] if key == "TOFF"
                    else result["chopper"][key.lower()]
                )
            elif key == "PWM_AUTOSCALE":
                value = "true"
            elif key == "PWM_AUTOGRAD":
                value = "true"
            elif key == "PWM_OFS":
                value = str(args.pwm_ofs)
            elif key == "PWM_GRAD":
                value = str(args.pwm_grad)
            elif key == "IHOLDDELAY":
                value = str(args.iholddelay)
            elif key == "TPOWERDOWN":
                value = str(args.tpowerdown)
            elif key in ("SGTHRS", "SGT"):
                value = str(args.sgt)
            else:  # pragma: no cover - guarded by driver_lines
                raise CalcError("internal error: no value for %s" % key)
            lines.append(("driver_%s" % key, value if comment is None else "%s  # %s" % (value, comment)))
        sections.append({"name": name, "pin": pin, "lines": lines})
    return sections


def _fmt(value: object) -> str:
    if isinstance(value, float):
        text = "%.4f" % value
        return text.rstrip("0").rstrip(".")
    return str(value)


def render_text(result: dict[str, object], sections: list[dict[str, object]]) -> str:
    driver = result["driver"]
    motor = result["motor"] or "CLI parameters"
    out: list[str] = []
    out.append("# %s + %s, VM=%s V, Rsense=%s Ohm, режим %s"
               % (DRIVER_LABELS[driver], motor, _fmt(result["vm"]),
                  _fmt(result["sense_resistor"]), result["mode"]))
    if result.get("current_basis") == "peak":
        rating = ("номинал %s A peak = %s A RMS"
                  % (_fmt(result["rated_current_a"]),
                     _fmt(result["rated_current_rms"])))
    else:
        rating = "номинал %s A RMS" % _fmt(result["rated_current_a"])
    out.append("# run_current=%s A RMS (%s x %s, предел IC %s A)"
               % (_fmt(result["run_current"]), rating,
                  _fmt(result["i_factor"]), round(float(result["current_limit_rms"]), 3)))
    regs = result["registers"]
    if driver == "tmc2209":
        out.append("# сверка: CS=%d vsense=%d -> %.3f A RMS (Klipper считает сам)"
                   % (int(regs["cs"]), int(regs["vsense"]), regs["i_rms_actual"]))
    else:
        out.append("# сверка: GLOBALSCALER=%d IRUN=%d -> %.3f A RMS (Klipper считает сам)"
                   % (int(regs["globalscaler"]), int(regs["irun"]), regs["i_rms_actual"]))
    chopper_values = result["chopper"]
    if chopper_values:
        out.append("# chopper: TBL=%s (%s) TOFF=%s (%s) HSTRT=%d HEND=%d, "
                   "fCHOP(limit)=%.1f kHz"
                   % (result["tbl"], result["tbl_source"],
                      result["toff"], result["toff_source"],
                      chopper_values["hstrt"], chopper_values["hend"],
                      chopper_values["fchop_limit_khz"]))
    for section in sections:
        out.append("")
        out.append("[%s %s]" % (driver, section["name"]))
        for key, value in section["lines"]:
            out.append("%s: %s" % (key, value))
    if result["notes"]:
        out.append("")
        out.append("# Примечания:")
        for note in result["notes"]:
            out.append("# - %s" % note)
    if result["warnings"]:
        out.append("")
        out.append("# ВНИМАНИЕ:")
        for warning in result["warnings"]:
            out.append("# - %s" % warning)
    return "\n".join(out) + "\n"


# --- Updating an existing module ----------------------------------------

# Options this mode owns.  Everything else in the file (pins, SPI/UART
# transport, sense_resistor, diag pins, hand-written driver_* outside this set)
# is preserved verbatim, together with the option order.
MANAGED_KEYS = (
    "run_current",
    "hold_current",
    "stealthchop_threshold",
    "driver_tbl",
    "driver_toff",
    "driver_hstrt",
    "driver_hend",
)
CHOPPER_KEYS = ("driver_tbl", "driver_toff", "driver_hstrt", "driver_hend")
# Klipper option spelling for lines this mode adds (Klipper itself lower-cases
# every option, but the repository modules use the register names).
OPTION_SPELLING = {
    "driver_tbl": "driver_TBL",
    "driver_toff": "driver_TOFF",
    "driver_hstrt": "driver_HSTRT",
    "driver_hend": "driver_HEND",
}

UPDATE_BEGIN = "# >>> tmc_calc.py --update-module: расчёт (блок обновляется автоматически)"
UPDATE_END = "# <<< tmc_calc.py: конец блока расчёта"
SECTION_RE = re.compile(r"^\[(tmc2209|tmc5160)\s+([^\]]+?)\]\s*$")
ANY_SECTION_RE = re.compile(r"^\[[^\]]+\]\s*$")


def split_option(line: str) -> tuple[str, str, str] | None:
    """Split an active ``key: value  # comment`` line.

    Returns ``(key_lower, value, trailing)`` where ``trailing`` starts with the
    ``#`` of an inline comment (empty when there is none), or None for blank
    lines, comments and anything without a colon.

    >>> split_option("run_current: 0.600")
    ('run_current', '0.600', '')
    >>> split_option("driver_TBL: 0   # hand-set")
    ('driver_tbl', '0', '# hand-set')
    >>> split_option("#run_current: 1.768") is None
    True
    >>> split_option("") is None
    True
    """
    stripped = line.lstrip()
    if not stripped or stripped[0] in "#;" or ":" not in stripped:
        return None
    key, _, rest = stripped.partition(":")
    value, sep, comment = rest.partition("#")
    # The comment marker belongs to the trailing part: "+ sep + comment" keeps
    # the spacing the author used.
    return key.strip().lower(), value.strip(), (sep + comment if sep else "")


def rewrite_option(line: str, value: str) -> str:
    """Replace the value of an option line, keeping key, indent and comment.

    >>> rewrite_option("run_current: 0.600", "0.85")
    'run_current: 0.85'
    >>> rewrite_option("  driver_TBL: 2  # vendor", "0")
    '  driver_TBL: 0  # vendor'
    """
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    key, _, rest = stripped.partition(":")
    _old, sep, comment = rest.partition("#")
    space = rest[: len(rest) - len(rest.lstrip())] or " "
    tail = ("  # " + comment.strip()) if sep else ""
    return "%s%s:%s%s%s" % (indent, key, space, value, tail)


def same_number(left: str, right: str) -> bool:
    """True when two option values are the same number (keeps the spelling).

    >>> same_number("0.600", "0.6"), same_number("0.600", "1.7")
    (True, False)
    >>> same_number("0.110", "0.110"), same_number("x", "0")
    (True, False)
    """
    try:
        return abs(float(left) - float(right)) <= 1e-9
    except ValueError:
        return left == right


def section_blocks(lines: list[str]) -> list[dict[str, object]]:
    """Locate ``[tmc<ic> <stepper>]`` blocks.

    A block ends at the next section header of *any* type: a driver stanza in
    a file that also defines ``[fan]`` or ``[extruder]`` must not swallow those
    sections when options are appended.

    >>> text = ["[tmc2209 stepper_z]", "run_current: 0.6", "",
    ...         "[tmc5160 stepper_x]", "run_current: 1", "[fan]", "pin: X"]
    >>> [(b["driver"], b["name"], b["start"], b["end"]) for b in section_blocks(text)]
    [('tmc2209', 'stepper_z', 0, 3), ('tmc5160', 'stepper_x', 3, 5)]
    """
    headers = [
        index for index, line in enumerate(lines) if ANY_SECTION_RE.match(line.strip())
    ]
    blocks: list[dict[str, object]] = []
    for position, index in enumerate(headers):
        match = SECTION_RE.match(lines[index].strip())
        if not match:
            continue
        blocks.append(
            {
                "driver": match.group(1),
                "name": match.group(2).strip(),
                "start": index,
                "end": headers[position + 1] if position + 1 < len(headers) else len(lines),
            }
        )
    return blocks


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


def module_motor(module_stem: str, module_map: dict[str, str]) -> str | None:
    """Motor of a driver module (lower case, size prefix stripped).

    >>> module_motor("3z-tmc2109-17hs4401s", {"tmc2109-17hs4401s": "17HS4401S"})
    '17HS4401S'
    >>> module_motor("xy-tmc5160-LDO-42STH48-2804AH-R", {"tmc5160-ldo-42sth48-2804ah-r": "x"})
    'x'
    >>> module_motor("unknown", {}) is None
    True
    """
    stem = module_stem.lower()
    for prefix in ("xy-", "3z-", "4z-"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    return module_map.get(stem)


def _section_args(
    args: argparse.Namespace, driver: str, name: str, rsense: float | None, mode: str
) -> argparse.Namespace:
    """Copy of the CLI arguments targeted at one section."""
    clone = argparse.Namespace(**vars(args))
    clone.driver = driver
    clone.section = [name]
    clone.rsense = rsense
    clone.mode = mode
    clone.write = None
    clone.update_module = None
    clone.wire_profile = None
    clone.json = False
    clone.force = False
    return clone


def _target_values(result: dict[str, object]) -> dict[str, str]:
    """Option values this mode writes, in canonical order."""
    values = {"run_current": _fmt(result["run_current"])}
    if result["hold_current"] is not None:
        values["hold_current"] = _fmt(result["hold_current"])
    values["stealthchop_threshold"] = _fmt(result["stealthchop_threshold"])
    chopper_values = result["chopper"]
    if chopper_values:
        values["driver_tbl"] = str(result["tbl"])
        values["driver_toff"] = str(result["toff"])
        values["driver_hstrt"] = str(chopper_values["hstrt"])
        values["driver_hend"] = str(chopper_values["hend"])
    return values


def update_module_text(
    text: str,
    args: argparse.Namespace,
    motors: dict[str, dict[str, object]],
) -> tuple[str, dict[str, object]]:
    """Recompute the managed options of every targeted section.

    Returns the new file text and a report with one row per section.  The
    report is what --json prints and what the bringup stage logs.
    """
    lines = text.splitlines()
    blocks = section_blocks(lines)
    if not blocks:
        raise CalcError("no [tmc2209 ...] or [tmc5160 ...] section found")
    wanted_raw = args.sections
    if isinstance(wanted_raw, str):
        wanted_raw = wanted_raw.split(",")
    wanted = [item.strip().lower() for item in (wanted_raw or []) if item.strip()]
    targets = []
    for block in blocks:
        name = str(block["name"])
        if wanted and name.lower() not in wanted and name.lower().split()[-1] not in wanted:
            continue
        if args.driver and block["driver"] != args.driver:
            raise CalcError(
                "[%s %s] is a %s section, but --driver %s was requested"
                % (block["driver"], name, block["driver"], args.driver)
            )
        targets.append(block)
    if not targets:
        raise CalcError(
            "no matching section (found: %s)"
            % ", ".join(str(block["name"]) for block in blocks)
        )

    report: dict[str, object] = {
        "sections": [],
        "warnings": [],
        "notes": [],
        "changed": False,
    }
    rows: list[dict[str, object]] = []
    # Bottom-up: inserting options into one section must not shift the line
    # numbers of the sections above it.
    for block in reversed(targets):
        start, end = int(block["start"]), int(block["end"])
        body = lines[start + 1:end]
        active: dict[str, str] = {}
        for line in body:
            parsed = split_option(line)
            if parsed:
                active[parsed[0]] = parsed[1]
        driver = str(block["driver"])
        rsense = active.get("sense_resistor")
        section_rsense = float(rsense) if rsense else None
        if args.rsense is not None and section_rsense is not None:
            if abs(section_rsense - args.rsense) > 1e-9:
                raise CalcError(
                    "[%s %s] uses sense_resistor=%s but --rsense=%s was given"
                    % (driver, block["name"], rsense, _fmt(args.rsense))
                )
        mode = args.mode or section_mode(active.get("stealthchop_threshold"))
        section_args = _section_args(args, driver, str(block["name"]),
                                     args.rsense or section_rsense, mode)
        # Without an explicit CLI value the module keeps its own TBL/TOFF: the
        # chopper inputs are a machine property, not a CLI default.
        if section_args.tbl is None and "driver_tbl" in active:
            try:
                section_args.tbl = int(active["driver_tbl"])
                section_args.tbl_source = "module"
            except ValueError:
                pass
        if section_args.toff is None and "driver_toff" in active:
            try:
                section_args.toff = int(active["driver_toff"])
                section_args.toff_source = "module"
            except ValueError:
                pass
        result = calculate(section_args, motors)
        values = _target_values(result)
        for warning in result["warnings"]:
            report["warnings"].append(
                "[%s %s] %s" % (driver, block["name"], warning)
            )

        # hold_current is only rewritten when the section already sets it:
        # adding it would silently lower the holding torque of Z.
        if "hold_current" not in active:
            values.pop("hold_current", None)
            report["notes"].append(
                "[%s %s] hold_current не задан: Klipper держит током run_current"
                % (driver, block["name"])
            )
        if mode == "stealthchop":
            for key in CHOPPER_KEYS:
                if key in active:
                    report["notes"].append(
                        "[%s %s] %s сохранён: в StealthChop регистры чоппера не работают"
                        % (driver, block["name"], key)
                    )
            for key in CHOPPER_KEYS:
                values.pop(key, None)
        for key in values:
            if key.startswith("driver_"):
                field = key[len("driver_"):].upper()
                if field not in DRIVER_KEYS[driver]:
                    raise CalcError(
                        "internal error: %s is not a %s driver key" % (key, driver)
                    )
        for key, raw in active.items():
            if key.startswith("driver_") and key not in MANAGED_KEYS:
                field = key[len("driver_"):].upper()
                if field not in DRIVER_KEYS[driver]:
                    report["warnings"].append(
                        "[%s %s] неизвестный драйверу ключ %s=%s сохранён как есть"
                        % (driver, block["name"], key, raw)
                    )
                else:
                    report["notes"].append(
                        "[%s %s] %s=%s сохранён: не входит в расчёт"
                        % (driver, block["name"], key, raw)
                    )

        new_body: list[str] = []
        seen: set[str] = set()
        for line in body:
            parsed = split_option(line)
            if parsed and parsed[0] in values:
                if same_number(parsed[1], values[parsed[0]]):
                    # ``0.600`` and ``0.6`` are the same current: rewriting it
                    # would only add diff noise to unrelated modules.
                    new_body.append(line)
                else:
                    new_body.append(rewrite_option(line, values[parsed[0]]))
                seen.add(parsed[0])
            else:
                new_body.append(line)
        missing = [key for key in values if key not in seen]
        if missing:
            insert_at = len(new_body)
            while insert_at > 0 and not new_body[insert_at - 1].strip():
                insert_at -= 1
            last_active = None
            for index, line in enumerate(new_body[:insert_at]):
                if split_option(line):
                    last_active = index
            insert_at = (last_active + 1) if last_active is not None else 0
            new_body[insert_at:insert_at] = [
                "%s: %s" % (OPTION_SPELLING.get(key, key), values[key])
                for key in missing
            ]
        lines[start + 1:end] = new_body
        rows.append(
            {
                "section": "[%s %s]" % (driver, block["name"]),
                "motor": result["motor"],
                "vm": result["vm"],
                "sense_resistor": result["sense_resistor"],
                "mode": mode,
                "run_current": result["run_current"],
                "i_factor": result["i_factor_effective"],
                "tbl": result["tbl"],
                "toff": result["toff"],
                "tbl_source": result["tbl_source"],
                "toff_source": result["toff_source"],
                "registers": result["registers"],
            }
        )
    rows.reverse()
    report["notes"].reverse()
    report["warnings"].reverse()

    # Replace the managed block (if any) and put the fresh one on top.
    cleaned: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == UPDATE_BEGIN:
            inside = True
            continue
        if line.strip() == UPDATE_END:
            inside = False
            continue
        if not inside:
            cleaned.append(line)
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    header = [UPDATE_BEGIN]
    first = rows[0]
    header.append(
        "# %s @ %s V, Rsense=%s Ohm, i_factor=%s"
        % (first["motor"] or "CLI parameters", _fmt(first["vm"]),
           _fmt(first["sense_resistor"]), _fmt(first["i_factor"]))
    )
    if args.motor:
        header.append("# Мотор: %s" % motors[args.motor]["source"])
    else:
        header.append("# Мотор: параметры из командной строки")
    for row in rows:
        regs = row["registers"]
        if "cs" in regs:
            detail = "CS=%d vsense=%d" % (int(regs["cs"]), int(regs["vsense"]))
        else:
            detail = "GLOBALSCALER=%d IRUN=%d" % (
                int(regs["globalscaler"]), int(regs["irun"]))
        header.append(
            "#   %s: run_current=%s A RMS, %s, %s"
            % (row["section"], _fmt(row["run_current"]), detail, row["mode"])
        )
    header.append(UPDATE_END)
    new_text = "\n".join(header + cleaned) + "\n"
    if "\r\n" in text:
        # Keep a CRLF module byte-identical outside the managed changes: the
        # updater must not turn one board file into a whole-file diff.
        new_text = new_text.replace("\n", "\r\n")
    report["sections"] = rows
    report["changed"] = new_text != text
    return new_text, report


def write_module_file(path: str, text: str) -> str:
    """Atomically replace an existing .cfg file, keeping its mode."""
    target = os.path.realpath(path)
    if not os.path.isfile(target) or not target.endswith(".cfg"):
        raise CalcError("--update-module needs an existing .cfg file, got %r" % path)
    mode = os.stat(target).st_mode & 0o777
    temporary = "%s.tmp-%d" % (target, os.getpid())
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


# --- Writing -------------------------------------------------------------


def write_module(path: str, text: str, force: bool) -> str:
    base = os.path.realpath(os.path.join(REPO_ROOT, TMC_MODULE_DIR))
    target = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    if not (target.startswith(base + os.sep) and target.endswith(".cfg")):
        raise CalcError(
            "--write must stay inside %s and name a .cfg file, got %r"
            % (TMC_MODULE_DIR, path)
        )
    if os.path.exists(target) and not force:
        raise CalcError("%s already exists (use --force to overwrite)" % target)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.chmod(target, 0o644)
    return target


def module_xy_pair(path: str) -> tuple[str, str]:
    """(driver, motor) of an ``xy-<driver>-<motor>.cfg`` module path.

    >>> module_xy_pair("manta-m8p/xy-tmc5160-LDO-42STH48-2804AH-R.cfg")
    ('tmc5160', 'LDO-42STH48-2804AH-R')
    >>> module_xy_pair("manta-m5p/xy-tmc2209-17HM19-1684.cfg")
    ('tmc2209', '17HM19-1684')
    """
    stem = os.path.basename(path)[:-4] if path.endswith(".cfg") else os.path.basename(path)
    if not stem.startswith("xy-"):
        raise CalcError(
            "only xy-*.cfg modules can be wired to the xy_driver axis, got %r"
            % os.path.basename(path)
        )
    rest = stem[3:]
    for driver in sorted(DRIVER_LABELS):
        prefix = driver + "-"
        if rest.startswith(prefix):
            return driver, rest[len(prefix):]
    raise CalcError(
        "cannot read the driver from %r: expected xy-<tmc5160|tmc2209>-<motor>.cfg"
        % os.path.basename(path)
    )


def profile_dir_of(profile: str) -> str:
    profile_dir = os.path.realpath(
        profile if os.path.isabs(profile) else os.path.join(REPO_ROOT, profile)
    )
    if not profile_dir.startswith(os.path.realpath(REPO_ROOT) + os.sep):
        raise CalcError("--wire-profile must point inside the repository")
    if not os.path.isfile(os.path.join(profile_dir, "machine.conf")):
        raise CalcError(
            "machine.conf not found: %s" % os.path.join(profile_dir, "machine.conf")
        )
    return profile_dir


def ensure_step_angle(profile: str, step_angle: object) -> None:
    """Refuse to wire a module whose motor does not match the profile.

    A driver module is written for one motor type: wiring a 1.8 degree motor
    into a 0.9 degree machine would silently halve the travel per step.
    """
    if step_angle is None:
        return
    conf = os.path.join(profile_dir_of(profile), "machine.conf")
    profile_step = None
    with open(conf, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip().startswith("xy_step="):
                profile_step = line.split("=", 1)[1].strip()
    if profile_step is None:
        return
    if abs(float(step_angle) - float(profile_step)) > 0.001:
        raise CalcError(
            "motor step angle %s does not match %s xy_step=%s: fix xy_step "
            "first or choose the module for the other motor"
            % (step_angle, os.path.join(profile, "machine.conf"), profile_step)
        )


def validate_wire_pair(profile: str, driver: str, motor: str) -> None:
    """Refuse a pair the profile cannot render (module missing, wrong step...)."""
    profile_dir = profile_dir_of(profile)
    conf = os.path.join(profile_dir, "machine.conf")
    render = os.path.join(REPO_ROOT, "scripts", "render_profile.py")
    sys.path.insert(0, os.path.dirname(render))
    try:
        import render_profile  # noqa: WPS433 - sibling script, loaded on demand
    finally:
        sys.path.pop(0)
    try:
        values = render_profile.parse_machine_conf(conf)
        values["xy_driver"] = driver
        values["xy_motor"] = motor
        render_profile.validate(values)
    except (render_profile.ProfileError, ValueError) as exc:
        raise CalcError("cannot wire %s+%s: %s" % (driver, motor, exc))


def wire_profile(
    profile: str, driver: str, motor: str, step_angle: object = None
) -> str:
    """Write ``xy_driver`` and ``xy_motor`` into machine.conf, then re-render.

    The profile is validated before anything is written: a pair without a
    module for both board families is refused, so the profile cannot be left
    pointing at a module that does not exist.
    """
    profile_dir = profile_dir_of(profile)
    conf = os.path.join(profile_dir, "machine.conf")
    ensure_step_angle(profile, step_angle)
    validate_wire_pair(profile, driver, motor)

    render = os.path.join(REPO_ROOT, "scripts", "render_profile.py")

    with open(conf, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    wanted = {"xy_driver": driver, "xy_motor": motor}
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in wanted and "=" in line:
            lines[index] = "%s=%s" % (key, wanted.pop(key))
    missing = [key for key in ("xy_motor", "xy_driver") if key in wanted]
    if missing:
        insert_at = len(lines)
        for index, line in enumerate(lines):
            if line.strip().startswith("xy_step="):
                insert_at = index + 1
                break
        lines[insert_at:insert_at] = [
            "%s=%s" % (key, wanted[key]) for key in missing
        ]
    with open(conf, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    proc = subprocess.run(
        [sys.executable, render, "--machine-dir", profile_dir, "--write"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CalcError(
            "render_profile.py failed (%d): %s"
            % (proc.returncode, (proc.stderr or proc.stdout).strip())
        )
    rel = os.path.relpath(profile_dir, REPO_ROOT)
    return (
        "%s: xy_driver=%s xy_motor=%s\n"
        "%s/profile.cfg перегенерирован. Проверка:\n"
        "  ./scripts/deploy_configs.sh -p %s --check"
        % (os.path.join(rel, "machine.conf"), driver, motor, rel, os.path.basename(rel))
    )


# --- CLI -----------------------------------------------------------------


def run_update_module(args: argparse.Namespace) -> int:
    """--update-module: recompute a module in place (or show the diff)."""
    if args.vm is None:
        print("ERROR: --update-module requires --vm", file=sys.stderr)
        return 2
    if args.sections:
        args.sections = [item.strip() for item in args.sections.split(",") if item.strip()]
    try:
        with open(args.update_module, "r", encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        print("ERROR: cannot read %s: %s" % (args.update_module, exc), file=sys.stderr)
        return 2
    try:
        motors = load_motors(args.motors_db)
        new_text, report = update_module_text(text, args, motors)
        changed = bool(report["changed"])
        written = None
        if changed and args.force:
            written = write_module_file(args.update_module, new_text)
    except CalcError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        report["module"] = args.update_module
        report["written"] = bool(written)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        diff_stream = sys.stderr
    else:
        diff_stream = sys.stdout
        print("модуль: %s" % args.update_module)
        for row in report["sections"]:
            regs = row["registers"]
            detail = (
                "CS=%d vsense=%d" % (int(regs["cs"]), int(regs["vsense"]))
                if "cs" in regs
                else "GLOBALSCALER=%d IRUN=%d"
                % (int(regs["globalscaler"]), int(regs["irun"]))
            )
            print(
                "  %s: run_current=%s A RMS (%s, %s), TBL=%s (%s) TOFF=%s (%s)"
                % (row["section"], _fmt(row["run_current"]), detail, row["mode"],
                   row["tbl"], row["tbl_source"], row["toff"], row["toff_source"])
            )
        for note in report["notes"]:
            print("  примечание: %s" % note)
        for warning in report["warnings"]:
            print("  ВНИМАНИЕ: %s" % warning)
        if written:
            print("записан модуль: %s" % os.path.relpath(written, os.getcwd()))
        elif changed:
            print("DRY-RUN: изменения не записаны (добавьте --force)")
        else:
            print("изменений нет")

    if changed and not args.json:
        diff = difflib.unified_diff(
            text.splitlines(), new_text.splitlines(),
            fromfile=args.update_module, tofile=args.update_module + " (new)",
            lineterm="",
        )
        for line in diff:
            diff_stream.write(line + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Расчёт параметров TMC2209/TMC5160 для Klipper по даташиту мотора. "
            "Формулы — только из docs/tmc/CALCS.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24\n"
            "  tmc_calc.py --driver tmc2209 --i-rated 1.7 --l-mh 2.8 --r-ohm 1.5 "
            "--vm 24 --section stepper_z\n"
            "  tmc_calc.py --driver tmc5160 --motor LDO-42STH48-2804AH-R --vm 48 "
            "--write manta-m8p/xy-tmc5160-LDO-42STH48-2804AH-R.cfg "
            "--wire-profile printers/v24-350\n"
        ),
    )
    parser.add_argument("--driver", choices=sorted(DRIVER_LABELS), help="тип драйвера")
    parser.add_argument("--motor", help="имя мотора из docs/tmc/motors.json")
    parser.add_argument("--i-rated", type=float, help="номинальный ток фазы, A")
    parser.add_argument("--l-mh", type=float, help="индуктивность фазы, мГн")
    parser.add_argument("--r-ohm", type=float, help="сопротивление фазы, Ом")
    parser.add_argument("--vm", type=float, help="напряжение питания драйвера, В")
    parser.add_argument("--rsense", type=float, help="шунт, Ом (по умолчанию 2209: 0.110, 5160: 0.075)")
    parser.add_argument("--current-basis", choices=("rms", "peak"),
                        default="rms",
                        help="как трактовать номинальный ток: RMS (по умолчанию) "
                             "или peak; peak переводится в RMS делением на √2")
    parser.add_argument("--i-factor", type=float, default=0.8,
                        help="доля номинального тока (по умолчанию 0.8); "
                             "игнорируется при --run-current")
    parser.add_argument("--run-current", type=float, metavar="A",
                        help="явный run_current, A RMS; i_factor выводится из него")
    parser.add_argument("--mode", choices=("spreadcycle", "stealthchop"),
                        help="режим чоппера (по умолчанию spreadcycle; "
                             "--update-module без флага сохраняет режим каждой секции)")
    parser.add_argument("--hold-frac", type=float, default=0.5,
                        help="hold_current = run_current x доля; 0 — не печатать")
    parser.add_argument("--stealthchop-threshold", type=float,
                        help="порог stealthchop в мм/с (по умолчанию 999999 для stealthchop, иначе 0)")
    parser.add_argument("--tbl", type=int, default=None,
                        help="TBL 0..3 (по умолчанию 0 — правило парка; "
                             "--update-module берёт значение секции)")
    parser.add_argument("--toff", type=int, default=None,
                        help="TOFF 1..15 (по умолчанию 3; --update-module берёт "
                             "значение секции)")
    parser.add_argument("--tbl-source", choices=("cli", "module", "profile"),
                        default="cli", help=argparse.SUPPRESS)
    parser.add_argument("--toff-source", choices=("cli", "module", "profile"),
                        default="cli", help=argparse.SUPPRESS)
    parser.add_argument("--iholddelay", type=int, help="driver_IHOLDDELAY, печатается если отличается от Klipper")
    parser.add_argument("--tpowerdown", type=int, help="driver_TPOWERDOWN, печатается если отличается от Klipper")
    parser.add_argument("--pwm-ofs", type=int, help="PWM_OFS из PWM_AUTO (только stealthchop)")
    parser.add_argument("--pwm-grad", type=int, help="PWM_GRAD из PWM_AUTO (только stealthchop)")
    parser.add_argument("--sgt", help="'auto' — подсказка, число — driver_SGTHRS/driver_SGT")
    parser.add_argument("--section", action="append", default=[],
                        metavar="NAME", help="секция stepper_* (можно повторять)")
    parser.add_argument("--pins", help="список пинов через запятую (UART_0,UART_1)")
    parser.add_argument("--spi", choices=("spi2", "spi1", "software"), default="spi2",
                        help="SPI TMC5160: аппаратный bus или software SPI")
    parser.add_argument("--spi-prefix", default="TMC", help="префикс software SPI пинов (TMC)")
    parser.add_argument("--no-diag", action="store_true", help="не печатать diag1_pin (TMC5160)")
    parser.add_argument("--xy-step", help="шаг мотора в профиле (0.9/1.8) для сверки")
    parser.add_argument("--motors-db", default=os.path.join(REPO_ROOT, MOTORS_DB),
                        help="путь к motors.json")
    parser.add_argument("--json", action="store_true", help="машинно-читаемый вывод")
    parser.add_argument("--write", metavar="FILE",
                        help="записать модуль в std.configs/mechanics/tmc/ (путь относительно)")
    parser.add_argument("--force", action="store_true", help="перезаписать существующий модуль")
    parser.add_argument("--wire-profile", metavar="DIR",
                        help="прописать xy_driver+xy_motor в printers/<id>/machine.conf и перегенерировать profile.cfg")
    parser.add_argument("--update-module", metavar="FILE",
                        help="пересчитать параметры в существующем модуле (.cfg) на месте, "
                             "сохранив пины и порядок опций")
    parser.add_argument("--sections", metavar="A,B",
                        help="секции для --update-module (по умолчанию все в файле)")
    parser.add_argument("--list-motors", action="store_true", help="список моторов в базе")
    parser.add_argument("--selftest", action="store_true",
                        help="сверить формулы с docs/tmc/*.xlsx и прогнать doctest")
    return parser


def format_json(result: dict[str, object], sections: list[dict[str, object]]) -> str:
    payload = dict(result)
    chopper_values = payload.get("chopper")
    if chopper_values:
        payload["chopper"] = {key: round(value, 6) if isinstance(value, float) else value
                              for key, value in chopper_values.items()}
    payload["sections"] = [
        {"name": section["name"], "pin": section["pin"],
         "config": dict(section["lines"])}
        for section in sections
    ]
    payload["vm_window"] = [round(v, 4) for v in payload["vm_window"]]
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.selftest:
        return selftest()
    if args.update_module:
        return run_update_module(args)
    if args.list_motors:
        try:
            motors = load_motors(args.motors_db)
        except CalcError as exc:
            print("ERROR: %s" % exc, file=sys.stderr)
            return 2
        print("%-22s %8s %8s %8s %6s  %s" % ("motor", "I(A)", "L(mH)", "R(Ohm)", "step", "source"))
        for name in sorted(motors):
            entry = motors[name]
            print("%-22s %8.2f %8.2f %8.2f %6s  %s"
                  % (name, float(entry["rated_current_a"]),
                     float(entry["inductance_mh"]), float(entry["resistance_ohm"]),
                     entry.get("step_angle_deg", "?"), entry["source"]))
        return 0

    missing = [name for name, value in (("--driver", args.driver), ("--vm", args.vm))
               if value is None]
    if missing:
        parser.error("required: %s" % ", ".join(missing))
    if args.mode is None:
        args.mode = "spreadcycle"

    if args.pins:
        args.pins = [item.strip() for item in args.pins.split(",") if item.strip()]
    if not args.section:
        args.section = ["stepper_x"]
    if args.pins and len(args.pins) != len(args.section):
        print("ERROR: --pins needs one pin per --section", file=sys.stderr)
        return 2
    if args.sgt in ("none", "no"):
        args.sgt = None
    if args.mode == "spreadcycle" and (args.pwm_ofs is not None or args.pwm_grad is not None):
        print("ERROR: --pwm-ofs/--pwm-grad only apply to --mode stealthchop", file=sys.stderr)
        return 2
    if args.wire_profile and not args.write:
        print("ERROR: --wire-profile requires --write (the module must exist)", file=sys.stderr)
        return 2

    try:
        motors = load_motors(args.motors_db)
        result = calculate(args, motors)
        step_angle = result["step_angle"]
        sections = render_sections(result, args)
        text = render_text(result, sections)
        wire_pair: tuple[str, str] | None = None
        if args.wire_profile:
            # Validate the profile before writing anything: a refused wiring must
            # not leave a module the machine cannot use.
            wire_pair = module_xy_pair(args.write)
            if result["motor"] and result["motor"] != wire_pair[1]:
                raise CalcError(
                    "--write names motor %s, but --motor %s was calculated"
                    % (wire_pair[1], result["motor"])
                )
            ensure_step_angle(args.wire_profile, result["step_angle"])
            validate_wire_pair(args.wire_profile, wire_pair[0], wire_pair[1])
        written = None
        if args.write:
            written = write_module(args.write, text, args.force)
    except CalcError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    if args.json:
        print(format_json(result, sections))
    else:
        sys.stdout.write(text)
    if written:
        print("записан модуль: %s" % os.path.relpath(written, REPO_ROOT), file=sys.stderr)
    if args.wire_profile and wire_pair is not None:
        try:
            driver, motor = wire_pair
            print(
                wire_profile(args.wire_profile, driver, motor, step_angle),
                file=sys.stderr,
            )
        except CalcError as exc:
            print("ERROR: %s" % exc, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())