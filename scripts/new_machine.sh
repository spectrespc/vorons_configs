#!/usr/bin/env bash
# Create a new printer profile under printers/<id> from the schema v2 template
# and render its include manifest. The new profile is validated offline; no file
# is deployed until deploy_configs.sh is run.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
TEMPLATE="$SCRIPT_DIR/templates/machine.conf.template"

ID=""
SIZE=""
MODEL=""
BOARD=""
XY_STEP=""
XY_MOTOR=""
XY_DRIVER=""
Z_DRIVER=""
Z_MOTOR=""
E_MOTOR=""
TOOLHEAD="sht36-v3"
HEAD="HGX.8T"
VM_XY=""
FEATURES=""
FEATURES_SET=0
FRAME_W=""
FRAME_D=""
FORCE=0

usage() {
  cat <<'EOF'
Usage: new_machine.sh -p ID --size N --model MODEL [options]

Creates printers/<ID>/ from scripts/templates/machine.conf.template with seed
printer.cfg, anchors.cfg, machine-extras.cfg, macros.cfg, moonraker.conf and an
empty local/ dir, then renders profile.cfg and validates it with
check_config.py --machine. The full key reference is docs/PROFILES.md.

Required:
  -p, --printer ID    new profile name under printers/
      --size N        bed size: 150, 200, 250, 300, 350
      --model MODEL   trident (3Z, z_tilt) or v24 (4Z, quad_gantry_level)

Optional:
      --board NAME    manta-m5p, manta-m8p (M8P V2.0), manta-m8p-v1.0 or
                      manta-m8p-v1.1 (default: per model)
      --xy-step V     0.9 only for 150 mm, 1.8 for larger machines
                      (default: 0.9 at 150, 1.8 otherwise)
      --xy-motor NAME motor key from docs/tmc/motors.json for X/Y
                      (default follows xy-step: 17HM19-1684 / LDO-42STH48-2804AC)
      --xy-driver IC  X/Y driver IC: tmc5160 (default) or tmc2209
      --z-driver IC   Z driver IC (default: tmc2109 for trident, tmc2209 for v24)
      --z-motor NAME  Z motor key from docs/tmc/motors.json (default: 17HS4401S)
      --e-motor NAME  extruder motor key from docs/tmc/motors.json
                      (default: MOONS-CSE14HRA1L410A-01, the fleet HGX motor)
      --extruder-motor NAME
                      deprecated alias of --e-motor
      --toolhead NAME toolhead board module (default: sht36-v3, empty to omit)
      --head NAME     extruder head module (default: HGX.8T, empty to omit)
      --vm-xy N       X/Y driver rail: 48 (default) or 55.  55 V is only
                      accepted on manta-m8p (V2.0 HV input); Z/E stay on 24 V.
      --features LIST comma separated: fans,display,buttons,belay,
                      btt_sfs,runout,extra_extruder,host,y_frame,eddy
                      (belay and btt_sfs require extra_extruder: their
                      sensors are wired to the SHT42 board). When omitted on
                      an interactive terminal the wizard asks for the list.
      --frame-w MM    frame width (default: size + 160)
      --frame-d MM    frame depth (default: size + 160)
      --force         add files to an existing profile directory
  -h, --help          show this help
EOF
}

