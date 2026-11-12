#!/usr/bin/env bash
# Rebuild and flash every Klipper MCU after a Klipper update.
#
# The main board is a USB-CAN bridge: the host's can0 interface is provided by
# that board itself.  Therefore the CAN nodes (toolhead and extra extruder) are
# flashed first over CAN, and the bridge is flashed last through its bootloader
# over USB (Katapult) or DFU.  Flashing the bridge over can0 would remove the
# interface in the middle of the upload.
#
# On an interactive run the UUIDs are read from the deployed uuids.cfg, never
# from this script.  --auto is intended for the systemd path/timer hook and
# additionally compares the Klipper commit with the last flashed commit.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROFILE="voron-t"
PROFILE_DIR=""
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
KATAPULT_DIR="${KATAPULT_DIR:-$HOME/katapult}"
PRINTER_DATA_CONFIG="${PRINTER_DATA_CONFIG:-$HOME/printer_data/config}"
UUID_FILE=""
CAN_IFACE="can0"
OUT_ROOT="${OUT_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/klipper-firmware/out}"
STAMP_FILE="${STAMP_FILE:-${XDG_CACHE_HOME:-$HOME/.cache}/klipper-firmware/last-commit}"
PYTHON_BIN="${PYTHON:-python3}"
JOBS=4
AUTO=0
DRY_RUN=0
FORCE=0
NO_BUILD=0
BUILD_ONLY=0
SKIP_MAIN=0
SKIP_EXTRUDER=0
SKIP_EXTRA=0
MAIN_CONFIG=""
EXTRUDER_CONFIG=""
EXTRA_CONFIG=""
MAIN_METHOD="auto"
MAIN_DEVICE=""
WAIT_BUSY=600
TIMEOUT=30
MAIN_CONFIG_PATH=""
EXTRUDER_CONFIG_PATH=""
EXTRA_CONFIG_PATH=""
BIN_MAIN=""
BIN_EXTRUDER=""
BIN_EXTRA=""
UUID_MAIN=""
UUID_EXTRUDER=""
UUID_EXTRA=""
CURRENT_COMMIT=""
KLI_WAS_ACTIVE=0

usage() {
  cat <<'EOF'
Usage: update_firmware.sh [options]

Rebuild the Klipper firmware for the main board, toolhead and (optionally) the
extra extruder, then flash them in the order required by a USB-CAN bridge:
CAN nodes first, the bridge last through USB/DFU.

Options:
  -p, --profile ID       printer profile (default: voron-t)
  -c, --klipper-dir DIR  Klipper checkout (default: ~/klipper)
      --katapult-dir DIR Katapult checkout (default: ~/katapult)
      --printer-data DIR live printer_data/config (default: ~/printer_data/config)
      --uuids FILE       uuids.cfg (default: <live>/std.config.local/uuids.cfg,
                         then printers/<id>/local/uuids.cfg)
  -j, --jobs N           build jobs (default: 4)
      --main-config NAME     override the main Kconfig (name or path)
      --extruder-config NAME override the toolhead Kconfig
      --extra-config NAME    override the extra extruder Kconfig
      --skip-main            do not update the main board
      --skip-extruder        do not update the toolhead
      --skip-extra           do not update the extra extruder
      --main-method M        bridge upload: auto, usb or dfu (default: auto)
      --main-device DEV      explicit Katapult tty or DFU id for the bridge
      --timeout N            seconds to wait for a bootloader device (default: 30)
      --wait-busy N          seconds to wait for Moonraker idle (default: 600)
      --out-root DIR         build output root (default: ~/.cache/klipper-firmware/out)
      --no-build             reuse <out-root>/<config>/klipper.bin
      --build-only           build the binaries and exit; do not flash
      --auto                 systemd mode: skip when the Klipper commit is
                             already stamped, wait for Moonraker updates/prints
      --force                ignore the commit stamp and the printing guard
      --dry-run              print the plan and exit without building/flashing
  -h, --help                 show this help

Examples:
  scripts/update_firmware.sh --dry-run
  scripts/update_firmware.sh
  scripts/update_firmware.sh --auto
  scripts/update_firmware.sh --force --skip-extra

The UUIDs come from the deployed uuids.cfg; this script never hardcodes them.
The bridge's Katapult must support USB (Katapult-USB) or the board must fall
back to the STM32 ROM DFU.  A CAN-only Katapult on the bridge cannot be
recovered automatically because it would take can0 down with it.
EOF
}

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

