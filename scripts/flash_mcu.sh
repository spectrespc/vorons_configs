#!/usr/bin/env bash
# Flash a built Klipper binary to a CAN MCU through Katapult.
set -euo pipefail

KATAPULT_DIR="${KATAPULT_DIR:-$HOME/katapult}"
IFACE="can0"
UUID=""
BIN=""

usage() {
  cat <<'EOF'
Usage: flash_mcu.sh -u UUID -f BIN [-i IFACE]

Flashes a Klipper binary to a CAN MCU using Katapult's flash_can.py.

  -u, --uuid UUID    CAN bus UUID of the target MCU (from local/uuids.cfg)
  -f, --file BIN     path to klipper.bin
  -i, --interface IF CAN interface (default: can0)
  -h, --help         show this help

The Katapult checkout can be overridden with the KATAPULT_DIR environment variable.
EOF
}

while (($#)); do
  case "$1" in
    -u|--uuid)      UUID="${2:?missing value for $1}"; shift 2 ;;
    -f|--file)      BIN="${2:?missing value for $1}"; shift 2 ;;
    -i|--interface) IFACE="${2:?missing value for $1}"; shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$UUID" ]] || { echo "UUID is required (-u). See printers/<profile>/local/uuids.cfg." >&2; exit 2; }
[[ -n "$BIN" ]] || { echo "Binary is required (-f)." >&2; exit 2; }
[[ -f "$BIN" ]] || { echo "Binary not found: $BIN" >&2; exit 1; }
[[ -f "$KATAPULT_DIR/scripts/flash_can.py" ]] || {
  echo "Katapult flash script not found under $KATAPULT_DIR" >&2
  exit 1
}

exec python3 "$KATAPULT_DIR/scripts/flash_can.py" -i "$IFACE" -u "$UUID" -f "$BIN"