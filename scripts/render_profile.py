#!/usr/bin/env python3
"""Render a printer profile include manifest from printers/<id>/machine.conf.

machine.conf is the single place where the hardware is chosen: bed size, the
mechanics archetype (model/kinematics/z_count/leveling), board, and the X/Y, Z
and extruder driver/motor pairs. This script validates those values and emits a
deterministic profile.cfg with a fixed include order:

    macros.cfg
    system.cfg -> board -> toolhead board -> mechanic -> x/y + z modules
    -> motors -> geometry
    optional subsystems (fixed order) -> extruder -> features
    std.macros -> anchors.cfg -> machine-extras.cfg -> probe temperature guard
    (v24)

std.configs/probe.cfg is emitted only when no eddy feature is enabled: an eddy
probe registers as "probe" itself and both sections abort Klipper.

The generated manifest is committed into the profile and re-rendered by
deploy_configs.sh, which aborts when the committed copy is stale.

Usage:
  render_profile.py --machine-dir printers/<id>            # print manifest
  render_profile.py --machine-dir printers/<id> --write    # write profile.cfg
  render_profile.py --machine-dir printers/<id> --output FILE
  render_profile.py --machine-dir printers/<id> --dump-conf FILE
  render_profile.py --machine-dir printers/<id> --axis size=250 --axis model=v24

Exit status: 2 on validation errors (unknown key/value, missing module).
"""

from __future__ import annotations

import argparse
import os
import sys

# Accepted axis values. Keep in sync with check_config.py and README.
SIZES = (150, 200, 250, 300, 350)
MODELS = ("trident", "v24")
BOARDS = ("manta-m5p", "manta-m8p", "manta-m8p-v1.0", "manta-m8p-v1.1")
# M8P revisions (V1.0, V1.1, V2.0) share every family module; only the pin file
# and the display bus differ.  Modules are named after this family.
BOARD_FAMILIES = ("manta-m5p", "manta-m8p")
XY_STEPS = ("0.9", "1.8")
# Driver ICs of the X/Y module family.  The motor is a separate key, so the
# module name is always xy-<driver>-<motor>.cfg.
XY_DRIVER_ICS = ("tmc5160", "tmc2209")
# Hardware driver name -> Klipper section name.  The M5P carries TMC2109 chips
# that Klipper drives through its tmc2209 module, so a Z module is named after
# the hardware but tmc_calc.py is called with the Klipper IC.
KLIPPER_DRIVER_IC = {"tmc2109": "tmc2209"}

# Archetype of every mechanics model: (kinematics, z_count, leveling).  The
# model stays the mechanics selector; the explicit keys must agree with it.
MODEL_PROFILE = {
    "trident": ("corexy", 3, "z_tilt"),
    "v24": ("corexy", 4, "quad_gantry_level"),
}
# Z driver/motor pair of the archetype (fleet hardware).  The v24 line uses
# the stronger 17HS19-2004S1 from 250 mm and up.
V24_Z_MOTOR_FROM = 250
DEFAULT_Z_PAIR = {
    "trident": ("tmc2109", "17HS4401S"),
    "v24": ("tmc2209", "17HS4401S"),
}
DEFAULT_E_MOTOR = "MOONS-CSE14HRA1L410A-01"
# The extruder driver is fixed by the toolhead board.  Only boards listed here
# are named in the resolved header; the key itself is never stored, so the
# profile cannot drift from the hardware.
E_DRIVER_BY_TOOLHEAD = {"sht36-v3": "tmc2209"}

# Supply rails.  X/Y may run from the higher rail only on a board that has a
# driver-power HV input; Z and the extruders always use the 24 V rail.  The
# per-board maximum is a hardware fact from the BTT wiki: the M5P and the M8P
# V1.x feed the drivers from the 24 V input ("driver power up to DC 48 V" is
# the absolute module rating), while the M8P V2.0 has a selectable HV input
# (24-60 V) for the driver rail.
VM_XY_VALUES = ("48", "55")
# SpreadCycle chopper inputs of tmc_calc.py, one pair per axis group.  The
# fleet runs TBL=0 on every motor, so an omitted key resolves to the fleet
# value rather than the tmc_calc.py CLI default.
CHOPPER_DEFAULTS = {"xy": (0, 3), "z": (0, 3), "e": (0, 3)}
TBL_VALUES = (0, 1, 2, 3)
TOFF_VALUES = tuple(range(1, 16))
VM_ZE = 24
BOARD_VM_XY_MAX = {
    "manta-m5p": 48,
    "manta-m8p": 55,
    "manta-m8p-v1.0": 48,
    "manta-m8p-v1.1": 48,
}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _xy_modules_by_family() -> dict[str, set[str]]:
    """``xy-*.cfg`` file names present in every board family directory."""
    base = os.path.join(REPO_ROOT, "std.configs", "mechanics", "tmc")
    families: dict[str, set[str]] = {}
    for name in BOARD_FAMILIES:
        try:
            families[name] = {
                item
                for item in os.listdir(os.path.join(base, name))
                if item.startswith("xy-") and item.endswith(".cfg")
            }
        except OSError:
            families[name] = set()
    return families