as_root() {
  if (( EUID == 0 )); then
    "$@"
  else
    sudo "$@"
  fi
}

while (($#)); do
  case "$1" in
    -p|--profile)       PROFILE="${2:?missing value for $1}"; shift 2 ;;
    -c|--klipper-dir)   KLIPPER_DIR="${2:?missing value for $1}"; shift 2 ;;
    --katapult-dir)     KATAPULT_DIR="${2:?missing value for $1}"; shift 2 ;;
    --printer-data)     PRINTER_DATA_CONFIG="${2:?missing value for $1}"; shift 2 ;;
    --uuids)            UUID_FILE="${2:?missing value for $1}"; shift 2 ;;
    -j|--jobs)          JOBS="${2:?missing value for $1}"; shift 2 ;;
    --main-config)      MAIN_CONFIG="${2:?missing value for $1}"; shift 2 ;;
    --extruder-config)  EXTRUDER_CONFIG="${2:?missing value for $1}"; shift 2 ;;
    --extra-config)     EXTRA_CONFIG="${2:?missing value for $1}"; shift 2 ;;
    --skip-main)        SKIP_MAIN=1; shift ;;
    --skip-extruder)    SKIP_EXTRUDER=1; shift ;;
    --skip-extra)       SKIP_EXTRA=1; shift ;;
    --main-method)      MAIN_METHOD="${2:?missing value for $1}"; shift 2 ;;
    --main-device)      MAIN_DEVICE="${2:?missing value for $1}"; shift 2 ;;
    --timeout)          TIMEOUT="${2:?missing value for $1}"; shift 2 ;;
    --wait-busy)        WAIT_BUSY="${2:?missing value for $1}"; shift 2 ;;
    --out-root)         OUT_ROOT="${2:?missing value for $1}"; shift 2 ;;
    --no-build)         NO_BUILD=1; shift ;;
    --build-only)       BUILD_ONLY=1; shift ;;
    --auto)             AUTO=1; shift ;;
    --force)            FORCE=1; shift ;;
    --dry-run)          DRY_RUN=1; shift ;;
    -h|--help)          usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$MAIN_METHOD" in
  auto|usb|dfu) ;;
  *) die "--main-method must be auto, usb or dfu (got '$MAIN_METHOD')" ;;
esac
for value in "$JOBS" "$TIMEOUT" "$WAIT_BUSY"; do
  [[ "$value" =~ ^[0-9]+$ ]] || die "expected a positive integer, got '$value'"
done
(( JOBS > 0 && TIMEOUT > 0 && WAIT_BUSY > 0 )) || die "numeric options must be positive"

PROFILE_DIR="$REPO/printers/$PROFILE"
[[ -f "$PROFILE_DIR/machine.conf" ]] || die "profile not found: $PROFILE_DIR/machine.conf"
[[ -d "$KLIPPER_DIR" ]] || die "Klipper directory not found: $KLIPPER_DIR"
[[ -f "$KATAPULT_DIR/scripts/flashtool.py" ]] || die \
  "Katapult flashtool not found: $KATAPULT_DIR/scripts/flashtool.py (git clone https://github.com/Arksine/katapult ~/katapult)"
