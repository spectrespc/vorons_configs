#!/usr/bin/env bash
# Build Klipper or Katapult firmware from one of the stored MCU configs.
#
# The config file (std.compil.configs/config_*) is a Kconfig .config snapshot.
# It is passed as KCONFIG_CONFIG and the build tree is kept out of the
# repository, so any number of MCU configurations can be built in parallel.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DEFAULT_SRC="${KLIPPER_DIR:-$HOME/klipper}"
SRC="$DEFAULT_SRC"
CONFIG=""
OUT=""
JOBS=4
DO_CLEAN=0
DO_MENUCONFIG=0
PRINT_BIN=0

usage() {
  cat <<'EOF'
Usage: build_mcu.sh -c CONFIG [options]

Builds Klipper (or Katapult) firmware for one MCU with a config from
std.compil.configs/.

  -c, --config FILE   MCU config, absolute or relative to the repository root
  -o, --out DIR       output directory (default: <src>/out/<config name>)
      --src DIR       source tree to build: ~/klipper (default) or ~/katapult
      --clean         run "make clean" for this config before building
      --menuconfig    open the interactive Kconfig editor and exit
  -j, --jobs N        parallel build jobs (default: 4)
      --print-bin     print the built binary path (klipper.bin/katapult.bin)
  -h, --help          show this help

Examples:
  scripts/build_mcu.sh -c std.compil.configs/config_sht36_v3
  scripts/build_mcu.sh -c std.compil.configs/config_m5p_v1 --clean -j8
  scripts/build_mcu.sh -c std.compil.configs/config_sht42_katapult.v1 \
      --src ~/katapult --print-bin

The Klipper checkout defaults to ~/klipper; override it with KLIPPER_DIR.
Katapult is expected at ~/katapult (git clone https://github.com/Arksine/katapult).
EOF
}

while (($#)); do
  case "$1" in
    -c|--config)   CONFIG="${2:?missing value for $1}"; shift 2 ;;
    -o|--out)      OUT="${2:?missing value for $1}"; shift 2 ;;
    --src)         SRC="${2:?missing value for $1}"; shift 2 ;;
    --clean)       DO_CLEAN=1; shift ;;
    --menuconfig)  DO_MENUCONFIG=1; shift ;;
    -j|--jobs)     JOBS="${2:?missing value for $1}"; shift 2 ;;
    --print-bin)   PRINT_BIN=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$CONFIG" ]]; then
  echo "MCU config is required (-c). Available configs:" >&2
  find "$REPO/std.compil.configs" -maxdepth 1 -type f -printf '  - std.compil.configs/%f\n' 2>/dev/null | sort >&2
  exit 2
fi

[[ "$CONFIG" = /* ]] || CONFIG="$REPO/$CONFIG"
[[ -f "$CONFIG" ]] || { echo "Config not found: $CONFIG" >&2; exit 1; }

[[ "$SRC" = /* ]] || SRC="$PWD/$SRC"
[[ -d "$SRC" ]] || { echo "Source directory not found: $SRC" >&2; exit 1; }
[[ -f "$SRC/Makefile" ]] || { echo "No Makefile in $SRC" >&2; exit 1; }

if [[ -z "$OUT" ]]; then
  OUT="$SRC/out/$(basename -- "$CONFIG")"
fi
[[ "$OUT" = /* ]] || OUT="$PWD/$OUT"
OUT="${OUT%/}"

# Katapult is a Klipper-derived bootloader and produces katapult.bin; the Linux
# process MCU is linked to klipper.elf and installed with "make flash".
BIN_NAME="klipper.bin"
if [[ -f "$SRC/src/katapult/katapult.c" ]] || grep -qs 'katapult\.bin' "$SRC/Makefile"; then
  BIN_NAME="katapult.bin"
elif grep -q '^CONFIG_MACH_LINUX=y' "$CONFIG"; then
  BIN_NAME="klipper.elf"
fi
BIN="$OUT/$BIN_NAME"

# Klipper's Makefile treats OUT as a prefix ($(OUT)src/foo.o), so the trailing
# slash is required; without it objects land in "out/config_m5p_v1src/".
MAKE_ARGS=(-C "$SRC" "KCONFIG_CONFIG=$CONFIG" "OUT=$OUT/")

printf 'Build %s\n  config: %s\n  source: %s\n  out:    %s\n' \
  "$(basename -- "$CONFIG")" "$CONFIG" "$SRC" "$OUT"

if (( DO_CLEAN )); then
  printf 'Cleaning %s\n' "$OUT"
  make "${MAKE_ARGS[@]}" clean
fi

if (( DO_MENUCONFIG )); then
  exec make "${MAKE_ARGS[@]}" menuconfig
fi

make "${MAKE_ARGS[@]}" -j"$JOBS"

if (( PRINT_BIN )); then
  # Katapult appends the MCU name for some targets; the plain name is the one
  # documented in README and used by flash_mcu.sh -f.
  if [[ ! -f "$BIN" ]]; then
    echo "ERROR: build finished but $BIN is missing" >&2
    exit 1
  fi
  printf '%s\n' "$BIN"
fi
