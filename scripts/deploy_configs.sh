#!/usr/bin/env bash
# Deploy one printer profile from this repository into the live config tree.
#
# The fleet axes (size/model/board/xy_step/xy_driver) are read once from
# printers/<profile>/machine.conf. deploy renders profile.cfg from them, checks
# that the committed copy is fresh, builds a staging tree, validates it with
# check_config.py and only then writes to DEST.
#
# Managed files are overwritten on every deploy. Seed files are created only
# when missing. printer.cfg is a seed because Klipper's SAVE_CONFIG appends its
# autosave block there; the block is carried into staging for validation but is
# never rewritten from the repository.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DEST="$HOME/printer_data/config"
PROFILE=""
DRY_RUN=0
BACKUP=0
CHECK_ONLY=0
RENDER_ONLY=0
MATRIX=0
PRUNE=1
AXES=()
PYTHON_BIN="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: deploy_configs.sh -p PROFILE [-s SRC] [-d DEST] [-n] [-b]
                         [--check] [--axis KEY=VALUE]... [--no-prune]

Renders profile.cfg from printers/<profile>/machine.conf, validates a staging
tree with check_config.py, then deploys it.

Managed (always overwritten):
  profile.cfg, machine.conf, anchors.cfg, machine-extras.cfg,
  macros.cfg, moonraker.conf                          -> DEST/
  printers/<profile>/local/*.cfg                      -> DEST/std.config.local/
  std.configs/**                                      -> DEST/std.configs/
  std.macros/**                                       -> DEST/std.macros/

Seed (copied only when missing in DEST):
  printer.cfg, KlipperScreen.conf, crowsnest.conf, sonar.conf, telegram.conf

printer.cfg is a seed because Klipper writes SAVE_CONFIG output into it. It is
never overwritten by the repository copy.

std.compil.configs/ is never deployed: it holds MCU build configs for
scripts/build_mcu.sh, not runtime Klipper configuration.

  -p, --printer NAME  profile under printers/ (required)
  -s, --src DIR       repository root (default: parent of this script)
  -d, --dest DIR      destination (default: ~/printer_data/config)
  -n, --dry-run       validate and list actions, change nothing
  -b, --backup        back up overwritten and pruned files under DEST/.backup/<ts>/
  -c, --check         render + stage + validate only; no writes, no prune
      --axis K=V      temporary axis override (matrix checks; implies --check)
      --render        regenerate printers/<profile>/profile.cfg from machine.conf
      --matrix        validate all model x size combinations and exit
      --no-prune      keep legacy files that are otherwise pruned
  -h, --help          show this help

Pruned by default (whitelist only):
  std.configs/gantry/, std.configs/pinout/, std.configs/tc.ext/,
  DEST/printers/ (leftover from the first 1.1.0 layout), *.old and *.bkp files.
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
    -c|--check)   CHECK_ONLY=1; shift ;;
    --axis)       AXES+=("${2:?missing value for $1}"); CHECK_ONLY=1; shift 2 ;;
    --render)     RENDER_ONLY=1; shift ;;
    --matrix)     MATRIX=1; shift ;;
    --prune)      PRUNE=1; shift ;;
    --no-prune)   PRUNE=0; shift ;;
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

for required in machine.conf printer.cfg profile.cfg anchors.cfg machine-extras.cfg macros.cfg moonraker.conf; do
  [[ -f "$PROFILE_DIR/$required" ]] || {
    echo "Profile '$PROFILE' is missing required file: $required" >&2
    echo "Create it with scripts/new_machine.sh or restore it from git." >&2
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

render() {
  "$PYTHON_BIN" "$SCRIPT_DIR/render_profile.py" --machine-dir "$PROFILE_DIR" "$@"
}

if (( RENDER_ONLY )); then
  if ((${#AXES[@]})); then
    echo "ERROR: --render cannot be combined with --axis." >&2
    exit 2
  fi
  render --write
  echo "Rendered $PROFILE_DIR/profile.cfg"
  exit 0
fi

if (( MATRIX )); then
  if ((${#AXES[@]})); then
    echo "ERROR: --matrix cannot be combined with --axis." >&2
    exit 2
  fi
  # The fleet axis has two feature variants: the profile's own feature set
  # ("full") and a machine without the SHT42 extra extruder ("lite"), where
  # belay/btt_sfs cannot be enabled because their sensors live on that board.
  read_features() {
    "$PYTHON_BIN" - "$1" <<'PY'
import sys
value = ""
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line.startswith("features="):
            value = line.split("=", 1)[1].strip()
print(value)
PY
  }
  lite_features="$("$PYTHON_BIN" -c '
import sys
skip = {"extra_extruder", "belay", "btt_sfs"}
print(",".join(item for item in sys.argv[1].split(",") if item and item not in skip))
' "$(read_features "$PROFILE_DIR/machine.conf")")"
  matrix_rc=0
  for variant in full lite; do
    feature_axis=()
    if [[ "$variant" == lite ]]; then
      feature_axis=(--axis "features=$lite_features")
    fi
    for model in trident v24; do
      for size in 150 200 250 300 350; do
        printf 'matrix: %s %s-%s ... ' "$variant" "$model" "$size"
        if "$SCRIPT_DIR/deploy_configs.sh" -p "$PROFILE" -s "$SRC" \
            --check --axis "model=$model" --axis "size=$size" \
            ${feature_axis[@]+"${feature_axis[@]}"} >/dev/null; then
          echo "ok"
        else
          echo "FAILED"
          matrix_rc=1
        fi
      done
    done
  done
  exit "$matrix_rc"
fi

axis_args=()
for axis in "${AXES[@]}"; do
  axis_args+=(--axis "$axis")
done

# --- 1. committed profile.cfg must match machine.conf -------------------------
if ((${#AXES[@]} == 0)); then
  rendered="$(mktemp "${TMPDIR:-/tmp}/vorons-profile.XXXXXX")"
  render --output "$rendered"
  if ! cmp -s -- "$rendered" "$PROFILE_DIR/profile.cfg"; then
    rm -f -- "$rendered"
    echo "ERROR: profile.cfg is stale for profile '$PROFILE'." >&2
    echo "Run: scripts/deploy_configs.sh -p $PROFILE --render" >&2
    echo "Then commit the regenerated file." >&2
    exit 1
  fi
  rm -f -- "$rendered"
fi

# --- 2. staging tree ----------------------------------------------------------
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/vorons-deploy.XXXXXX")"
cleanup() { rm -rf -- "$STAGE"; }
trap cleanup EXIT

mkdir -p -- "$STAGE/std.config.local"
render --output "$STAGE/profile.cfg" "${axis_args[@]}"
render --dump-conf "$STAGE/machine.conf" "${axis_args[@]}"

cp -p -- "$PROFILE_DIR/printer.cfg" "$STAGE/printer.cfg"
extract_autosave() {
  local source="$1" target="$2"
  [[ -f "$source" ]] || return 1
  awk '/^#\*# <.*SAVE_CONFIG/ {found=1} found {print}' "$source" > "$target"
  [[ -s "$target" ]]
}
if ((${#AXES[@]} == 0)) && extract_autosave "$DEST/printer.cfg" "$STAGE/.autosave"; then
  printf '\n' >> "$STAGE/printer.cfg"
  cat "$STAGE/.autosave" >> "$STAGE/printer.cfg"
  rm -f -- "$STAGE/.autosave"
fi

if ((${#AXES[@]} > 0)); then
  # A hypothetical machine has no measured anchors yet.
  cat > "$STAGE/anchors.cfg" <<'EOF'
# Matrix check: measured anchors are not defined for this hypothetical machine.
# The geometry/<model>-<size>.cfg defaults are used as-is.
EOF
else
  cp -p -- "$PROFILE_DIR/anchors.cfg" "$STAGE/anchors.cfg"
fi
cp -p -- "$PROFILE_DIR/machine-extras.cfg" "$STAGE/machine-extras.cfg"
cp -p -- "$PROFILE_DIR/macros.cfg" "$STAGE/macros.cfg"
cp -p -- "$PROFILE_DIR/moonraker.conf" "$STAGE/moonraker.conf"

if [[ -d "$PROFILE_DIR/local" ]]; then
  while IFS= read -r -d '' file; do
    cp -p -- "$file" "$STAGE/std.config.local/$(basename -- "$file")"
  done < <(find "$PROFILE_DIR/local" -maxdepth 1 -type f -name '*.cfg' -print0 | sort -z)
fi

cp -R -- "$SRC/std.configs/." "$STAGE/std.configs/"
cp -R -- "$SRC/std.macros/." "$STAGE/std.macros/"

# --- 3. validate staging ------------------------------------------------------
if ! "$PYTHON_BIN" "$SCRIPT_DIR/check_config.py" --config-dir "$STAGE"; then
  echo "ERROR: staging validation failed for profile '$PROFILE'; nothing was written." >&2
  exit 1
fi

if (( CHECK_ONLY )); then
  echo "Check passed: profile '$PROFILE' renders and validates (staging: $STAGE)."
  exit 0
fi

# --- 4. refuse to deploy while printing --------------------------------------
if (( ! DRY_RUN )) && command -v curl >/dev/null 2>&1; then
  state="$(curl -s --max-time 2 \
    'http://127.0.0.1:7125/printer/objects/query?print_stats' 2>/dev/null \
    | sed -n 's/.*"state"[[:space:]]*:[[:space:]]*"\([a-z_]*\)".*/\1/p' \
    | head -n 1 || true)"
  case "$state" in
    printing|paused)
      echo "ERROR: Moonraker reports print_stats.state=$state; refusing to deploy." >&2
      echo "Stop or finish the print, or use --check for an offline validation." >&2
      exit 1
      ;;
  esac
