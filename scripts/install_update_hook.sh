#!/usr/bin/env bash
# Install the systemd path/timer units that rebuild and flash the MCUs after a
# Klipper update.  Run once with sudo; --dry-run prints the units and commands.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROFILE="voron-t"
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" ]] || TARGET_HOME="$HOME"
KLIPPER_DIR="$TARGET_HOME/klipper"
KATAPULT_DIR="$TARGET_HOME/katapult"
PRINTER_DATA_CONFIG="$TARGET_HOME/printer_data/config"
DATA_DIR="/var/lib/klipper-firmware"
DRY_RUN=0
UNINSTALL=0

SERVICE_NAME="klipper-firmware-update.service"
PATH_NAME="klipper-firmware-update.path"
TIMER_NAME="klipper-firmware-update.timer"
UNIT_DIR="/etc/systemd/system"

usage() {
  cat <<'EOF'
Usage: install_update_hook.sh [options]

Installs a systemd path unit (watching Klipper git refs) and a retry timer that
run scripts/update_firmware.sh --auto after a Klipper update.

Options:
  -p, --profile ID       printer profile (default: voron-t)
      --klipper-dir DIR  Klipper checkout (default: <user home>/klipper)
      --katapult-dir DIR Katapult checkout (default: <user home>/katapult)
      --printer-data DIR live printer_data/config (default: <user home>/printer_data/config)
      --data-dir DIR     state/build directory (default: /var/lib/klipper-firmware)
      --uninstall        disable and remove the units (state is kept)
      --dry-run          print the units and commands, change nothing
  -h, --help             show this help

The units run as root because flashing and service control need it.  The
installer stamps the current Klipper commit, so installing the hook does not
flash anything immediately; the next Klipper update does.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    -p|--profile)       PROFILE="${2:?missing value for $1}"; shift 2 ;;
    --klipper-dir)      KLIPPER_DIR="${2:?missing value for $1}"; shift 2 ;;
    --katapult-dir)     KATAPULT_DIR="${2:?missing value for $1}"; shift 2 ;;
    --printer-data)     PRINTER_DATA_CONFIG="${2:?missing value for $1}"; shift 2 ;;
    --data-dir)         DATA_DIR="${2:?missing value for $1}"; shift 2 ;;
    --uninstall)        UNINSTALL=1; shift ;;
    --dry-run)          DRY_RUN=1; shift ;;
    -h|--help)          usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if (( ! DRY_RUN )) && (( EUID != 0 )); then
  die "run with sudo (or use --dry-run to only print the units)"
fi
service_unit() {
  cat <<EOF
[Unit]
Description=Rebuild and flash Klipper MCU firmware after a Klipper update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=HOME=$TARGET_HOME
Environment=KLIPPER_DIR=$KLIPPER_DIR
Environment=KATAPULT_DIR=$KATAPULT_DIR
Environment=PRINTER_DATA_CONFIG=$PRINTER_DATA_CONFIG
Environment=OUT_ROOT=$DATA_DIR/out
Environment=STAMP_FILE=$DATA_DIR/last-commit
WorkingDirectory=$REPO
ExecStart=$SCRIPT_DIR/update_firmware.sh --auto --profile $PROFILE
TimeoutStartSec=3600
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
EOF
}

path_unit() {
  cat <<EOF
[Unit]
Description=Watch Klipper git refs for MCU firmware updates

[Path]
PathChanged=$KLIPPER_DIR/.git/HEAD
PathChanged=$KLIPPER_DIR/.git/refs/heads
Unit=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF
}

timer_unit() {
  cat <<EOF
[Unit]
Description=Retry Klipper MCU firmware updates after a deferred or failed run

[Timer]
OnBootSec=3min
OnUnitActiveSec=10min
AccuracySec=1min
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
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

if (( UNINSTALL )); then
  run systemctl disable --now "$PATH_NAME" "$TIMER_NAME" || true
  run rm -f "$UNIT_DIR/$SERVICE_NAME" "$UNIT_DIR/$PATH_NAME" "$UNIT_DIR/$TIMER_NAME"
  run systemctl daemon-reload
  echo "Removed the firmware update hook. State in $DATA_DIR is kept."
  exit 0
fi

[[ -x "$SCRIPT_DIR/update_firmware.sh" ]] || \
  die "missing executable $SCRIPT_DIR/update_firmware.sh"
[[ -d "$KLIPPER_DIR/.git" ]] || die "not a git checkout: $KLIPPER_DIR"
[[ -f "$PRINTER_DATA_CONFIG/std.config.local/uuids.cfg" ]] || \
  die "missing deployed UUIDs: $PRINTER_DATA_CONFIG/std.config.local/uuids.cfg"
if (( ! DRY_RUN )); then
  python3 -c 'import serial' 2>/dev/null || die \
    "python3-serial is missing; run: sudo apt install python3-serial"
fi

if (( DRY_RUN )); then
  echo "--- $UNIT_DIR/$SERVICE_NAME"
  service_unit
  echo
  echo "--- $UNIT_DIR/$PATH_NAME"
  path_unit
  echo
  echo "--- $UNIT_DIR/$TIMER_NAME"
  timer_unit
  echo
  echo "Would create $DATA_DIR and stamp the current Klipper commit."
  run install -d -m 0755 "$DATA_DIR" "$DATA_DIR/out"
  run systemctl daemon-reload
  run systemctl enable --now "$PATH_NAME" "$TIMER_NAME"
  exit 0
fi

run install -d -m 0755 "$DATA_DIR" "$DATA_DIR/out"
service_unit > "$UNIT_DIR/$SERVICE_NAME"
path_unit > "$UNIT_DIR/$PATH_NAME"
timer_unit > "$UNIT_DIR/$TIMER_NAME"

# Mark the currently running Klipper as already flashed: installing the hook
# must not trigger an immediate flash.  The next Klipper update changes HEAD.
git -C "$KLIPPER_DIR" rev-parse HEAD > "$DATA_DIR/last-commit"

run systemctl daemon-reload
run systemctl enable --now "$PATH_NAME" "$TIMER_NAME"
echo "Installed $SERVICE_NAME, $PATH_NAME and $TIMER_NAME."
echo "The hook watches $KLIPPER_DIR/.git and retries every 10 minutes."
echo "Logs: journalctl -u $SERVICE_NAME"