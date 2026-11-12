#!/usr/bin/env bash
# Flash a Klipper binary to one MCU of the fleet.
#
# Commands map to the MCU kinds in README "Flashing controllers":
#   can     Katapult over CAN (toolhead, extra extruder, non-bridge main board)
#   bridge  USB-CAN bridge MCU: request bootloader over CAN, upload over USB/DFU
#   query   list Katapult CAN nodes and their UUIDs
#   serial  Katapult over a USB serial port (/dev/ttyACM0)
#   dfu     STM32 DFU, first-time Katapult install (mass erase!)
#   linux   Linux host MCU built and installed with "make flash"
#
# The UUID is never hardcoded: pass it with -u or type it at the prompt. It is
# taken from printers/<profile>/local/uuids.cfg or flashtool.py -q.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
KATAPULT_DIR="${KATAPULT_DIR:-$HOME/katapult}"
PYTHON_BIN="${PYTHON:-python3}"

COMMAND=""
BIN=""
UUID=""
IFACE="can0"
DEVICE=""
BAUD="250000"
CONFIG=""
OUT=""
JOBS="4"
DO_SETUP=0
DRY_RUN=0
NO_SERVICE=0
TIMEOUT=30
BRIDGE_METHOD="auto"
APP_ADDRESS=""

usage() {
  cat <<'EOF'
Usage: flash_mcu.sh [COMMAND] [options]

Flash a Klipper binary to one MCU.

Commands:
  can       (default) flash one CAN node through Katapult
  bridge    update a USB-CAN bridge MCU: request the bootloader over CAN, then
            upload over USB (Katapult) or STM32 DFU without mass erase
  query     list CAN nodes and UUIDs (Katapult, no service stop)
  serial    flash over serial through Katapult (/dev/ttyACM0)
  dfu       flash through STM32 DFU; mass-erase wipes the bootloader
  linux     build and install the Linux host MCU ("make flash")

Options:
  -f, --file BIN       firmware binary (klipper.bin/katapult.bin)
  -u, --uuid UUID      CAN UUID, 12 lowercase hex chars; prompted if omitted
  -i, --interface IF   CAN interface (default: can0)
  -d, --device DEV     serial port (default: auto for "bridge", /dev/ttyACM0
                       for "serial") or DFU id (default: 0483:df11)
  -b, --baud N         serial baud rate (default: 250000)
  -c, --config FILE    Kconfig for "linux" and for the DFU app address
  -o, --out DIR        "linux" build directory (default: ~/klipper/out/config_linux)
  -j, --jobs N         "linux" build jobs (default: 4)
      --method M       "bridge" bootloader upload: auto, usb or dfu (default: auto)
      --app-address A  "bridge" DFU application address (default: from the
                       Kconfig CONFIG_FLASH_APPLICATION_ADDRESS)
      --timeout N      seconds to wait for the bootloader device (default: 30)
      --no-service     do not stop/start klipper (the caller manages it)
      --setup          "linux" one-time host setup: klipper-mcu.service,
                       sysctl realtime limit, tty group (idempotent)
      --dry-run        print the commands and exit without executing
  -h, --help           show this help

Examples:
  flash_mcu.sh query
  flash_mcu.sh can -u 7082e04ea1c9 -f ~/klipper/out/config_sht42_v1/klipper.bin
  flash_mcu.sh bridge -u 993331fd8db1 -f ~/klipper/out/config_m5p_v1/klipper.bin
  flash_mcu.sh serial -f ~/klipper/out/config_sht36_v3/klipper.bin
  flash_mcu.sh dfu -f ~/klipper/out/config_sht42_katapult.v1/katapult.bin
  flash_mcu.sh linux --setup
  flash_mcu.sh linux

For a USB-CAN bridge the host CAN interface is provided by the board itself,
so it cannot be flashed over that same interface: "bridge" resets it into the
bootloader over CAN and uploads the application over USB or DFU.

Katapult is expected in ~/katapult; override with KATAPULT_DIR. The shell is
interactive by design: sudo and the UUID prompt need a console.
EOF
}

