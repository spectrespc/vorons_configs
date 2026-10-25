#!/usr/bin/env bash
# Deploy printer configs into ~/printer_data/config, preserving directory structure.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR"
DEST="$HOME/printer_data/config"
DRY_RUN=0
BACKUP=0

usage() {
  cat <<'EOF'
Usage: deploy_configs.sh [-s SRC] [-d DEST] [-n] [-b]

Copies *.cfg and *.conf files plus the whole std.compil.configs/ directory
from SRC (default: the script's directory) into DEST
(default: ~/printer_data/config), preserving the relative directory structure.
The .git directory is skipped.

  -s, --src DIR    source directory
  -d, --dest DIR   destination directory
  -n, --dry-run    list what would be copied, change nothing
  -b, --backup     back up overwritten files under DEST/.backup/<timestamp>/
  -h, --help       show this help
EOF
}

while (($#)); do
  case "$1" in
    -s|--src)  SRC="${2:?missing value for $1}"; shift 2 ;;
    -d|--dest) DEST="${2:?missing value for $1}"; shift 2 ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -b|--backup) BACKUP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Refuse any source/destination overlap, including destination nested in source.
check_overlap() {
  if [[ "$SRC" == "$DEST" ]]; then
    echo "Source and destination are the same directory ($SRC); nothing to do." >&2
    echo "Run the script from a cloned copy of the repository, or pass -s/--src." >&2
    exit 1
  fi
  if [[ "$DEST" == "$SRC"/* ]]; then
    echo "Destination is inside the source directory ($DEST); refusing to copy recursively." >&2
    exit 1
  fi
}

[[ -d "$SRC" ]] || { echo "Source directory not found: $SRC" >&2; exit 1; }
SRC="$(cd -- "$SRC" && pwd)"

[[ "$DEST" = /* ]] || DEST="$PWD/$DEST"
while [[ "$DEST" == */ && "$DEST" != / ]]; do
  DEST="${DEST%/}"
done
check_overlap

if [[ ! -d "$DEST" ]]; then
  if (( DRY_RUN )); then
    echo "Destination does not exist yet (would be created): $DEST"
  else
    mkdir -p -- "$DEST"
  fi
fi
[[ -d "$DEST" ]] && DEST="$(cd -- "$DEST" && pwd)"
check_overlap

backup_dir=""
if (( BACKUP && ! DRY_RUN )); then
  backup_dir="$DEST/.backup/$(date +%Y%m%d-%H%M%S)"
  [[ -e "$backup_dir" ]] && backup_dir="$backup_dir-$$"
fi

# Enumerate the files first so that find errors abort the deployment
# instead of silently copying a partial set.
list="$(mktemp)"
trap 'rm -f -- "$list"' EXIT
if ! (cd -- "$SRC" && find . -type f \
        \( -name '*.cfg' -o -name '*.conf' -o -path './std.compil.configs/*' \) \
        -not -path './.git/*' -print0 | sort -z) > "$list"; then
  echo "Failed to enumerate source files in $SRC; nothing was copied." >&2
  exit 1
fi

count=0
backed_up=0
while IFS= read -r -d '' file; do
  rel="${file#./}"
  count=$((count + 1))
  if (( DRY_RUN )); then
    printf 'would copy: %s\n' "$rel"
    continue
  fi
  if [[ -n "$backup_dir" && -e "$DEST/$rel" ]]; then
    mkdir -p -- "$backup_dir/$(dirname -- "$rel")"
    cp -p -- "$DEST/$rel" "$backup_dir/$rel"
    backed_up=$((backed_up + 1))
    printf 'backed up: %s\n' "$rel"
  fi
  mkdir -p -- "$DEST/$(dirname -- "$rel")"
  cp -p -- "$SRC/$rel" "$DEST/$rel"
  printf 'copied: %s\n' "$rel"
done < "$list"

if (( DRY_RUN )); then
  printf 'Dry run: %d file(s) would be copied to %s\n' "$count" "$DEST"
elif (( backed_up > 0 )); then
  printf 'Done: %d file(s) copied to %s (backed up %d file(s) to %s)\n' \
    "$count" "$DEST" "$backed_up" "$backup_dir"
else
  printf 'Done: %d file(s) copied to %s\n' "$count" "$DEST"
fi