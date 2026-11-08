#!/usr/bin/env bash
# Create a new printer profile under printers/<id> from the fleet axes and
# render its include manifest. The new profile is validated offline; no file is
# deployed until deploy_configs.sh is run.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

ID=""
SIZE=""
MODEL=""
BOARD=""
XY_STEP="0.9"
TOOLHEAD="sht36-v3"
HEAD="HGX.8T"
FEATURES=""
FEATURES_SET=0
FRAME_W=""
FRAME_D=""
FORCE=0

usage() {
  cat <<'EOF'
Usage: new_machine.sh -p ID --size N --model MODEL [options]

Creates printers/<ID>/ with machine.conf, seed printer.cfg, anchors.cfg,
machine-extras.cfg, macros.cfg, moonraker.conf and an empty local/ dir, then
renders profile.cfg and validates it with check_config.py --machine.

Required:
  -p, --printer ID    new profile name under printers/
      --size N        bed size: 150, 200, 250, 300, 350
      --model MODEL   trident (3Z, z_tilt) or v24 (4Z, quad_gantry_level)

Optional:
      --board NAME    manta-m5p or manta-m8p (default: per model)
      --xy-step V     0.9 or 1.8 (default: 0.9)
      --toolhead NAME toolhead board module (default: sht36-v3, empty to omit)
      --head NAME     extruder head module (default: HGX.8T, empty to omit)
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
    --toolhead)   TOOLHEAD="${2-}"; shift 2 ;;
    --head)       HEAD="${2-}"; shift 2 ;;
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

{
  echo "# Axes and features for profile $ID. Read by scripts/render_profile.py."
  echo "# Fill the measured anchors in anchors.cfg after commissioning."
  echo "size=$SIZE"
  echo "model=$MODEL"
  if [[ -n "$BOARD" ]]; then
    echo "board=$BOARD"
  fi
  echo "xy_step=$XY_STEP"
  if [[ -n "$TOOLHEAD" ]]; then
    echo "toolhead=$TOOLHEAD"
  fi
  if [[ -n "$HEAD" ]]; then
    echo "head=$HEAD"
  fi
  echo "frame_w=$FRAME_W"
  echo "frame_d=$FRAME_D"
  if [[ -n "$FEATURES" ]]; then
    echo "features=$FEATURES"
  fi
} > "$PROFILE_DIR/machine.conf"

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
  echo "#serial: /dev/serial/by-id/usb-Klipper_Klipper_firmware_12345-if00"
  echo "canbus_uuid: REPLACE_WITH_MAIN_MCU_UUID"
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
Next steps:
  1. Replace the UUID placeholders in $PROFILE_DIR/local/uuids.cfg
     (read real UUIDs with flashtool.py -q; flash_mcu.sh asks for them on run).
  2. Measure the machine and fill $PROFILE_DIR/anchors.cfg.
  3. Commit the profile, then deploy on the printer:
       scripts/deploy_configs.sh -p $ID -b
EOF