def discover_xy_pairs() -> tuple[tuple[str, str], ...]:
    """(driver, motor) pairs that have an XY module in every board family.

    A pair is wireable once ``xy-<driver>-<motor>.cfg`` exists in both family
    directories (see scripts/tmc_calc.py --write).
    """
    families = _xy_modules_by_family()
    common: set[str] | None = None
    for names in families.values():
        common = set(names) if common is None else common & names
    pairs = []
    for name in sorted(common or ()):
        stem = name[3:-4]
        for driver in XY_DRIVER_ICS:
            prefix = driver + "-"
            if stem.startswith(prefix):
                pairs.append((driver, stem[len(prefix):]))
                break
    return tuple(pairs)


XY_PAIRS = discover_xy_pairs() or (
    ("tmc5160", "17HM19-1684"),
    ("tmc5160", "LDO-42STH48-2804AH-R"),
)

DEFAULT_BOARD = {"trident": "manta-m5p", "v24": "manta-m8p"}
# Fleet rule: only the 150 mm machine uses the 0.9 degree motors.  All other
# sizes use LDO-42STH48-2804AH-R (1.8 degree) on TMC5160.
DEFAULT_XY_STEP = {"150": "0.9"}
DEFAULT_XY_MOTOR = {
    "0.9": "17HM19-1684",
    "1.8": "LDO-42STH48-2804AH-R",
}
DEFAULT_XY_DRIVER = "tmc5160"

# Optional modules, emitted in this exact order regardless of the order in
# machine.conf. A feature may expand to several include files.
FEATURES = {
    "fans": [
        "std.configs/fans/host_fan.cfg",
        "std.configs/fans/{board}/drivers_hv_fan.cfg",
        "std.configs/fans/{board}/drivers_fan.cfg",
        "std.configs/fans/{board}/psu_fan.cfg",
        "std.configs/fans/{board}/board_fan.cfg",
        "std.configs/fans/{board}/filter_fan.cfg",
        "std.configs/fans/{board}/exhaust_fan.cfg",
        "std.configs/fans/mcu_extruder_fan.cfg",
    ],
    "display": ["std.configs/display/mini12864.cfg"],
    "buttons": ["std.configs/buttons/emergency_stop.cfg"],
    "belay": ["std.configs/belay.cfg"],
    "btt_sfs": ["std.configs/btt_sfs.cfg"],
    "runout": ["std.configs/extruder_runout.cfg"],
    "extra_extruder": ["std.configs/extra-extruder.cfg"],
    "host": ["std.configs/host.cfg"],
    "y_frame": ["std.configs/sensors/y-frame/{board}.cfg"],
    "eddy": ["std.configs/sht36-v3.eddy.cfg"],
    "eddy_f": ["std.configs/sht36-v3.eddy-f.cfg"],
}

# A feature whose config references an MCU must never be enabled without the
# feature that declares it: the pins would reference an undeclared MCU.
FEATURE_DEPENDENCIES = {
    "belay": ("extra_extruder", "its sensors are wired to the extra extruder MCU"),
    "btt_sfs": ("extra_extruder", "its sensors are wired to the extra extruder MCU"),
    "fans": ("host", "fans/host_fan.cfg needs the host MCU ([mcu host])"),
}

# Feature pairs that declare the same Klipper section.  Klipper merges same-named
# sections with last-wins semantics, so enabling both would silently pick one.
FEATURE_CONFLICTS = {
    "eddy": ("eddy_f", "both declare [probe_eddy_current fly_eddy_probe]"),
}

# Eddy probes are wired to the toolhead board and address its MCU ("extruder"),
# so they need the board module that declares that MCU.
EDDY_FEATURES = ("eddy", "eddy_f")
EDDY_TOOLHEAD = "sht36-v3"

KNOWN_KEYS = {
    "size",
    "model",
    "kinematics",
    "z_count",
    "leveling",
    "board",
    "xy_step",
    "xy_motor",
    "xy_driver",
    "z_motor",
    "z_driver",
    "e_motor",
    "toolhead",
    "head",
    # Schema v1 key, kept only to produce an explicit migration error.
    "extruder_motor",
    "vm_xy",
    "vm_ze",
    "features",
    "frame_w",
    "frame_d",
    "z_base_measured",
    "z_leg_measured",
    # SpreadCycle chopper inputs (docs/tmc/CALCS.md §3).  They are the TBL/TOFF
    # arguments of tmc_calc.py, named per axis group.
    "xy_tbl",
    "xy_toff",
    "z_tbl",
    "z_toff",
    "e_tbl",
    "e_toff",
}

REQUIRED_KEYS = ("size", "model")
# Every committed profile must name the full hardware.  They are separate from
# REQUIRED_KEYS because --axis matrix runs describe hypothetical machines and
# get safe defaults for them.
MANDATORY_KEYS = (
    "board",
    "kinematics",
    "z_count",
    "leveling",
    "xy_step",
    "xy_motor",
    "xy_driver",
    "z_motor",
    "z_driver",
    "e_motor",
    "vm_xy",
    "vm_ze",
)
# The rail check is also called by check_config.py and new_machine.sh with a
# partial mapping, so it only insists on the two rail keys.
RAIL_KEYS = ("vm_xy", "vm_ze")

class ProfileError(Exception):
    pass


def _motors_db() -> dict[str, dict[str, object]]:
    import json

    path = os.path.join(REPO_ROOT, "docs", "tmc", "motors.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        name: entry
        for name, entry in data.items()
        if isinstance(entry, dict) and name != "motor_by_module"
    }


def motor_names() -> set[str]:
    """Motor keys of docs/tmc/motors.json (the "motor_by_module" map excluded)."""
    return set(_motors_db())


