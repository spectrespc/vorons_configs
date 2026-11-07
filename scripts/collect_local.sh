#!/usr/bin/env bash
# Copy runtime local overrides (SAVE_CONFIG results and tuning) from the live
# config tree back into the repository profile.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LIVE="$HOME/printer_data/config"
PROFILE=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: collect_local.sh -p PROFILE [-l LIVE_DIR] [-n]

Copies LIVE_DIR/std.config.local/*.cfg into printers/<profile>/local/ so that
SAVE_CONFIG output and driver tuning are versioned in the repository.

  -p, --printer NAME  profile under printers/ (required)
  -l, --live DIR      live config tree (default: ~/printer_data/config)
  -n, --dry-run       list what would be copied, change nothing
  -h, --help          show this help

Typical tuning cycle:
  collect_local.sh -p voron-t
  git add printers/voron-t/local && git commit && git push
EOF
}

list_profiles() {
  find "$SRC/printers" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort
}

while (($#)); do
  case "$1" in
    -p|--printer) PROFILE="${2:?missing value for $1}"; shift 2 ;;
    -l|--live)    LIVE="${2:?missing value for $1}"; shift 2 ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  echo "Profile is required (-p). Available profiles:" >&2
  list_profiles | sed 's/^/  - /' >&2
  exit 2
fi

PROFILE_DIR="$SRC/printers/$PROFILE"
[[ -d "$PROFILE_DIR" ]] || {
  echo "Unknown profile '$PROFILE'. Available profiles:" >&2
  list_profiles | sed 's/^/  - /' >&2
  exit 1
}

[[ -d "$LIVE" ]] || { echo "Live config directory not found: $LIVE" >&2; exit 1; }
LIVE="$(cd -- "$LIVE" && pwd)"

LOCAL_SRC="$LIVE/std.config.local"
LOCAL_DEST="$PROFILE_DIR/local"
[[ -d "$LOCAL_SRC" ]] || { echo "No std.config.local directory in $LIVE" >&2; exit 1; }

files=()
while IFS= read -r -d '' file; do
  files+=("$file")
done < <(find "$LOCAL_SRC" -maxdepth 1 -type f -name '*.cfg' -print0 | sort -z)

if ((${#files[@]} == 0)); then
  echo "No *.cfg files in $LOCAL_SRC; nothing to collect."
  exit 0
fi

if (( DRY_RUN )); then
  for file in "${files[@]}"; do
    printf 'would collect: %s\n' "${file#"$LOCAL_SRC/"}"
  done
  printf 'Dry run: %d file(s) would be copied to %s\n' "${#files[@]}" "$LOCAL_DEST"
  exit 0
fi

mkdir -p -- "$LOCAL_DEST"
count=0
for file in "${files[@]}"; do
  name="$(basename -- "$file")"
  cp -p -- "$file" "$LOCAL_DEST/$name"
  printf 'collected: %s\n' "$name"
  count=$((count + 1))
done
printf 'Done: %d file(s) copied from %s to %s\n' "$count" "$LOCAL_SRC" "$LOCAL_DEST"