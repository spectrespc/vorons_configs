#!/usr/bin/env bash
# Install the systemd path/timer units that deploy the live Klipper configs
# after Moonraker updates this repository.  Run once with sudo; --dry-run
# prints the units and commands.
#
# Moonraker only pulls the repository: its legacy "install_script" option is
# never executed, so the path unit is what turns a new commit into a deploy.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" ]] || TARGET_HOME="$HOME"
PRINTER_DATA_CONFIG="$TARGET_HOME/printer_data/config"
DRY_RUN=0
UNINSTALL=0

SERVICE_NAME="klipper-configs-deploy.service"
PATH_NAME="klipper-configs-deploy.path"
TIMER_NAME="klipper-configs-deploy.timer"
UNIT_DIR="/etc/systemd/system"

usage() {
  cat <<'EOF'
Usage: install_config_update_hook.sh [options]

Installs a systemd path unit (watching the vorons_configs git refs) and a
retry timer that run scripts/moonraker_update.sh --auto after Moonraker pulls
a new commit into this checkout.

Options:
      --printer-data DIR live printer_data/config (default: <user home>/printer_data/config)
      --uninstall        disable and remove the units (deployed state is kept)
      --dry-run          print the units and commands, change nothing
  -h, --help             show this help

The units run as the printer user, so they need no root privileges at runtime;
installing them needs sudo.  The script itself does not deploy: run
scripts/deploy_configs.sh -p <profile> -b once (or let the timer do it).
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --printer-data) PRINTER_DATA_CONFIG="${2:?missing value for $1}"; shift 2 ;;
    --uninstall)    UNINSTALL=1; shift ;;
    --dry-run)      DRY_RUN=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if (( ! DRY_RUN )) && (( EUID != 0 )); then
  die "run with sudo (or use --dry-run to only print the units)"
fi

service_unit() {
  cat <<EOF
[Unit]
Description=Deploy vorons_configs into the live Klipper config tree
After=network-online.target moonraker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$TARGET_USER
Environment=HOME=$TARGET_HOME
Environment=PRINTER_DATA_CONFIG=$PRINTER_DATA_CONFIG
WorkingDirectory=$REPO
ExecStart=$SCRIPT_DIR/moonraker_update.sh --auto
TimeoutStartSec=900
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
EOF
}

path_unit() {
  cat <<EOF
[Unit]
Description=Watch the vorons_configs git refs for a deployable update

[Path]
PathChanged=$REPO/.git/HEAD
PathChanged=$REPO/.git/FETCH_HEAD
PathChanged=$REPO/.git/refs/heads
Unit=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF
}

timer_unit() {
  cat <<EOF
[Unit]
Description=Retry the vorons_configs deploy after a deferred or failed run

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
  echo "Removed the config deploy hook. Deployed state in $PRINTER_DATA_CONFIG is kept."
  exit 0
fi

[[ -x "$SCRIPT_DIR/moonraker_update.sh" ]] || \
  die "missing executable $SCRIPT_DIR/moonraker_update.sh"
[[ -d "$REPO/.git" ]] || die "not a git checkout: $REPO"

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
  run systemctl daemon-reload
  run systemctl enable --now "$PATH_NAME" "$TIMER_NAME"
  exit 0
fi

service_unit > "$UNIT_DIR/$SERVICE_NAME"
path_unit > "$UNIT_DIR/$PATH_NAME"
timer_unit > "$UNIT_DIR/$TIMER_NAME"

run systemctl daemon-reload
run systemctl enable --now "$PATH_NAME" "$TIMER_NAME"
echo "Installed $SERVICE_NAME, $PATH_NAME and $TIMER_NAME."
echo "Moonraker only pulls $REPO; these units deploy it afterwards as $TARGET_USER."
echo "First deploy: scripts/deploy_configs.sh -p <profile> -b (the timer also runs it within 3 minutes)."
echo "Logs: journalctl -u $SERVICE_NAME"