def motor_step_angle(name: str) -> str | None:
    """``step_angle_deg`` of a motor as the profile spells it ("0.9"/"1.8").

    >>> motor_step_angle("17HM19-1684"), motor_step_angle("17HS4401S")
    ('0.9', '1.8')
    >>> motor_step_angle("no-such-motor") is None
    True
    """
    entry = _motors_db().get(name)
    if entry is None:
        return None
    value = entry.get("step_angle_deg")
    if value is None:
        return None
    return "%g" % float(value)


def _check_chopper_int(
    values: dict[str, str], key: str, default: int, allowed: tuple[int, ...], label: str
) -> int:
    raw = str(values.get(key, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ProfileError("%s=%r is not an integer" % (key, raw))
    if value not in allowed:
        raise ProfileError("%s=%d is outside %s" % (key, value, label))
    return value


def check_chopper_pair(values: dict[str, str], axis: str) -> tuple[int, int]:
    """``<axis>_tbl``/``<axis>_toff`` with range checks.

    >>> check_chopper_pair({}, "xy")
    (0, 3)
    >>> check_chopper_pair({"xy_tbl": "0", "xy_toff": "3"}, "xy")
    (0, 3)
    >>> try:
    ...     check_chopper_pair({"z_tbl": "9"}, "z")
    ... except ProfileError as exc:
    ...     print(str(exc).split(":")[0])
    z_tbl=9 is outside 0..3
    >>> try:
    ...     check_chopper_pair({"e_toff": "0"}, "e")
    ... except ProfileError as exc:
    ...     print(str(exc))
    e_toff=0 is outside 1..15
    """
    tbl_default, toff_default = CHOPPER_DEFAULTS[axis]
    tbl = _check_chopper_int(values, "%s_tbl" % axis, tbl_default, TBL_VALUES, "0..3")
    toff = _check_chopper_int(
        values, "%s_toff" % axis, toff_default, TOFF_VALUES, "1..15"
    )
    return tbl, toff


def check_step_angle(xy_step: str, xy_motor: str) -> None:
    """The geometry module and the motor must agree on the step angle.

    >>> check_step_angle("0.9", "17HM19-1684")
    >>> try:
    ...     check_step_angle("1.8", "17HM19-1684")
    ... except ProfileError as exc:
    ...     print(str(exc).split(":")[0])
    xy_step=1.8 does not match 17HM19-1684 step_angle_deg=0.9
    """
    angle = motor_step_angle(xy_motor)
    if angle is None:
        known = motor_names()
        if known:
            raise ProfileError(
                "xy_motor=%r is not in docs/tmc/motors.json (known: %s)"
                % (xy_motor, ", ".join(sorted(known)))
            )
        return
    if abs(float(angle) - float(xy_step)) > 1e-6:
        raise ProfileError(
            "xy_step=%s does not match %s step_angle_deg=%s: the geometry "
            "module would be wrong" % (xy_step, xy_motor, angle)
        )


def check_legacy_keys(values: dict[str, str]) -> None:
    """Reject schema v1 keys with an explicit migration hint.

    >>> try:
    ...     check_legacy_keys({"xy_driver": "tmc5160-17HM19-1684"})
    ... except ProfileError as exc:
    ...     print(str(exc).split(":")[0])
    xy_driver='tmc5160-17HM19-1684' is the old combined driver+motor value
    >>> try:
    ...     check_legacy_keys({"extruder_motor": "MOONS"})
    ... except ProfileError as exc:
    ...     print(str(exc).split(":")[0])
    extruder_motor='MOONS' is the old key
    >>> check_legacy_keys({"xy_driver": "tmc5160", "e_motor": "MOONS"})
    """
    driver = values.get("xy_driver", "").strip()
    if driver and driver not in XY_DRIVER_ICS:
        if "-" in driver:
            raise ProfileError(
                "xy_driver=%r is the old combined driver+motor value: split it "
                "into xy_driver=<driver ic> and xy_motor=<docs/tmc/motors.json "
                "key> (allowed drivers: %s; see docs/PROFILES.md)"
                % (driver, ", ".join(XY_DRIVER_ICS))
            )
        raise ProfileError(
            "xy_driver=%s is not supported (allowed drivers: %s; the motor goes "
            "into xy_motor, see docs/PROFILES.md)"
            % (driver, ", ".join(XY_DRIVER_ICS))
        )
    if "extruder_motor" in values:
        raise ProfileError(
            "extruder_motor=%r is the old key: rename it to e_motor=%r "
            "(schema v2, see docs/PROFILES.md)"
            % (values["extruder_motor"], values["extruder_motor"])
        )


def check_model_profile(
    model: str, kinematics: str, z_count: object, leveling: str
) -> None:
    """kinematics/z_count/leveling must agree with the mechanics model.

    >>> check_model_profile("trident", "corexy", 3, "z_tilt")
    >>> try:
    ...     check_model_profile("trident", "corexy", 4, "z_tilt")
    ... except ProfileError as exc:
    ...     print(str(exc).split(" (")[0])
    z_count=4 does not match model=trident, expected 3
    >>> try:
    ...     check_model_profile("v24", "delta", 4, "quad_gantry_level")
    ... except ProfileError as exc:
    ...     print(str(exc).split(" (")[0])
    kinematics=delta does not match model=v24, expected corexy
    """
    expected_kinematics, expected_count, expected_leveling = MODEL_PROFILE[model]
    if kinematics != expected_kinematics:
        raise ProfileError(
            "kinematics=%s does not match model=%s, expected %s (change the "
            "model or the key, see docs/PROFILES.md)"
            % (kinematics, model, expected_kinematics)
        )
    try:
        count = int(z_count)
    except (TypeError, ValueError):
        raise ProfileError("z_count=%r is not an integer" % (z_count,))
    if count != expected_count:
        raise ProfileError(
            "z_count=%s does not match model=%s, expected %d (change the model "
            "or the key, see docs/PROFILES.md)" % (count, model, expected_count)
        )
    if leveling != expected_leveling:
        raise ProfileError(
            "leveling=%s does not match model=%s, expected %s (change the model "
            "or the key, see docs/PROFILES.md)"
            % (leveling, model, expected_leveling)
        )


def default_z_pair(model: str, size: object) -> tuple[str, str]:
    """Default Z driver/motor pair of a model and size.

    >>> default_z_pair("v24", 250)
    ('tmc2209', '17HS19-2004S1')
    >>> default_z_pair("v24", 200)
    ('tmc2209', '17HS4401S')
    >>> default_z_pair("trident", 350)
    ('tmc2109', '17HS4401S')
    """
    driver, motor = DEFAULT_Z_PAIR[model]
    try:
        large = int(size) >= V24_Z_MOTOR_FROM
    except (TypeError, ValueError):
        large = False
    if model == "v24" and large:
        motor = "17HS19-2004S1"
    return driver, motor


def check_feature_rules(features: list[str], toolhead: str | None) -> None:
    """Reject mutually exclusive features and eddy probes without a toolhead.

    >>> check_feature_rules(["fans", "eddy_f"], "sht36-v3")
    >>> try:
    ...     check_feature_rules(["eddy_f", "eddy"], "sht36-v3")
    ... except ProfileError as exc:
    ...     print(str(exc).split(":")[0])
    features 'eddy' and 'eddy_f' are mutually exclusive
    >>> try:
    ...     check_feature_rules(["eddy_f"], None)
    ... except ProfileError as exc:
    ...     print(str(exc).split(":")[0])
    feature 'eddy_f' requires toolhead=sht36-v3
    """
    for name, (other, reason) in FEATURE_CONFLICTS.items():
        if name in features and other in features:
            raise ProfileError(
                "features %r and %r are mutually exclusive: %s (Klipper merges "
                "the sections, last value wins)" % (name, other, reason)
            )
    for name in EDDY_FEATURES:
        if name in features and toolhead != EDDY_TOOLHEAD:
            raise ProfileError(
                "feature %r requires toolhead=%s: its pins live on the toolhead "
                "MCU 'extruder'" % (name, EDDY_TOOLHEAD)
            )


def _find_module(rel_dir: str, stem: str) -> str | None:
    """Repository-relative path of ``<rel_dir>/<stem>.cfg`` or None.

    Module names are case-sensitive on Linux, while a motor key keeps the
    vendor casing (17HS4401S) and the Z modules use lower case; the fallback
    accepts any casing but returns the real file name.
    """
    directory = os.path.join(REPO_ROOT, rel_dir)
    target = os.path.join(directory, stem + ".cfg")
    if os.path.isfile(target):
        return rel_dir + "/" + stem + ".cfg"
    lowered = (stem + ".cfg").lower()
    try:
        names = os.listdir(directory)
    except OSError:
        return None
    for name in names:
        if name.lower() == lowered:
            return rel_dir + "/" + name
    return None


def xy_module(family: str, driver: str, motor: str) -> str | None:
    """XY driver module of one board family (both keys are explicit)."""
    return _find_module(
        "std.configs/mechanics/tmc/" + family, "xy-%s-%s" % (driver, motor)
    )


def z_module(z_count: int, driver: str, motor: str) -> str | None:
    """Z driver module ``<count>z-<driver>-<motor>.cfg`` (lower-case stem)."""
    return _find_module(
        "std.configs/mechanics/tmc",
        "%dz-%s-%s" % (z_count, driver, motor.lower()),
    )


def parse_machine_conf(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "=" not in line:
                raise ProfileError(
                    "%s:%d: expected key=value, got %r" % (path, lineno, line)
                )
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key not in KNOWN_KEYS:
                raise ProfileError(
                    "%s:%d: unknown machine.conf key %r (known: %s)"
                    % (path, lineno, key, ", ".join(sorted(KNOWN_KEYS)))
                )
            if not value:
                raise ProfileError("%s:%d: empty value for %s" % (path, lineno, key))
            values[key] = value
    return values


def apply_axis_overrides(values: dict[str, str], overrides: list[str]) -> set[str]:
    keys: set[str] = set()
    for item in overrides:
        if "=" not in item:
            raise ProfileError("--axis expects key=value, got %r" % item)
        key, value = item.split("=", 1)
        key = key.strip()
        if key not in KNOWN_KEYS:
            raise ProfileError(
                "--axis: unknown key %r (known: %s)"
                % (key, ", ".join(sorted(KNOWN_KEYS)))
            )
        values[key] = value.strip()
        keys.add(key)
    # Matrix convenience: switching the model/board or the bed size must not
    # inherit declarations that belong to the repository profile.
    if "model" in keys and "board" not in keys:
        values.pop("board", None)
    if "size" in keys:
        frame = None
        try:
            frame = int(float(values["size"])) + 160
        except (KeyError, ValueError):
            frame = None
        if frame is not None:
            if "frame_w" not in keys:
                values["frame_w"] = str(frame)
            if "frame_d" not in keys:
                values["frame_d"] = str(frame)
    # The fleet rule is tied to the bed size: only 150 mm uses 0.9 degree
    # motors, every larger machine uses the 1.8 degree LDO motors.
    if "size" in keys:
        # A derived default must not inherit the repository profile's pair.
        if "xy_step" not in keys:
            values.pop("xy_step", None)
        if "xy_motor" not in keys:
            values.pop("xy_motor", None)
        if "xy_driver" not in keys:
            values.pop("xy_driver", None)
    if "xy_step" in keys:
        if "xy_motor" not in keys:
            values.pop("xy_motor", None)
        if "xy_driver" not in keys:
            values.pop("xy_driver", None)
    # Switching the mechanics archetype resets every key that belongs to it.
    if "model" in keys:
        for key in ("kinematics", "z_count", "leveling", "z_driver", "z_motor"):
            if key not in keys:
                values.pop(key, None)
    # A hypothetical machine (--axis model/board) must not inherit the real
    # machine's rails: 48 V is legal on every board of the fleet, while the
    # Z/E rail is always 24 V.
    if ("model" in keys or "board" in keys) and "vm_xy" not in keys:
        values["vm_xy"] = "48"
    if keys and "vm_ze" not in keys:
        values.setdefault("vm_ze", str(VM_ZE))
    return keys


def check_voltage(values: dict[str, str], board: str) -> None:
    """Validate vm_xy/vm_ze against the board limits (shared with check_config).

    >>> check_voltage({"vm_xy": "48", "vm_ze": "24"}, "manta-m5p")
    >>> check_voltage({"vm_xy": "55", "vm_ze": "24"}, "manta-m8p")
    >>> try:
    ...     check_voltage({"vm_xy": "55", "vm_ze": "24"}, "manta-m5p")
    ... except ProfileError as exc:
    ...     print(str(exc).split(" (")[0])
    vm_xy=55 is above the manta-m5p limit of 48 V
    >>> try:
    ...     check_voltage({"vm_xy": "48", "vm_ze": "12"}, "manta-m8p")
    ... except ProfileError as exc:
    ...     print(str(exc).split(" must")[0])
    vm_ze=12
    """
    missing = [key for key in RAIL_KEYS if not str(values.get(key, "")).strip()]
    if missing:
        raise ProfileError(
            "machine.conf is missing: %s (vm_xy is 48 or 55, vm_ze is 24)"
            % ", ".join(missing)
        )
    vm_xy = str(values["vm_xy"]).strip()
    if vm_xy not in VM_XY_VALUES:
        raise ProfileError(
            "vm_xy=%s is not supported (allowed: %s)" % (vm_xy, ", ".join(VM_XY_VALUES))
        )
    board_max = BOARD_VM_XY_MAX.get(board)
    if board_max is None:
        raise ProfileError(
            "vm_xy: board=%s has no driver-voltage limit in BOARD_VM_XY_MAX" % board
        )
    if int(vm_xy) > board_max:
        raise ProfileError(
            "vm_xy=%s is above the %s limit of %d V (BTT spec: driver power up "
            "to DC 48 V on this revision)" % (vm_xy, board, board_max)
        )
    vm_ze = str(values["vm_ze"]).strip()
    try:
        ze_value = float(vm_ze)
    except ValueError:
        raise ProfileError("vm_ze=%r is not a number" % vm_ze)
    if ze_value != VM_ZE:
        raise ProfileError(
            "vm_ze=%s must be %d V: Z and the extruders always use the 24 V rail"
            % (vm_ze, VM_ZE)
        )


def validate(values: dict[str, str], strict: bool = True) -> dict[str, object]:
    """Validate machine.conf and return the resolved hardware map.

    ``strict`` is False for --axis runs: a hypothetical machine may omit the
    keys that the renderer can derive from model/size and gets the fleet
    defaults, while a committed profile must name every hardware key.
    """
    check_legacy_keys(values)

    if strict:
        missing = [
            key for key in MANDATORY_KEYS if not str(values.get(key, "")).strip()
        ]
        if missing:
            raise ProfileError(
                "machine.conf is missing: %s (schema v2 requires every hardware "
                "key; see docs/PROFILES.md)" % ", ".join(missing)
            )

    missing = [key for key in REQUIRED_KEYS if key not in values]
    if missing:
        raise ProfileError("machine.conf is missing: %s" % ", ".join(missing))

    size = int(values["size"])  # ValueError is turned into ProfileError below
    if size not in SIZES:
        raise ProfileError(
            "size=%s is not supported (allowed: %s)"
            % (values["size"], ", ".join(str(s) for s in SIZES))
        )

    model = values["model"]
    if model not in MODELS:
        raise ProfileError(
            "model=%s is not supported (allowed: %s)"
            % (model, ", ".join(MODELS))
        )

    board = values.get("board") or DEFAULT_BOARD[model]
    if board not in BOARDS:
        raise ProfileError(
            "board=%s is not supported (allowed: %s)"
            % (board, ", ".join(BOARDS))
        )

    model_kinematics, model_z, model_leveling = MODEL_PROFILE[model]
    kinematics = values.get("kinematics") or model_kinematics
    z_count_raw = values.get("z_count") or str(model_z)
    leveling = values.get("leveling") or model_leveling
    check_model_profile(model, kinematics, z_count_raw, leveling)
    z_count = int(z_count_raw)

    xy_step = values.get("xy_step")
    if xy_step is None:
        xy_step = DEFAULT_XY_STEP.get(str(size), "1.8")
    if xy_step not in XY_STEPS:
        raise ProfileError(
            "xy_step=%s is not supported (allowed: %s)"
            % (xy_step, ", ".join(XY_STEPS))
        )

    xy_motor = values.get("xy_motor") or DEFAULT_XY_MOTOR[xy_step]
    check_step_angle(xy_step, xy_motor)

    xy_driver = values.get("xy_driver") or DEFAULT_XY_DRIVER
    if xy_driver not in XY_DRIVER_ICS:
        raise ProfileError(
            "xy_driver=%s is not supported (allowed drivers: %s)"
            % (xy_driver, ", ".join(XY_DRIVER_ICS))
        )

    default_z_driver, default_z_motor = default_z_pair(model, size)
    z_driver = values.get("z_driver") or default_z_driver
    z_motor = values.get("z_motor") or default_z_motor
    known_motors = motor_names()
    if known_motors and z_motor not in known_motors:
        raise ProfileError(
            "z_motor=%r is not in docs/tmc/motors.json (known: %s)"
            % (z_motor, ", ".join(sorted(known_motors)))
        )

    e_motor = values.get("e_motor") or DEFAULT_E_MOTOR
    if known_motors and e_motor not in known_motors:
        raise ProfileError(
            "e_motor=%r is not in docs/tmc/motors.json (known: %s)"
            % (e_motor, ", ".join(sorted(known_motors)))
        )

    toolhead = values.get("toolhead")
    head = values.get("head")
    for label, name in (("toolhead", toolhead), ("head", head)):
        if name is not None and not _safe_name(name):
            raise ProfileError("%s=%r is not a plain module name" % (label, name))
    for label, name in (
        ("xy_motor", xy_motor),
        ("z_motor", z_motor),
        ("e_motor", e_motor),
    ):
        if not _safe_name(name):
            raise ProfileError("%s=%r is not a plain motor name" % (label, name))

    check_voltage(values, board)

    xy_modules: dict[str, str] = {}
    missing_families = []
    for family in BOARD_FAMILIES:
        path = xy_module(family, xy_driver, xy_motor)
        if path is None:
            missing_families.append(family)
        else:
            xy_modules[family] = path
    if missing_families:
        allowed = ", ".join("%s+%s" % pair for pair in XY_PAIRS)
        raise ProfileError(
            "xy_driver=%s + xy_motor=%s has no xy-%s-%s.cfg in %s (existing "
            "pairs: %s); create it with scripts/tmc_calc.py --driver %s "
            "--motor %s --vm %s --write <family>/xy-%s-%s.cfg"
            % (
                xy_driver,
                xy_motor,
                xy_driver,
                xy_motor,
                ", ".join(missing_families),
                allowed,
                xy_driver,
                xy_motor,
                values.get("vm_xy", "48"),
                xy_driver,
                xy_motor,
            )
        )

    z_path = z_module(z_count, z_driver, z_motor)
    if z_path is None:
        tool_ic = KLIPPER_DRIVER_IC.get(z_driver, z_driver)
        raise ProfileError(
            "z_driver=%s + z_motor=%s has no %dz-%s-%s.cfg module; create it "
            "with scripts/tmc_calc.py --driver %s --motor %s --vm %s --write "
            "%dz-%s-%s.cfg"
            % (
                z_driver,
                z_motor,
                z_count,
                z_driver,
                z_motor.lower(),
                tool_ic,
                z_motor,
                values.get("vm_ze", "24"),
                z_count,
                z_driver,
                z_motor.lower(),
            )
        )

    features: list[str] = []
    for name in _split_features(values.get("features", "")):
        if name == "eddy_off":
            # Historical spelling in the plan: explicitly disabled.
            continue
        if name not in FEATURES:
            raise ProfileError(
                "unknown feature %r (allowed: %s)"
                % (name, ", ".join(sorted(FEATURES)))
            )
        if name not in features:
            features.append(name)

    for name, (required, reason) in FEATURE_DEPENDENCIES.items():
        if name in features and required not in features:
            raise ProfileError(
                "feature %r requires %r: %s" % (name, required, reason)
            )
    check_feature_rules(features, toolhead)

    numeric: dict[str, float] = {}
    for key in ("frame_w", "frame_d", "z_base_measured", "z_leg_measured"):
        if key in values:
            try:
                numeric[key] = float(values[key])
            except ValueError:
                raise ProfileError("%s=%r is not a number" % (key, values[key]))
            if numeric[key] <= 0:
                raise ProfileError("%s must be positive" % key)

    family = board_family(board)
    chopper = {axis: check_chopper_pair(values, axis) for axis in CHOPPER_DEFAULTS}
    return {
        "size": size,
        "model": model,
        "kinematics": kinematics,
        "z_count": z_count,
        "leveling": leveling,
        "board": board,
        "xy_step": xy_step,
        "xy_motor": xy_motor,
        "xy_driver": xy_driver,
        "z_motor": z_motor,
        "z_driver": z_driver,
        "e_motor": e_motor,
        "xy_module": xy_modules[family],
        "z_module": z_path,
        "toolhead": toolhead,
        "head": head,
        "vm_xy": values["vm_xy"].strip(),
        "vm_ze": VM_ZE,
        "xy_tbl": chopper["xy"][0],
        "xy_toff": chopper["xy"][1],
        "z_tbl": chopper["z"][0],
        "z_toff": chopper["z"][1],
        "e_tbl": chopper["e"][0],
        "e_toff": chopper["e"][1],
        "features": features,
        "numeric": numeric,
    }


def _safe_name(name: str) -> bool:
    return bool(name) and all(ch.isalnum() or ch in "-_." for ch in name)


def _split_features(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _require(path: str, context: str) -> None:
    if not os.path.isfile(os.path.join(REPO_ROOT, path)):
        raise ProfileError("%s refers to missing module %s" % (context, path))


def board_family(board: str) -> str:
    """Map a board revision to the shared module family.

    All Manta M8P revisions use the same mechanic, fan, bed, sensor and TMC
    modules; the version differences live in boards/<board>.cfg.
    """
    for family in BOARD_FAMILIES:
        if board == family or board.startswith(family + "-"):
            return family
    return board


def build_includes(values: dict[str, str], checked: dict[str, object]) -> list[str]:
    size = checked["size"]
    model = checked["model"]
    board = checked["board"]
    family = board_family(board)
    xy_step = checked["xy_step"]
    features = checked["features"]

    includes = ["macros.cfg", "std.configs/system.cfg"]
    includes.append("std.configs/boards/%s.cfg" % board)
    if checked["toolhead"]:
        includes.append("std.configs/boards/%s.cfg" % checked["toolhead"])
    includes.append("std.configs/mechanics/%s.cfg" % model)
    # Both driver modules come from the manifest: the mechanics files no longer
    # choose a TMC pair, so the machine.conf keys are the only source.
    includes.append(str(checked["xy_module"]))
    includes.append(str(checked["z_module"]))
    if family == "manta-m8p":
        # TH2/TH3 monitor the TMC5160 driver heatsinks on the M8P family; the
        # M5P uses those pins for the bed and Y-frame instead.
        includes.append("std.configs/sensors/tmc5160/%s.cfg" % family)
        # v24 Y-frame uses a 10K B3950 thermistor, not the 100K Generic 3950.
        if "y_frame" in features:
            includes.append("std.configs/sensors/ntc10k-3950.cfg")
    includes.append("std.configs/motors/xy-step-%s.cfg" % xy_step)
    includes.append("std.configs/geometry/%s-%d.cfg" % (model, size))

    # Subsystems that must be defined before the extruder/probe sections.
    if "fans" in features:
        includes.extend(path.format(board=family) for path in FEATURES["fans"])
    if "display" in features:
        includes.extend(path.format(board=family) for path in FEATURES["display"])
        if board.startswith("manta-m8p-v1."):
            # The v1.x EXP2 header does not carry the hardware spi2 MOSI, so
            # the display section is reopened with software SPI.  Klipper
            # merges same-named sections and the last value wins.
            includes.append("std.configs/display/mini12864-swspi.cfg")
    if "buttons" in features:
        includes.extend(path.format(board=family) for path in FEATURES["buttons"])
    if not any(name in features for name in EDDY_FEATURES):
        # Registered together, [probe] and [probe_eddy_current] abort Klipper
        # with "Registering duplicate object 'probe'"; an eddy module registers
        # as "probe" itself, so the physical probe section must be left out.
        includes.append("std.configs/probe.cfg")
    includes.append("std.configs/bed/%s.cfg" % family)
    if checked["head"]:
        includes.append("std.configs/extruder/heads/%s.cfg" % checked["head"])
    includes.append("std.configs/extruder/main.cfg")
    # Filament and host features that overlay the extruder/probe setup.
    for name in ("belay", "btt_sfs", "runout", "extra_extruder", "host"):
        if name in features:
            includes.extend(path.format(board=family) for path in FEATURES[name])
    for name in ("y_frame", "eddy", "eddy_f"):
        if name in features:
            includes.extend(path.format(board=family) for path in FEATURES[name])

    includes.append("std.macros/test_speed.cfg")
    includes.append("std.macros/test_speed_z.cfg")
    includes.append("std.macros/test_kinematics.cfg")
    includes.append("anchors.cfg")
    includes.append("machine-extras.cfg")
    if model == "v24":
        # Probe sits on the toolhead: keep the nozzle at or below 150C while Z is
        # homed and the gantry is levelled.  The module wraps G28/QUAD_GANTRY_LEVEL
        # on klippy:connect, so it stays effective next to safe_z_home.
        includes.append("std.macros/homing.cfg")

    for path in includes:
        if path in ("macros.cfg", "anchors.cfg", "machine-extras.cfg"):
            # Profile-local files; deploy and the checker resolve them next to
            # printer.cfg, so only the repository profile can be verified here.
            continue
        _require(path, "machine.conf")
    return includes


def hardware_line(checked: dict[str, object]) -> str:
    """Resolved hardware map shown in the generated manifest header.

    >>> hardware_line({"xy_driver": "tmc5160", "xy_motor": "17HM19-1684",
    ...  "z_count": 3, "z_driver": "tmc2109", "z_motor": "17HS4401S",
    ...  "e_motor": "MOONS", "toolhead": "sht36-v3", "vm_xy": "48",
    ...  "vm_ze": 24})
    'X/Y: tmc5160+17HM19-1684 @vm_xy=48 | Z×3: tmc2109+17HS4401S @vm_ze=24 | E: tmc2209(sht36-v3)+MOONS'
    """
    xy = "X/Y: %s+%s @vm_xy=%s" % (
        checked["xy_driver"],
        checked["xy_motor"],
        checked["vm_xy"],
    )
    z = "Z×%s: %s+%s @vm_ze=%s" % (
        checked["z_count"],
        checked["z_driver"],
        checked["z_motor"],
        checked["vm_ze"],
    )
    toolhead = checked.get("toolhead")
    e_driver = E_DRIVER_BY_TOOLHEAD.get(str(toolhead or ""))
    if e_driver:
        extruder = "E: %s(%s)+%s" % (e_driver, toolhead, checked["e_motor"])
    else:
        extruder = "E: %s" % checked["e_motor"]
    return "%s | %s | %s" % (xy, z, extruder)


def render(values: dict[str, str], checked: dict[str, object], includes: list[str]) -> str:
    numeric = checked["numeric"]
    header = [
        "# GENERATED FILE - do not edit.",
        "# Source: printers/<profile>/machine.conf",
        "# Regenerate: scripts/render_profile.py --machine-dir <profile> --write",
        "#",
        "# size=%d model=%s board=%s xy_step=%s"
        % (checked["size"], checked["model"], checked["board"], checked["xy_step"]),
        "# kinematics=%s z_count=%s leveling=%s"
        % (checked["kinematics"], checked["z_count"], checked["leveling"]),
        "# " + hardware_line(checked),
    ]
    if checked["toolhead"]:
        header.append("# toolhead=%s" % checked["toolhead"])
    if checked["head"]:
        header.append("# head=%s" % checked["head"])
    header.append("# vm_xy=%s vm_ze=%s" % (checked["vm_xy"], checked["vm_ze"]))
    if "frame_w" in numeric:
        header.append("# frame_w=%g" % numeric["frame_w"])
    if "frame_d" in numeric:
        header.append("# frame_d=%g" % numeric["frame_d"])
    header.append("")
    body = ["[include %s]" % path for path in includes]
    return "\n".join(header + body) + "\n"


def machine_conf_text(checked: dict[str, object]) -> str:
    """Normalised effective machine.conf (used for deploy staging/checks)."""
    lines = [
        "# Effective machine settings for this deploy (axis overrides applied).",
        "size=%d" % checked["size"],
        "model=%s" % checked["model"],
        "kinematics=%s" % checked["kinematics"],
        "z_count=%s" % checked["z_count"],
        "leveling=%s" % checked["leveling"],
        "board=%s" % checked["board"],
        "xy_step=%s" % checked["xy_step"],
        "xy_motor=%s" % checked["xy_motor"],
        "xy_driver=%s" % checked["xy_driver"],
        "z_motor=%s" % checked["z_motor"],
        "z_driver=%s" % checked["z_driver"],
        "e_motor=%s" % checked["e_motor"],
        "vm_xy=%s" % checked["vm_xy"],
        "vm_ze=%s" % checked["vm_ze"],
        "xy_tbl=%s" % checked["xy_tbl"],
        "xy_toff=%s" % checked["xy_toff"],
        "z_tbl=%s" % checked["z_tbl"],
        "z_toff=%s" % checked["z_toff"],
        "e_tbl=%s" % checked["e_tbl"],
        "e_toff=%s" % checked["e_toff"],
    ]
    if checked["toolhead"]:
        lines.append("toolhead=%s" % checked["toolhead"])
    if checked["head"]:
        lines.append("head=%s" % checked["head"])
    for key in ("frame_w", "frame_d", "z_base_measured", "z_leg_measured"):
        if key in checked["numeric"]:
            lines.append("%s=%g" % (key, checked["numeric"][key]))
    if checked["features"]:
        lines.append("features=%s" % ",".join(checked["features"]))
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate machine.conf and render the profile.cfg manifest."
    )
    parser.add_argument(
        "--machine-dir",
        required=True,
        metavar="DIR",
        help="printer profile directory containing machine.conf",
    )
    parser.add_argument("--output", metavar="FILE", help="write manifest to FILE")
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the manifest to <machine-dir>/profile.cfg",
    )
    parser.add_argument(
        "--dump-conf",
        metavar="FILE",
        help="write the effective machine.conf to FILE",
    )
    parser.add_argument(
        "--axis",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="temporary axis override for --check matrix runs",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    conf_path = os.path.join(args.machine_dir, "machine.conf")
    if not os.path.isfile(conf_path):
        print("ERROR: machine.conf not found: %s" % conf_path, file=sys.stderr)
        return 2
    try:
        values = parse_machine_conf(conf_path)
        overridden = apply_axis_overrides(values, args.axis)
        if overridden:
            # --axis describes a hypothetical machine: use the default board for
            # the selected model and do not apply this machine's measured
            # anchors to a different bed size.
            if "model" in overridden and "board" not in overridden:
                values.pop("board", None)
            for key in ("z_base_measured", "z_leg_measured"):
                values.pop(key, None)
        checked = validate(values, strict=not overridden)
        includes = build_includes(values, checked)
    except (ProfileError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    text = render(values, checked, includes)
    if args.dump_conf:
        _write_file(args.dump_conf, machine_conf_text(checked))
    if args.write:
        _write_file(os.path.join(args.machine_dir, "profile.cfg"), text)
    if args.output:
        _write_file(args.output, text)
    if not (args.write or args.output or args.dump_conf):
        sys.stdout.write(text)
    return 0


def _write_file(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.chmod(path, 0o644)


if __name__ == "__main__":
    raise SystemExit(main())