while (($#)); do
  case "$1" in
    -p|--printer) ID="${2:?missing value for $1}"; shift 2 ;;
    --size)       SIZE="${2:?missing value for $1}"; shift 2 ;;
    --model)      MODEL="${2:?missing value for $1}"; shift 2 ;;
    --board)      BOARD="${2:?missing value for $1}"; shift 2 ;;
    --xy-step)    XY_STEP="${2:?missing value for $1}"; shift 2 ;;
    --xy-motor)   XY_MOTOR="${2:?missing value for $1}"; shift 2 ;;
    --xy-driver)  XY_DRIVER="${2:?missing value for $1}"; shift 2 ;;
    --z-driver)   Z_DRIVER="${2:?missing value for $1}"; shift 2 ;;
    --z-motor)    Z_MOTOR="${2:?missing value for $1}"; shift 2 ;;
    --e-motor)    E_MOTOR="${2:?missing value for $1}"; shift 2 ;;
    --extruder-motor) E_MOTOR="${2:?missing value for $1}"; shift 2 ;;
    --toolhead)   TOOLHEAD="${2-}"; shift 2 ;;
    --head)       HEAD="${2-}"; shift 2 ;;
    --vm-xy)      VM_XY="${2:?missing value for $1}"; shift 2 ;;
    --features)   FEATURES="${2:?missing value for $1}"; FEATURES_SET=1; shift 2 ;;
    --frame-w)    FRAME_W="${2:?missing value for $1}"; shift 2 ;;
    --frame-d)    FRAME_D="${2:?missing value for $1}"; shift 2 ;;
    --force)      FORCE=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$ID" ]] || { echo "Profile id is required (-p)." >&2; exit 2; }
[[ -n "$SIZE" ]] || { echo "--size is required." >&2; exit 2; }
[[ -n "$MODEL" ]] || { echo "--model is required." >&2; exit 2; }
[[ "$ID" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "Invalid profile id: $ID" >&2; exit 2; }
[[ -f "$TEMPLATE" ]] || { echo "Template not found: $TEMPLATE" >&2; exit 1; }

case "$MODEL" in
  trident)
    KINEMATICS="corexy"; Z_COUNT=3; LEVELING="z_tilt"; DEFAULT_Z_DRIVER="tmc2109" ;;
  v24)
    KINEMATICS="corexy"; Z_COUNT=4; LEVELING="quad_gantry_level"; DEFAULT_Z_DRIVER="tmc2209" ;;
  *)
    echo "Unknown model '$MODEL' (allowed: trident, v24)." >&2
    exit 2 ;;
esac

# Only the 150 mm machine uses 0.9 degree X/Y motors; the rest of the fleet
# uses LDO-42STH48-2804AC (1.8 degree) on TMC5160.
if [[ -z "$XY_STEP" ]]; then
  if [[ "$SIZE" == "150" ]]; then XY_STEP="0.9"; else XY_STEP="1.8"; fi
fi
if [[ -z "$XY_MOTOR" ]]; then
  if [[ "$XY_STEP" == "0.9" ]]; then
    XY_MOTOR="17HM19-1684"
  else
    XY_MOTOR="LDO-42STH48-2804AC"
  fi
fi
if [[ -z "$XY_DRIVER" ]]; then XY_DRIVER="tmc5160"; fi
if [[ -z "$Z_DRIVER" ]]; then Z_DRIVER="$DEFAULT_Z_DRIVER"; fi
if [[ -z "$Z_MOTOR" ]]; then Z_MOTOR="17HS4401S"; fi
if [[ -z "$E_MOTOR" ]]; then E_MOTOR="MOONS-CSE14HRA1L410A-01"; fi

# Effective board: the explicit --board or the per-model default.  It decides
# whether the main MCU is a CAN node or USB only (M8P V1.0).
if [[ -n "$BOARD" ]]; then
  EFFECTIVE_BOARD="$BOARD"
else
  case "$MODEL" in
    trident) EFFECTIVE_BOARD="manta-m5p" ;;
    v24)     EFFECTIVE_BOARD="manta-m8p" ;;
    *)       EFFECTIVE_BOARD="" ;;
  esac
fi

# The X/Y rail defaults to 48 V.  Only an M8P V2.0 board accepts 55 V (its HV
# driver input); the pair is validated by render_profile.py so the limits are
# not duplicated here.
if [[ -z "$VM_XY" ]]; then
  VM_XY="48"
fi
if [[ -z "$EFFECTIVE_BOARD" ]]; then
  echo "Cannot validate --vm-xy without a known --model/--board." >&2
  exit 2
