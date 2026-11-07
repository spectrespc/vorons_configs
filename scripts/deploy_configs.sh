#!/usr/bin/env bash
# Deploy one printer profile from this repository into the live config tree.
#
# Managed files are copied with overwrite on every deploy. Seed files are
# copied only when they do not exist in DEST, so service-generated settings
# (KlipperScreen, telegram bot token, camera and sonar configs) survive.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DEST="$HOME/printer_data/config"
PROFILE=""
DRY_RUN=0
BACKUP=0

usage() {
  cat <<'EOF'
Usage: deploy_configs.sh -p PROFILE [-s SRC] [-d DEST] [-n] [-b]

Deploys one printer profile from the repository into the live config tree.

Managed (always overwritten):
  printers/<profile>/{printer.cfg,macros.cfg,moonraker.conf} -> DEST/
  printers/<profile>/local/*.cfg                             -> DEST/std.config.local/
  std.configs/**                                             -> DEST/std.configs/
  std.macros/**                                              -> DEST/std.macros/

Seed (copied only when missing in DEST):
  KlipperScreen.conf, crowsnest.conf, sonar.conf, telegram.conf

std.compil.configs/ is never deployed: it holds MCU build configs for
scripts/build_mcu.sh, not runtime Klipper configuration.

  -p, --printer NAME  profile under printers/ (required)
  -s, --src DIR       repository root (default: parent of this script)
  -d, --dest DIR      destination (default: ~/printer_data/config)
  -n, --dry-run       list what would be copied, change nothing
  -b, --backup        back up overwritten managed files under DEST/.backup/<timestamp>/
  -h, --help          show this help

When -p is omitted the available profiles are listed.
EOF
}

list_profiles() {
  find "$SRC/printers" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort
}

while (($#)); do
  case "$1" in
    -p|--printer) PROFILE="${2:?missing value for $1}"; shift 2 ;;
    -s|--src)     SRC="${2:?missing value for $1}"; shift 2 ;;
    -d|--dest)    DEST="${2:?missing value for $1}"; shift 2 ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -b|--backup)  BACKUP=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -d "$SRC" ]] || { echo "Source directory not found: $SRC" >&2; exit 1; }
SRC="$(cd -- "$SRC" && pwd)"

if [[ -z "$PROFILE" ]]; then
  echo "Profile is required (-p). Available profiles:" >&2
  list_profiles | sed 's/^/  - /' >&2
  exit 2
fi

PROFILE_DIR="$SRC/printers/$PROFILE"
if [[ ! -d "$PROFILE_DIR" ]]; then
  echo "Unknown profile '$PROFILE'. Available profiles:" >&2
  list_profiles | sed 's/^/  - /' >&2
  exit 1
fi

for required in printer.cfg macros.cfg moonraker.conf; do
  [[ -f "$PROFILE_DIR/$required" ]] || {
    echo "Profile '$PROFILE' is missing required file: $required" >&2
    exit 1
  }
done
for required_dir in std.configs std.macros; do
  [[ -d "$SRC/$required_dir" ]] || {
    echo "Repository is missing required directory: $required_dir" >&2
    exit 1
  }
done

[[ "$DEST" = /* ]] || DEST="$PWD/$DEST"
while [[ "$DEST" == */ && "$DEST" != / ]]; do
  DEST="${DEST%/}"
done