fi

# --- 5. write -----------------------------------------------------------------
if (( DRY_RUN )); then
  [[ -d "$DEST" ]] || echo "Destination does not exist yet (would be created): $DEST"
else
  mkdir -p -- "$DEST"
fi
if [[ -d "$DEST" ]]; then
  DEST="$(cd -- "$DEST" && pwd)"
fi
check_overlap

backup_dir=""
if (( BACKUP && ! DRY_RUN )); then
  backup_dir="$DEST/.backup/$(date +%Y%m%d-%H%M%S)"
  [[ -e "$backup_dir" ]] && backup_dir="$backup_dir-$$"
fi

backup_path() {
  local rel="$1"
  [[ -n "$backup_dir" && -e "$DEST/$rel" ]] || return 0
  mkdir -p -- "$backup_dir/$(dirname -- "$rel")"
  cp -a -- "$DEST/$rel" "$backup_dir/$rel"
  backed_up=$((backed_up + 1))
}

copied=0
seeded=0
seed_skipped=0
migrated=0
backed_up=0
pruned=0

managed_files=(profile.cfg machine.conf anchors.cfg machine-extras.cfg macros.cfg moonraker.conf)
managed_dirs=(std.configs std.macros std.config.local)

if (( DRY_RUN )); then
  for rel in "${managed_files[@]}"; do
    printf 'would copy: %s\n' "$rel"
    copied=$((copied + 1))
  done
  for dir in "${managed_dirs[@]}"; do
    printf 'would copy: %s/\n' "$dir"
    copied=$((copied + 1))
  done