fi
if ! "$PYTHON_BIN" - "$SCRIPT_DIR" "$EFFECTIVE_BOARD" "$VM_XY" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import render_profile
try:
    render_profile.check_voltage(
        {"vm_xy": sys.argv[3], "vm_ze": str(render_profile.VM_ZE)}, sys.argv[2]
    )
except render_profile.ProfileError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(1)
PY
then
  exit 2
fi

# An interactive wizard asks for the feature set instead of silently creating a
# machine without any optional subsystem. Scripted callers keep --features.
if (( ! FEATURES_SET )) && [[ -t 0 ]]; then
  cat >&2 <<'EOF'
Features (comma separated, empty for none):
  fans,display,buttons,runout,host,y_frame,eddy
  extra_extruder (SHT42) is required by belay and btt_sfs
EOF
  read -r -p "features: " FEATURES
fi

has_feature() {
  [[ ",$FEATURES," == *",$1,"* ]]
}
for feature in belay btt_sfs; do
  if has_feature "$feature" && ! has_feature extra_extruder; then
    echo "ERROR: feature '$feature' requires 'extra_extruder': its sensors are" >&2
    echo "wired to the SHT42 board. Add extra_extruder or drop $feature." >&2
    exit 2
  fi
done

PROFILE_DIR="$SRC/printers/$ID"
if [[ -e "$PROFILE_DIR" ]] && (( ! FORCE )); then
  echo "Profile already exists: $PROFILE_DIR" >&2
  echo "Use --force to add missing files to it." >&2
  exit 1
fi
mkdir -p -- "$PROFILE_DIR/local"

if [[ -z "$FRAME_W" ]]; then
  FRAME_W=$((SIZE + 160))
fi
if [[ -z "$FRAME_D" ]]; then
  FRAME_D="$FRAME_W"
fi

# machine.conf is generated from the canonical commented template. Empty
# optional keys are removed instead of written as "key=" (the parser rejects
# empty values).
"$PYTHON_BIN" - "$TEMPLATE" "$PROFILE_DIR/machine.conf" \
  "SIZE=$SIZE" "MODEL=$MODEL" "KINEMATICS=$KINEMATICS" \
  "Z_COUNT=$Z_COUNT" "LEVELING=$LEVELING" "BOARD=$EFFECTIVE_BOARD" \
  "XY_STEP=$XY_STEP" "XY_MOTOR=$XY_MOTOR" "XY_DRIVER=$XY_DRIVER" \
  "Z_MOTOR=$Z_MOTOR" "Z_DRIVER=$Z_DRIVER" "E_MOTOR=$E_MOTOR" \
  "TOOLHEAD=$TOOLHEAD" "HEAD=$HEAD" "VM_XY=$VM_XY" "VM_ZE=24" \
  "FRAME_W=$FRAME_W" "FRAME_D=$FRAME_D" "FEATURES=$FEATURES" <<'PY'
import sys

template, target = sys.argv[1], sys.argv[2]
values = dict(item.split("=", 1) for item in sys.argv[3:])
with open(template, "r", encoding="utf-8") as fh:
    text = fh.read()
for key, value in values.items():
    text = text.replace("@%s@" % key, value)
for key in ("TOOLHEAD", "HEAD", "FEATURES"):
    if not values[key]:
        text = "\n".join(
            line for line in text.split("\n") if not line.startswith(key.lower() + "=")
        )
