#!/usr/bin/env bash
# Build Klipper firmware from one of the stored MCU configs.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." && pwd)"
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
CONFIG=""
OUT=""

usage() {
  cat <<'EOF'
Usage: build_mcu.sh -c CONFIG [-o OUTDIR]

Builds Klipper firmware for one MCU using a config from std.compil.configs/.

  -c, --config FILE  MCU config, absolute or relative to the repository root
  -o, --out DIR      output directory (default: ~/klipper/out/<config name>)
  -h, --help         show this help

Examples:
  scripts/build_mcu.sh -c std.compil.configs/config_sht36_v3
  scripts/build_mcu.sh -c std.compil.configs/config_m5p_v1 -o ~/klipper/out/m5p

The Klipper checkout can be overridden with the KLIPPER_DIR environment variable.
EOF
}

while (($#)); do
  case "$1" in
    -c|--config) CONFIG="${2:?missing value for $1}"; shift 2 ;;
    -o|--out)    OUT="${2:?missing value for $1}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$CONFIG" ]]; then
  echo "MCU config is required (-c). Available configs:" >&2
  find "$SRC/std.compil.configs" -maxdepth 1 -type f -printf '  - std.compil.configs/%f\n' 2>/dev/null | sort >&2
  exit 2
fi

[[ "$CONFIG" = /* ]] || CONFIG="$SRC/$CONFIG"
[[ -f "$CONFIG" ]] || { echo "Config not found: $CONFIG" >&2; exit 1; }
[[ -d "$KLIPPER_DIR" ]] || { echo "Klipper directory not found: $KLIPPER_DIR" >&2; exit 1; }

if [[ -z "$OUT" ]]; then
  OUT="$KLIPPER_DIR/out/$(basename -- "$CONFIG")"
fi
[[ "$OUT" = /* ]] || OUT="$PWD/$OUT"

printf 'Building %s\n  KCONFIG_CONFIG=%s\n  OUT=%s\n' "$(basename -- "$CONFIG")" "$CONFIG" "$OUT"
exec make -C "$KLIPPER_DIR" KCONFIG_CONFIG="$CONFIG" OUT="$OUT"