check_overlap() {
  if [[ "$SRC" == "$DEST" ]]; then
    echo "Source and destination are the same directory ($SRC); nothing to do." >&2
    echo "Run this script from a clone (~/vorons_configs), not from the live config tree." >&2
    exit 1
  fi
  if [[ "$DEST" == "$SRC"/* ]]; then
    echo "Destination is inside the source directory ($DEST); refusing to copy recursively." >&2
    exit 1
  fi
}
check_overlap

# Collect the complete file list first so a source read error aborts before
# anything is written.
src_files=()
dest_rels=()
modes=()
add_file() {
  src_files+=("$1")
  dest_rels+=("$2")
  modes+=("$3")
}

for managed in printer.cfg macros.cfg moonraker.conf; do
  add_file "$PROFILE_DIR/$managed" "$managed" managed
done

if [[ -d "$PROFILE_DIR/local" ]]; then
  while IFS= read -r -d '' file; do
    rel="${file#"$PROFILE_DIR/local/"}"
    add_file "$file" "std.config.local/$rel" managed
  done < <(find "$PROFILE_DIR/local" -type f -name '*.cfg' -print0 | sort -z)
fi

for top in std.configs std.macros; do
  while IFS= read -r -d '' file; do
    rel="${file#"$SRC/$top/"}"
    add_file "$file" "$top/$rel" managed
  done < <(find "$SRC/$top" -type f -print0 | sort -z)
done

for seed in KlipperScreen.conf crowsnest.conf sonar.conf telegram.conf; do
  if [[ -f "$PROFILE_DIR/$seed" ]]; then
    add_file "$PROFILE_DIR/$seed" "$seed" seed
  fi
done

for file in "${src_files[@]}"; do
  [[ -r "$file" ]] || { echo "Cannot read source file: $file" >&2; exit 1; }
done

if (( DRY_RUN )); then
  [[ -d "$DEST" ]] || echo "Destination does not exist yet (would be created): $DEST"
else
  mkdir -p -- "$DEST"
fi
[[ -d "$DEST" ]] && DEST="$(cd -- "$DEST" && pwd)"
check_overlap

backup_dir=""
if (( BACKUP && ! DRY_RUN )); then
  backup_dir="$DEST/.backup/$(date +%Y%m%d-%H%M%S)"
  [[ -e "$backup_dir" ]] && backup_dir="$backup_dir-$$"
fi

copied=0
seeded=0
seed_skipped=0
backed_up=0

for i in "${!src_files[@]}"; do
  src="${src_files[$i]}"
  rel="${dest_rels[$i]}"
  mode="${modes[$i]}"

  if [[ "$mode" == "seed" && -e "$DEST/$rel" ]]; then
    seed_skipped=$((seed_skipped + 1))
    (( DRY_RUN )) && printf 'would skip seed (exists): %s\n' "$rel"
    continue
  fi

  if (( DRY_RUN )); then
    if [[ "$mode" == "seed" ]]; then
      seeded=$((seeded + 1))
      printf 'would seed: %s\n' "$rel"
    else
      copied=$((copied + 1))
      printf 'would copy: %s\n' "$rel"
    fi
    continue
  fi

  if [[ -n "$backup_dir" && -e "$DEST/$rel" ]]; then
    mkdir -p -- "$backup_dir/$(dirname -- "$rel")"
    cp -p -- "$DEST/$rel" "$backup_dir/$rel"
    backed_up=$((backed_up + 1))
    printf 'backed up: %s\n' "$rel"
  fi

  mkdir -p -- "$DEST/$(dirname -- "$rel")"
  cp -p -- "$src" "$DEST/$rel"
  if [[ "$mode" == "seed" ]]; then
    seeded=$((seeded + 1))
    printf 'seeded: %s\n' "$rel"
  else
    copied=$((copied + 1))
    printf 'copied: %s\n' "$rel"
  fi
done

if (( DRY_RUN )); then
  printf 'Dry run for profile %s: %d managed file(s) would be copied, %d seed file(s) would be created, %d seed file(s) already exist.\n' \
    "$PROFILE" "$copied" "$seeded" "$seed_skipped"
else
  printf 'Done: profile %s, %d managed file(s) copied, %d seed file(s) created, %d seed file(s) left untouched in %s' \
    "$PROFILE" "$copied" "$seeded" "$seed_skipped" "$DEST"
  if (( backed_up > 0 )); then
    printf ' (backed up %d file(s) to %s)' "$backed_up" "$backup_dir"
  fi
  printf '.\n'
fi