with open(target, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
PY

cat > "$PROFILE_DIR/printer.cfg" <<'EOF'
# Seed manifest for this Klipper profile.
#
# This file is a SEED: deploy_configs.sh creates it only when it is missing and
# never overwrites it. Klipper's SAVE_CONFIG appends its autosave block here.
#
# The include list itself is generated from machine.conf into profile.cfg.
[include profile.cfg]

# Runtime overrides (UUIDs, PID, input shaper, extruder calibration) come last.
[include std.config.local/*.cfg]
EOF

{
  echo "# Measured anchors for $ID. Managed file: deploy overwrites it from git."
  echo "#"
  echo "# TODO: measure the bed pivot points, safe_z_home, zero_reference_position"
  echo "# and the real travel limits, then put them here and add a line"
  echo "# '# замер YYYY-MM-DD' so check_config.py stops warning."
  echo "# Until then geometry/$(basename -- "$MODEL-${SIZE}.cfg") defaults apply."
} > "$PROFILE_DIR/anchors.cfg"

cat > "$PROFILE_DIR/machine-extras.cfg" <<'EOF'
# Machine-specific overrides that do not fit the shared catalogs.
[idle_timeout]
timeout: 1800
EOF

cat > "$PROFILE_DIR/macros.cfg" <<'EOF'
# Printer-specific macros. Shared macros are included by profile.cfg.
EOF

cat > "$PROFILE_DIR/moonraker.conf" <<EOF
[server]
host: 0.0.0.0
port: 7125
klippy_uds_address: $HOME/printer_data/comms/klippy.sock

[authorization]
trusted_clients:
    10.0.0.0/8
    127.0.0.0/8
    169.254.0.0/16
    172.16.0.0/12
    192.168.0.0/16
    FE80::/10
    ::1/128

[update_manager vorons_configs]
type: git_repo
path: ~/vorons_configs
origin: https://github.com/spectrespc/vorons_configs
primary_branch: main
EOF

{
  echo "# CAN UUIDs for profile $ID. Managed: deploy copies this to std.config.local/."
  echo "# UUIDs are entered on every flash run (scripts/flash_mcu.sh -u UUID) and"
  echo "# are never hardcoded in scripts. Read them from Katapult with:"
  echo "#   python3 ~/katapult/scripts/flashtool.py -i can0 -q"
  echo "# Replace the placeholders below before the first Klipper start."
  echo
  echo "[mcu]"
  if [[ "$EFFECTIVE_BOARD" == "manta-m8p-v1.0" ]]; then
    # The V1.0 has no CAN transceiver: the host talks to the main MCU over USB.
    echo "serial: /dev/serial/by-id/usb-Klipper_Klipper_firmware_12345-if00"
    echo "#canbus_uuid: REPLACE_WITH_MAIN_MCU_UUID   # M8P V1.0 is USB only"
  else
    echo "#serial: /dev/serial/by-id/usb-Klipper_Klipper_firmware_12345-if00"
    echo "canbus_uuid: REPLACE_WITH_MAIN_MCU_UUID"
  fi
  echo
  echo "[mcu extruder]"
  echo "canbus_uuid: REPLACE_WITH_TOOLHEAD_UUID"
  if has_feature extra_extruder; then
    echo
    echo "[mcu ext-extruder]"
    echo "canbus_uuid: REPLACE_WITH_EXT_EXTRUDER_UUID"
  fi
} > "$PROFILE_DIR/local/uuids.cfg"
touch "$PROFILE_DIR/local/.gitkeep"

"$PYTHON_BIN" "$SCRIPT_DIR/render_profile.py" --machine-dir "$PROFILE_DIR" --write
if ! "$PYTHON_BIN" "$SCRIPT_DIR/check_config.py" --machine "$PROFILE_DIR"; then
  echo "ERROR: the new profile does not validate; fix it before deploying." >&2
  exit 1
fi

cat <<EOF
Created profile $ID in $PROFILE_DIR
Key reference: docs/PROFILES.md
Next steps:
  1. Replace the UUID placeholders in $PROFILE_DIR/local/uuids.cfg
     (read real UUIDs with flashtool.py -q; flash_mcu.sh asks for them on run).
  2. Measure the machine and fill $PROFILE_DIR/anchors.cfg.
  3. Commit the profile, then deploy on the printer:
       scripts/deploy_configs.sh -p $ID -b
EOF