[[ -x "$SCRIPT_DIR/build_mcu.sh" ]] || die "missing $SCRIPT_DIR/build_mcu.sh"
[[ -x "$SCRIPT_DIR/flash_mcu.sh" ]] || die "missing $SCRIPT_DIR/flash_mcu.sh"

# Systemd serializes its path/timer activations, but a manual run can overlap
# with the service.  The lock is world-writable so root and the owner share it.
if (( ! DRY_RUN )) && command -v flock >/dev/null 2>&1; then
  LOCK_FILE="${LOCK_FILE:-/tmp/klipper-firmware-update.lock}"
  (umask 000; : >>"$LOCK_FILE")
  exec 9>>"$LOCK_FILE"
  flock -n 9 || die "another firmware update is already running"
fi

machine_value() {
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$PROFILE_DIR/machine.conf" \
    | tail -n1 | tr -d '\r'
}

features_value() {
  machine_value features | tr -d '[:space:]'
}

has_feature() {
  [[ ",$(features_value)," == *",$1,"* ]]
}

resolve_config() {
  local value="$1"
  [[ "$value" == */* ]] || value="std.compil.configs/$value"
  [[ "$value" = /* ]] || value="$REPO/$value"
  printf '%s\n' "$value"
}

derive_configs() {
  local board model toolhead
  board="$(machine_value board)"
  model="$(machine_value model)"
  if [[ -z "$board" ]]; then
    case "$model" in
      trident) board="manta-m5p" ;;
      v24)     board="manta-m8p" ;;
      *) die "machine.conf has no board and model '$model' has no default" ;;
    esac
  fi

  if (( ! SKIP_MAIN )); then
    if [[ -z "$MAIN_CONFIG" ]]; then
      case "$board" in
        manta-m5p) MAIN_CONFIG="config_m5p_v1" ;;
        manta-m8p) MAIN_CONFIG="config_m8p_v2" ;;
        *) die "unknown board '$board'; pass --main-config" ;;
      esac
    fi
    MAIN_CONFIG_PATH="$(resolve_config "$MAIN_CONFIG")"
    [[ -f "$MAIN_CONFIG_PATH" ]] || die "main Kconfig not found: $MAIN_CONFIG_PATH"
  fi

  toolhead="$(machine_value toolhead)"
  if (( ! SKIP_EXTRUDER )) && [[ -n "$toolhead" || -n "$EXTRUDER_CONFIG" ]]; then
    if [[ -z "$EXTRUDER_CONFIG" ]]; then
      case "$toolhead" in
        sht36-v3)   EXTRUDER_CONFIG="config_sht36_v3" ;;
        ebb36-v1.2) EXTRUDER_CONFIG="config_ebb36_v1.2-sb2209_v1" ;;
        *) die "no build config for toolhead '$toolhead'; pass --extruder-config" ;;
      esac
    fi
    EXTRUDER_CONFIG_PATH="$(resolve_config "$EXTRUDER_CONFIG")"
    [[ -f "$EXTRUDER_CONFIG_PATH" ]] || die "toolhead Kconfig not found: $EXTRUDER_CONFIG_PATH"
  fi

  if (( ! SKIP_EXTRA )) && { [[ -n "$EXTRA_CONFIG" ]] || has_feature extra_extruder; }; then
    [[ -n "$EXTRA_CONFIG" ]] || EXTRA_CONFIG="config_sht42_v1"
    EXTRA_CONFIG_PATH="$(resolve_config "$EXTRA_CONFIG")"
    [[ -f "$EXTRA_CONFIG_PATH" ]] || die "extra extruder Kconfig not found: $EXTRA_CONFIG_PATH"
  fi
}

resolve_uuid_file() {
  if [[ -n "$UUID_FILE" ]]; then
    [[ -f "$UUID_FILE" ]] || die "uuids file not found: $UUID_FILE"
    return
  fi
  local candidate
  for candidate in \
    "$PRINTER_DATA_CONFIG/std.config.local/uuids.cfg" \
    "$PROFILE_DIR/local/uuids.cfg"; do
    if [[ -f "$candidate" ]]; then
      UUID_FILE="$candidate"
      return
    fi
  done
  die "uuids.cfg not found; pass --uuids"
}

uuid_for() {
  "$PYTHON_BIN" - "$UUID_FILE" "$1" <<'PY'
import configparser
import sys

parser = configparser.RawConfigParser(
    strict=False, inline_comment_prefixes=("#", ";")
)
parser.read(sys.argv[1])
try:
    value = parser.get(sys.argv[2], "canbus_uuid")
except (configparser.Error, KeyError):
    value = ""
print(value.strip().lower())
PY
}

read_uuid() {
  local section="$1" value
  value="$(uuid_for "$section")"
  [[ "$value" =~ ^[0-9a-f]{12}$ ]] || die \
    "no valid canbus_uuid for [$section] in $UUID_FILE"
  printf '%s\n' "$value"
}

resolve_uuids() {
  resolve_uuid_file
  (( SKIP_MAIN )) || UUID_MAIN="$(read_uuid 'mcu')"
  if [[ -n "$EXTRUDER_CONFIG_PATH" ]]; then
    UUID_EXTRUDER="$(read_uuid 'mcu extruder')"
  fi
  if [[ -n "$EXTRA_CONFIG_PATH" ]]; then
    UUID_EXTRA="$(read_uuid 'mcu ext-extruder')"
  fi
}

moonraker_state() {
  curl -fsS --max-time 2 \
    'http://127.0.0.1:7125/printer/objects/query?print_stats' 2>/dev/null \
    | "$PYTHON_BIN" -c \
      'import json,sys; print(json.load(sys.stdin)["result"]["status"]["print_stats"]["state"])' \
      2>/dev/null || true
}

moonraker_busy() {
  curl -fsS --max-time 2 'http://127.0.0.1:7125/machine/update/status' 2>/dev/null \
    | "$PYTHON_BIN" -c \
      'import json,sys; print(json.load(sys.stdin)["result"].get("busy", False))' \
      2>/dev/null || true
}

wait_for_idle() {
  local deadline=$((SECONDS + WAIT_BUSY)) state busy
  while (( SECONDS < deadline )); do
    state="$(moonraker_state)"
    busy="$(moonraker_busy)"
    if [[ -z "$state" && -z "$busy" ]]; then
      if (( AUTO )); then
        log "Moonraker is unavailable; retrying"
        sleep 5
        continue
      fi
      log "WARNING: Moonraker is unavailable; continuing without the print guard"
      return 0
    fi
    if [[ "$state" == "printing" || "$state" == "paused" ]]; then
      if (( FORCE )); then
        log "WARNING: --force while the printer is $state"
        return 0
      fi
      if (( ! AUTO )); then
        die "printer is $state; aborting (use --force to override)"
      fi
      log "Printer is $state; waiting"
      sleep 10
      continue
    fi
    if [[ "$busy" == "True" ]]; then
      log "Moonraker is applying an update; waiting"
      sleep 5
      continue
    fi
    return 0
  done
  die "timed out waiting for the printer and Moonraker to be idle"
}

build_one() {
  local name="$1" cfg="$2" out bin log_file build_cfg
  out="$OUT_ROOT/$name"
  bin="$out/klipper.bin"
  build_cfg="$OUT_ROOT/kconfig-$name"
  if (( NO_BUILD )); then
    [[ -f "$bin" ]] || die "binary not found: $bin (omit --no-build to build)"
    printf '%s\n' "$bin"
    return 0
  fi
  mkdir -p "$OUT_ROOT"
  log_file="$OUT_ROOT/build-$name.log"
  log "Building $name"
  if (( DRY_RUN )); then
    printf '+ cp %s %s\n' "$cfg" "$build_cfg" >&2
    printf '+ make -C %s KCONFIG_CONFIG=%s olddefconfig\n' \
      "$KLIPPER_DIR" "$build_cfg" >&2
    printf '+ %s -c %s -o %s --clean -j %s --print-bin\n' \
      "$SCRIPT_DIR/build_mcu.sh" "$build_cfg" "$out" "$JOBS" >&2
    printf '%s\n' "$bin"
    return 0
  fi
  # Build from a copy: Klipper's olddefconfig may add derived symbols and must
  # not dirty the committed snapshots in std.compil.configs/ (the service runs
  # as root, so a rewrite would also change file ownership).
  cp -p -- "$cfg" "$build_cfg"
  chmod u+w "$build_cfg"
  if ! make -C "$KLIPPER_DIR" "KCONFIG_CONFIG=$build_cfg" "OUT=$out/" \
      olddefconfig >>"$log_file" 2>&1; then
    tail -n 80 "$log_file" >&2
    die "Kconfig sync failed: $name (log: $log_file)"
  fi
  if ! "$SCRIPT_DIR/build_mcu.sh" -c "$build_cfg" -o "$out" --clean \
      -j "$JOBS" --print-bin >>"$log_file" 2>&1; then
    tail -n 80 "$log_file" >&2
    die "build failed: $name (log: $log_file)"
  fi
  tail -n 5 "$log_file" >&2
  bin="$(tail -n1 "$log_file")"
  [[ -f "$bin" ]] || die "build did not produce $bin (log: $log_file)"
  printf '%s\n' "$bin"
}

build_all() {
  if [[ -n "$MAIN_CONFIG_PATH" ]]; then
    BIN_MAIN="$(build_one "$(basename -- "$MAIN_CONFIG_PATH")" "$MAIN_CONFIG_PATH")"
  fi
  if [[ -n "$EXTRUDER_CONFIG_PATH" ]]; then
    BIN_EXTRUDER="$(build_one "$(basename -- "$EXTRUDER_CONFIG_PATH")" "$EXTRUDER_CONFIG_PATH")"
  fi
  if [[ -n "$EXTRA_CONFIG_PATH" ]]; then
    BIN_EXTRA="$(build_one "$(basename -- "$EXTRA_CONFIG_PATH")" "$EXTRA_CONFIG_PATH")"
  fi
}

preflight() {
  (( DRY_RUN || BUILD_ONLY )) && return 0
  "$PYTHON_BIN" -c 'import serial' 2>/dev/null || die \
    "python3-serial is missing; install it with: sudo apt install python3-serial"
  if [[ "$MAIN_METHOD" == "dfu" ]]; then
    command -v dfu-util >/dev/null 2>&1 || die \
      "--main-method dfu needs dfu-util (sudo apt install dfu-util)"
  fi
}

start_klipper() {
  if (( KLI_WAS_ACTIVE )); then
    log "Starting klipper"
    as_root service klipper start || log "WARNING: failed to start klipper"
  fi
}

stop_klipper() {
  if systemctl is-active --quiet klipper; then
    KLI_WAS_ACTIVE=1
    log "Stopping klipper"
    as_root service klipper stop
  else
    log "Klipper is not active; continuing"
  fi
}

flash_all() {
  if [[ -n "$BIN_EXTRA" ]]; then
    log "Flashing extra extruder $UUID_EXTRA"
    "$SCRIPT_DIR/flash_mcu.sh" can --no-service -i "$CAN_IFACE" \
      -u "$UUID_EXTRA" -f "$BIN_EXTRA"
  fi
  if [[ -n "$BIN_EXTRUDER" ]]; then
    log "Flashing toolhead $UUID_EXTRUDER"
    "$SCRIPT_DIR/flash_mcu.sh" can --no-service -i "$CAN_IFACE" \
      -u "$UUID_EXTRUDER" -f "$BIN_EXTRUDER"
  fi
  if [[ -n "$BIN_MAIN" ]]; then
    log "Flashing main bridge $UUID_MAIN via $MAIN_METHOD"
    local -a args=(
      bridge --no-service -i "$CAN_IFACE" -u "$UUID_MAIN" -f "$BIN_MAIN"
      --method "$MAIN_METHOD" --timeout "$TIMEOUT" -c "$MAIN_CONFIG_PATH"
    )
    if [[ -n "$MAIN_DEVICE" ]]; then
      args+=(-d "$MAIN_DEVICE")
    fi
    "$SCRIPT_DIR/flash_mcu.sh" "${args[@]}"
  fi
}

print_plan() {
  log "Profile: $PROFILE"
  log "Klipper: $KLIPPER_DIR"
  log "UUIDs:   $UUID_FILE"
  [[ -n "$MAIN_CONFIG_PATH" ]] && log "Main:    $(basename "$MAIN_CONFIG_PATH") UUID $UUID_MAIN"
  [[ -n "$EXTRUDER_CONFIG_PATH" ]] && log "Toolhead $(basename "$EXTRUDER_CONFIG_PATH") UUID $UUID_EXTRUDER"
  [[ -n "$EXTRA_CONFIG_PATH" ]] && log "Extra:   $(basename "$EXTRA_CONFIG_PATH") UUID $UUID_EXTRA"
  if [[ -n "$BIN_EXTRA" ]]; then
    printf '+ %s can --no-service -i %s -u %s -f %s\n' \
      "$SCRIPT_DIR/flash_mcu.sh" "$CAN_IFACE" "$UUID_EXTRA" "$BIN_EXTRA"
  fi
  if [[ -n "$BIN_EXTRUDER" ]]; then
    printf '+ %s can --no-service -i %s -u %s -f %s\n' \
      "$SCRIPT_DIR/flash_mcu.sh" "$CAN_IFACE" "$UUID_EXTRUDER" "$BIN_EXTRUDER"
  fi
  if [[ -n "$BIN_MAIN" ]]; then
    printf '+ %s bridge --no-service -i %s -u %s -f %s --method %s -c %s\n' \
      "$SCRIPT_DIR/flash_mcu.sh" "$CAN_IFACE" "$UUID_MAIN" "$BIN_MAIN" \
      "$MAIN_METHOD" "$MAIN_CONFIG_PATH"
  fi
}

# --- main --------------------------------------------------------------------

derive_configs
if [[ -z "$MAIN_CONFIG_PATH" && -z "$EXTRUDER_CONFIG_PATH" && -z "$EXTRA_CONFIG_PATH" ]]; then
  die "nothing to update: all MCUs are skipped (check --skip-* options)"
fi
resolve_uuids

if (( AUTO )); then
  CURRENT_COMMIT="$(git -C "$KLIPPER_DIR" rev-parse HEAD 2>/dev/null)" || \
    die "cannot read the Klipper commit in $KLIPPER_DIR"
  if (( ! FORCE )) && [[ -f "$STAMP_FILE" ]] && \
      [[ "$(cat "$STAMP_FILE")" == "$CURRENT_COMMIT" ]]; then
    log "Klipper $CURRENT_COMMIT is already flashed; nothing to do"
    exit 0
  fi
fi

if (( DRY_RUN )); then
  log "DRY RUN: no build, no flash, no service changes"
  build_all
  print_plan
  exit 0
fi

preflight
wait_for_idle
build_all
if (( BUILD_ONLY )); then
  log "Build complete; --build-only set, not flashing"
  exit 0
fi
# The build may take a while; re-check right before stopping Klipper.
wait_for_idle
stop_klipper
trap start_klipper EXIT
flash_all

if (( AUTO )); then
  mkdir -p "$(dirname -- "$STAMP_FILE")"
  printf '%s\n' "$CURRENT_COMMIT" > "$STAMP_FILE"
  log "Stamped $CURRENT_COMMIT in $STAMP_FILE"
fi

log "Firmware update complete"