run() {
  if (( DRY_RUN )); then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_file() {
  [[ -n "$BIN" ]] || die "firmware binary is required (-f)"
  if (( ! DRY_RUN )) && [[ ! -f "$BIN" ]]; then
    die "binary not found: $BIN"
  fi
}

require_katapult() {
  if (( DRY_RUN )); then
    return 0
  fi
  [[ -f "$KATAPULT_DIR/scripts/flashtool.py" ]] || {
    cat >&2 <<EOF
ERROR: Katapult flashtool not found: $KATAPULT_DIR/scripts/flashtool.py
Install it with:
  git clone https://github.com/Arksine/katapult ~/katapult
  sudo apt install python3-serial
EOF
    exit 1
  }
  "$PYTHON_BIN" -c 'import serial' 2>/dev/null || die \
    "python3-serial is missing; install it with: sudo apt install python3-serial"
}

resolve_uuid() {
  if [[ -z "$UUID" ]] && (( ! DRY_RUN )); then
    if [[ -t 0 ]]; then
      read -r -p "CAN UUID (12 hex chars, from local/uuids.cfg or 'query'): " UUID
    else
      die "CAN UUID is required (-u); run 'flash_mcu.sh query' to list nodes"
    fi
  fi
  if [[ -n "$UUID" && ! "$UUID" =~ ^[0-9a-f]{12}$ ]]; then
    die "invalid CAN UUID '$UUID' (expected 12 lowercase hex chars)"
  fi
}

start_klipper_again() {
  if (( KLI_WAS_ACTIVE )); then
    sudo service klipper start
  fi
}

# --- commands ----------------------------------------------------------------

cmd_can() {
  resolve_uuid
  require_file
  require_katapult
  local uuid="${UUID:-<uuid>}"
  if (( DRY_RUN )); then
    if (( ! NO_SERVICE )); then
      printf '+ sudo service klipper stop   # only if klipper is active\n'
    fi
    printf '+ %s %s -i %s -u %s -f %s -v\n' \
      "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" "$IFACE" "$uuid" "$BIN"
    if (( ! NO_SERVICE )); then
      printf '+ sudo service klipper start  # restore the previous state\n'
    fi
    return 0
  fi
  if (( ! NO_SERVICE )) && systemctl is-active --quiet klipper; then
    KLI_WAS_ACTIVE=1
    trap start_klipper_again EXIT
    sudo service klipper stop
  fi
  "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" \
    -i "$IFACE" -u "$UUID" -f "$BIN" -v
}

cmd_query() {
  require_katapult
  run "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" -i "$IFACE" -q
}

# --- USB-CAN bridge bootloader ------------------------------------------------

is_klipper_bridge_interface() {
  local dev net mfr
  for dev in /sys/bus/usb/devices/*; do
    [[ -f "$dev/idVendor" && -f "$dev/idProduct" ]] || continue
    [[ "$(cat "$dev/idVendor")" == "1d50" ]] || continue
    [[ "$(cat "$dev/idProduct")" == "606f" ]] || continue
    [[ -f "$dev/manufacturer" ]] || continue
    mfr="$(<"$dev/manufacturer")"
    [[ "${mfr,,}" == "klipper" ]] || continue
    for net in "$dev"/*/net/"$IFACE"; do
      [[ -e "$net" ]] && return 0
    done
  done
  return 1
}

usb_id_present() {
  local dev
  for dev in /sys/bus/usb/devices/*; do
    [[ -f "$dev/idVendor" && -f "$dev/idProduct" ]] || continue
    [[ "$(cat "$dev/idVendor")" == "$1" ]] || continue
    [[ "$(cat "$dev/idProduct")" == "$2" ]] || continue
    return 0
  done
  return 1
}

katapult_tty() {
  local link dev ttydir
  for link in /dev/serial/by-id/*[Kk]atapult*; do
    [[ -e "$link" ]] || continue
    printf '%s\n' "$link"
    return 0
  done
  # Some Katapult builds expose only a ttyACM node; identify it by USB id.
  for dev in /sys/bus/usb/devices/*; do
    [[ -f "$dev/idVendor" && -f "$dev/idProduct" ]] || continue
    [[ "$(cat "$dev/idVendor")" == "1d50" ]] || continue
    [[ "$(cat "$dev/idProduct")" == "6177" ]] || continue
    for ttydir in "$dev"/*/tty/tty* "$dev"/tty/tty*; do
      [[ -e "$ttydir" ]] || continue
      printf '/dev/%s\n' "${ttydir##*/}"
      return 0
    done
  done
  return 1
}

dfu_app_address() {
  local cfg="$1" value=""
  if [[ -n "$cfg" && -f "$cfg" ]]; then
    value="$(sed -n 's/^CONFIG_FLASH_APPLICATION_ADDRESS=//p' "$cfg" | tail -n1)"
  fi
  printf '%s\n' "${value:-0x08002000}"
}

# Print "usb:<device>" or "dfu:<id>" once the bridge bootloader appears.
find_bridge_bootloader() {
  local deadline=$((SECONDS + TIMEOUT)) dev
  if [[ -n "$DEVICE" ]]; then
    if [[ "$DEVICE" == *:* ]]; then
      printf 'dfu:%s\n' "$DEVICE"
      return 0
    fi
    [[ -e "$DEVICE" ]] || DEVICE="/dev/$DEVICE"
    printf 'usb:%s\n' "$DEVICE"
    return 0
  fi
  while (( SECONDS < deadline )); do
    if [[ "$BRIDGE_METHOD" != "dfu" ]] && dev="$(katapult_tty)"; then
      printf 'usb:%s\n' "$dev"
      return 0
    fi
    if [[ "$BRIDGE_METHOD" != "usb" ]] && usb_id_present 0483 df11; then
      printf 'dfu:0483:df11\n'
      return 0
    fi
    sleep 0.5
  done
  return 1
}

wait_for_can_interface() {
  local deadline=$((SECONDS + TIMEOUT))
  command -v ip >/dev/null 2>&1 || return 0
  while (( SECONDS < deadline )); do
    if ip link show "$IFACE" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

cmd_bridge() {
  resolve_uuid
  require_file
  require_katapult
  case "$BRIDGE_METHOD" in
    auto|usb|dfu) ;;
    *) die "--method must be auto, usb or dfu (got '$BRIDGE_METHOD')" ;;
  esac

  local config_path="" target
  if [[ -n "$CONFIG" ]]; then
    [[ "$CONFIG" = /* ]] || CONFIG="$REPO/$CONFIG"
    [[ -f "$CONFIG" ]] || die "Kconfig not found: $CONFIG"
    config_path="$CONFIG"
  fi
  [[ -n "$APP_ADDRESS" ]] || APP_ADDRESS="$(dfu_app_address "$config_path")"

  if (( DRY_RUN )); then
    if (( ! NO_SERVICE )); then
      printf '+ sudo service klipper stop   # only if klipper is active\n'
    fi
    printf '+ check that %s is a Klipper USB-CAN bridge\n' "$IFACE"
    printf '+ %s %s -i %s -u %s -r -v\n' \
      "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" "$IFACE" "${UUID:-<uuid>}"
    case "$BRIDGE_METHOD" in
      usb) target="Katapult USB" ;;
      dfu) target="DFU 0483:df11" ;;
      *)   target="Katapult USB or DFU 0483:df11 (auto)" ;;
    esac
    printf '+ wait up to %ss for %s\n' "$TIMEOUT" "$target"
    if [[ "$BRIDGE_METHOD" != "dfu" ]]; then
      printf '+ %s %s -d <katapult-tty> -b %s -f %s\n' \
        "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" "$BAUD" "$BIN"
    fi
    if [[ "$BRIDGE_METHOD" != "usb" ]]; then
      printf '+ sudo dfu-util -R -a 0 -s %s:leave -D %s -d 0483:df11\n' \
        "$APP_ADDRESS" "$BIN"
    fi
    printf '+ wait up to %ss for CAN interface %s\n' "$TIMEOUT" "$IFACE"
    if (( ! NO_SERVICE )); then
      printf '+ sudo service klipper start  # restore the previous state\n'
    fi
    return 0
  fi

  if (( ! NO_SERVICE )) && systemctl is-active --quiet klipper; then
    KLI_WAS_ACTIVE=1
    trap start_klipper_again EXIT
    sudo service klipper stop
  fi

  is_klipper_bridge_interface || die \
    "$IFACE is not provided by a Klipper USB-CAN bridge; use 'can' for a normal CAN node"

  printf 'Requesting the bootloader for %s on %s\n' "$UUID" "$IFACE"
  "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" \
    -i "$IFACE" -u "$UUID" -r -v

  local target kind device
  target="$(find_bridge_bootloader)" || die \
    "bootloader device did not appear within ${TIMEOUT}s; the bridge may need a power cycle or a USB/DFU-capable Katapult"
  kind="${target%%:*}"
  device="${target#*:}"
  case "$kind" in
    usb)
      printf 'Uploading over Katapult USB: %s\n' "$device"
      "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" \
        -d "$device" -b "$BAUD" -f "$BIN"
      ;;
    dfu)
      command -v dfu-util >/dev/null 2>&1 || die \
        "dfu-util is missing; install it with: sudo apt install dfu-util"
      printf 'Uploading over DFU at %s (bootloader preserved)\n' "$APP_ADDRESS"
      sudo dfu-util -R -a 0 -s "${APP_ADDRESS}:leave" -D "$BIN" -d "$device"
      ;;
  esac

  wait_for_can_interface || die \
    "firmware uploaded but CAN interface $IFACE did not return; check the board and Klipper bridge flash"
  printf 'Bridge %s updated; %s is available again\n' "$UUID" "$IFACE"
}

cmd_serial() {
  require_file
  require_katapult
  [[ -n "$DEVICE" ]] || DEVICE="/dev/ttyACM0"
  run "$PYTHON_BIN" "$KATAPULT_DIR/scripts/flashtool.py" \
    -d "$DEVICE" -b "$BAUD" -f "$BIN"
}

cmd_dfu() {
  require_file
  [[ -n "$DEVICE" ]] || DEVICE="0483:df11"
  if (( ! DRY_RUN )); then
    cat >&2 <<'EOF'
WARNING: DFU mass-erase wipes the whole flash, including the Katapult
bootloader. Use it only for the first bootloader install on a blank board;
later firmware updates go through "can" (Katapult) instead.
EOF
    local answer=""
    read -r -p "Type 'yes' to mass-erase and flash: " answer
    [[ "$answer" == "yes" ]] || die "aborted by user"
  fi
  run sudo dfu-util -R -a 0 -s 0x08000000:mass-erase:force:leave \
    -D "$BIN" -d "$DEVICE"
}

cmd_linux_setup() {
  [[ -d "$KLIPPER_DIR" ]] || die "Klipper directory not found: $KLIPPER_DIR"
  [[ -f "$KLIPPER_DIR/scripts/klipper-mcu.service" ]] || \
    die "missing $KLIPPER_DIR/scripts/klipper-mcu.service"
  run sudo install -m 0644 "$KLIPPER_DIR/scripts/klipper-mcu.service" \
    /etc/systemd/system/klipper-mcu.service
  run sudo systemctl daemon-reload
  run sudo systemctl enable klipper-mcu
  if (( DRY_RUN )); then
    printf "+ printf '%%s\\\\n' 'kernel.sched_rt_runtime_us = -1'"
    printf ' | sudo tee /etc/sysctl.d/10-disable-rt-group-limit.conf\n'
  else
    # The redirect must run as root, so tee is used instead of "sudo echo >".
    printf '%s\n' 'kernel.sched_rt_runtime_us = -1' | \
      sudo tee /etc/sysctl.d/10-disable-rt-group-limit.conf >/dev/null
  fi
  run sudo sysctl -w kernel.sched_rt_runtime_us=-1
  run sudo usermod -a -G tty "$USER"
}

cmd_linux() {
  [[ -d "$KLIPPER_DIR" ]] || die "Klipper directory not found: $KLIPPER_DIR"
  [[ -z "$CONFIG" ]] && CONFIG="$REPO/std.compil.configs/config_linux"
  [[ "$CONFIG" = /* ]] || CONFIG="$REPO/$CONFIG"
  [[ -f "$CONFIG" ]] || die "Kconfig not found: $CONFIG"
  [[ -n "$OUT" ]] || OUT="$KLIPPER_DIR/out/config_linux"
  if (( DO_SETUP )); then
    cmd_linux_setup
  fi
  run make -C "$KLIPPER_DIR" "KCONFIG_CONFIG=$CONFIG" "OUT=$OUT" \
    -j"$JOBS" flash
}

# --- argument parsing --------------------------------------------------------

if (($#)) && [[ "$1" != -* ]]; then
  COMMAND="$1"
  shift
fi
COMMAND="${COMMAND:-can}"

while (($#)); do
  case "$1" in
    -f|--file)      BIN="${2:?missing value for $1}"; shift 2 ;;
    -u|--uuid)      UUID="${2:?missing value for $1}"; shift 2 ;;
    -i|--interface) IFACE="${2:?missing value for $1}"; shift 2 ;;
    -d|--device)    DEVICE="${2:?missing value for $1}"; shift 2 ;;
    -b|--baud)      BAUD="${2:?missing value for $1}"; shift 2 ;;
    -c|--config)    CONFIG="${2:?missing value for $1}"; shift 2 ;;
    -o|--out)       OUT="${2:?missing value for $1}"; shift 2 ;;
    -j|--jobs)      JOBS="${2:?missing value for $1}"; shift 2 ;;
    --method)       BRIDGE_METHOD="${2:?missing value for $1}"; shift 2 ;;
    --app-address)  APP_ADDRESS="${2:?missing value for $1}"; shift 2 ;;
    --timeout)      TIMEOUT="${2:?missing value for $1}"; shift 2 ;;
    --no-service)   NO_SERVICE=1; shift ;;
    --setup)        DO_SETUP=1; shift ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

KLI_WAS_ACTIVE=0
if [[ ! "$TIMEOUT" =~ ^[0-9]+$ ]] || (( TIMEOUT <= 0 )); then
  die "--timeout must be a positive integer"
fi

if (( DO_SETUP )) && [[ "$COMMAND" != linux ]]; then
  die "--setup is only valid with the 'linux' command"
fi

case "$COMMAND" in
  can)    cmd_can ;;
  bridge) cmd_bridge ;;
  query)  cmd_query ;;
  serial) cmd_serial ;;
  dfu)    cmd_dfu ;;
  linux)  cmd_linux ;;
  *) echo "Unknown command: $COMMAND" >&2; usage >&2; exit 2 ;;
esac