else
  for rel in "${managed_files[@]}"; do
    backup_path "$rel"
    mkdir -p -- "$DEST/$(dirname -- "$rel")"
    cp -p -- "$STAGE/$rel" "$DEST/$rel"
    printf 'copied: %s\n' "$rel"
    copied=$((copied + 1))
  done
  for dir in "${managed_dirs[@]}"; do
    backup_path "$dir"
    mkdir -p -- "$DEST/$dir"
    cp -R -- "$STAGE/$dir/." "$DEST/$dir/"
    printf 'copied: %s/\n' "$dir"
    copied=$((copied + 1))
  done
fi

is_seed_manifest() {
  grep -q '^\[include[[:space:]]\+profile\.cfg\]' "$1" 2>/dev/null
}

if [[ ! -e "$DEST/printer.cfg" ]]; then
  if (( DRY_RUN )); then
    printf 'would seed: printer.cfg\n'
  else
    cp -p -- "$PROFILE_DIR/printer.cfg" "$DEST/printer.cfg"
    printf 'seeded: printer.cfg\n'
  fi
  seeded=$((seeded + 1))
elif ! is_seed_manifest "$DEST/printer.cfg"; then
  # One-time migration from the 1.1.0 manifest (printer.cfg used to be managed).
  # The old file is backed up when -b is used; an existing SAVE_CONFIG block is
  # carried into the new seed so calibrated values are not lost.
  if (( DRY_RUN )); then
    printf 'would migrate: printer.cfg (old manifest -> seed)\n'
  else
    backup_path printer.cfg
    new_printer="$DEST/.printer.cfg.new.$$"
    autosave="$DEST/.printer.cfg.autosave.$$"
    cp -p -- "$PROFILE_DIR/printer.cfg" "$new_printer"
    if extract_autosave "$DEST/printer.cfg" "$autosave"; then
      printf '\n' >> "$new_printer"
      cat "$autosave" >> "$new_printer"
      rm -f -- "$autosave"
      printf 'migrated: printer.cfg to seed (SAVE_CONFIG block preserved)\n'
    else
      printf 'migrated: printer.cfg to seed (old manifest kept in backup)\n'
    fi
    mv -f -- "$new_printer" "$DEST/printer.cfg"
  fi
  migrated=$((migrated + 1))
