#!/usr/bin/env python3
"""Render a printer profile include manifest from printers/<id>/machine.conf.

machine.conf is the single place where the fleet axes (size, model, board,
motor step angle) are chosen. This script validates those values and emits a
deterministic profile.cfg with a fixed include order:

    macros.cfg
    system.cfg -> board -> toolhead board -> mechanic -> motors -> geometry
    optional subsystems (fixed order) -> extruder -> features
    std.macros -> anchors.cfg -> machine-extras.cfg

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
BOARDS = ("manta-m5p", "manta-m8p")
XY_STEPS = ("0.9", "1.8")

DEFAULT_BOARD = {"trident": "manta-m5p", "v24": "manta-m8p"}

# Optional modules, emitted in this exact order regardless of the order in
# machine.conf. A feature may expand to several include files.
FEATURES = {
    "fans": [
        "std.configs/fans/host_fan.cfg",
        "std.configs/fans/drivers_hv_fan.cfg",
        "std.configs/fans/drivers_fan.cfg",
        "std.configs/fans/filter_fan.cfg",
        "std.configs/fans/exhaust_fan.cfg",
        "std.configs/fans/mcu_extruder_fan.cfg",
    ],
    "display": ["std.configs/display/mini12864.cfg"],
    "buttons": ["std.configs/buttons/emergency_stop.cfg"],
    "belay": ["std.configs/belay.cfg"],
    "btt_sfs": ["std.configs/btt_sfs.cfg"],
    "runout": ["std.configs/extruder_runout.cfg"],
    "extra_extruder": ["std.configs/extra-extruder.cfg"],
    "host": ["std.configs/host.cfg"],
    "y_frame": ["std.configs/sensors/y-frame.cfg"],
    "eddy": ["std.configs/sht36-v3.eddy.cfg"],
}

KNOWN_KEYS = {
    "size",
    "model",
    "board",
    "xy_step",
    "toolhead",
    "head",
    "features",
    "frame_w",
    "frame_d",
    "z_base_measured",
    "z_leg_measured",
}

REQUIRED_KEYS = ("size", "model")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ProfileError(Exception):
    pass


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
    return keys


def validate(values: dict[str, str]) -> dict[str, object]:
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

    xy_step = values.get("xy_step", "0.9")
    if xy_step not in XY_STEPS:
        raise ProfileError(
            "xy_step=%s is not supported (allowed: %s)"
            % (xy_step, ", ".join(XY_STEPS))
        )

    toolhead = values.get("toolhead")
    head = values.get("head")
    for label, name in (("toolhead", toolhead), ("head", head)):
        if name is not None and not _safe_name(name):
            raise ProfileError("%s=%r is not a plain module name" % (label, name))

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

    numeric: dict[str, float] = {}
    for key in ("frame_w", "frame_d", "z_base_measured", "z_leg_measured"):
        if key in values:
            try:
                numeric[key] = float(values[key])
            except ValueError:
                raise ProfileError("%s=%r is not a number" % (key, values[key]))
            if numeric[key] <= 0:
                raise ProfileError("%s must be positive" % key)

    return {
        "size": size,
        "model": model,
        "board": board,
        "xy_step": xy_step,
        "toolhead": toolhead,
        "head": head,
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


def build_includes(values: dict[str, str], checked: dict[str, object]) -> list[str]:
    size = checked["size"]
    model = checked["model"]
    board = checked["board"]
    xy_step = checked["xy_step"]
    features = checked["features"]

    includes = ["macros.cfg", "std.configs/system.cfg"]
    includes.append("std.configs/boards/%s.cfg" % board)
    if checked["toolhead"]:
        includes.append("std.configs/boards/%s.cfg" % checked["toolhead"])
    includes.append("std.configs/mechanics/%s.cfg" % model)
    includes.append("std.configs/motors/xy-step-%s.cfg" % xy_step)
    includes.append("std.configs/geometry/%s-%d.cfg" % (model, size))

    # Subsystems that must be defined before the extruder/probe sections.
    for name in ("fans", "display", "buttons"):
        if name in features:
            includes.extend(FEATURES[name])
    includes.append("std.configs/probe.cfg")
    includes.append("std.configs/bed.cfg")
    if checked["head"]:
        includes.append("std.configs/extruder/heads/%s.cfg" % checked["head"])
    includes.append("std.configs/extruder/main.cfg")
    # Filament and host features that overlay the extruder/probe setup.
    for name in ("belay", "btt_sfs", "runout", "extra_extruder", "host"):
        if name in features:
            includes.extend(FEATURES[name])
    for name in ("y_frame", "eddy"):
        if name in features:
            includes.extend(FEATURES[name])

    includes.append("std.macros/test_speed.cfg")
    includes.append("anchors.cfg")
    includes.append("machine-extras.cfg")

    for path in includes:
        if path in ("macros.cfg", "anchors.cfg", "machine-extras.cfg"):
            # Profile-local files; deploy and the checker resolve them next to
            # printer.cfg, so only the repository profile can be verified here.
            continue
        _require(path, "machine.conf")
    return includes


def render(values: dict[str, str], checked: dict[str, object], includes: list[str]) -> str:
    numeric = checked["numeric"]
    header = [
        "# GENERATED FILE - do not edit.",
        "# Source: printers/<profile>/machine.conf",
        "# Regenerate: scripts/render_profile.py --machine-dir <profile> --write",
        "#",
        "# size=%d model=%s board=%s xy_step=%s"
        % (checked["size"], checked["model"], checked["board"], checked["xy_step"]),
    ]
    if checked["toolhead"]:
        header.append("# toolhead=%s" % checked["toolhead"])
    if checked["head"]:
        header.append("# head=%s" % checked["head"])
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
        "board=%s" % checked["board"],
        "xy_step=%s" % checked["xy_step"],
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
        checked = validate(values)
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