else
  seed_skipped=$((seed_skipped + 1))
  printf 'kept seed (exists): printer.cfg\n'
fi

for seed in KlipperScreen.conf crowsnest.conf sonar.conf telegram.conf; do
  [[ -f "$PROFILE_DIR/$seed" ]] || continue
  if [[ -e "$DEST/$seed" ]]; then
    seed_skipped=$((seed_skipped + 1))
    printf 'kept seed (exists): %s\n' "$seed"
    continue
  fi
  if (( DRY_RUN )); then
    printf 'would seed: %s\n' "$seed"
  else
    cp -p -- "$PROFILE_DIR/$seed" "$DEST/$seed"
    printf 'seeded: %s\n' "$seed"
  fi
  seeded=$((seeded + 1))
done

# --- 6. prune legacy paths ----------------------------------------------------
if (( PRUNE )); then
  for rel in std.configs/gantry std.configs/pinout std.configs/tc.ext printers; do
    [[ -e "$DEST/$rel" ]] || continue
    if (( DRY_RUN )); then
      printf 'would prune: %s\n' "$rel"
    else
      backup_path "$rel"
      rm -rf -- "${DEST:?}/$rel"
      printf 'pruned: %s\n' "$rel"
    fi
    pruned=$((pruned + 1))
  done
  if [[ -d "$DEST" ]]; then
    while IFS= read -r -d '' stale; do
      rel="${stale#"$DEST/"}"
      if (( DRY_RUN )); then
        printf 'would prune: %s\n' "$rel"
      else
        backup_path "$rel"
        rm -f -- "$stale"
        printf 'pruned: %s\n' "$rel"
      fi
      pruned=$((pruned + 1))
    done < <(find "$DEST" -path "$DEST/.backup" -prune -o -type f \( -name '*.old' -o -name '*.bkp' \) -print0)
  fi
fi

# --- 7. summary ---------------------------------------------------------------
if (( DRY_RUN )); then
  printf 'Dry run for profile %s: %d managed item(s) would be copied, %d seed file(s) would be created, %d printer.cfg migration(s), %d seed file(s) already exist, %d legacy item(s) would be pruned.\n' \
    "$PROFILE" "$copied" "$seeded" "$migrated" "$seed_skipped" "$pruned"
else
  printf 'Done: profile %s, %d managed item(s) copied, %d seed file(s) created, %d printer.cfg migration(s), %d seed file(s) left untouched in %s' \
    "$PROFILE" "$copied" "$seeded" "$migrated" "$seed_skipped" "$DEST"
  if (( pruned > 0 )); then
    printf ', %d legacy item(s) pruned' "$pruned"
  fi
  if (( backed_up > 0 )); then
    printf ' (backed up %d item(s) to %s)' "$backed_up" "$backup_dir"
  fi
  printf '.\n'
fi