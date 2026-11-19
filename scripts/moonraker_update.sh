#!/usr/bin/env bash
# Deploy the live Klipper configs after this repository is updated.
#
# scripts/install_config_update_hook.sh installs a systemd path unit, which runs
# this script as `--auto` when Moonraker pulls a new commit, plus a retry timer.
# Moonraker itself only pulls the repository: it never executes the legacy
# "install_script" option (Moonraker only parses it for a PKGLIST), so the
# deploy has to be triggered outside the updater.
#
# The hook detects the printer profile, deploys it into the live config tree,
# keeps the canonical [update_manager vorons_configs] entry in the live
# moonraker.conf, restarts Klipper through Moonraker and records the deployed
# commit in DEST/.deployed_commit.  Any failure exits non-zero: nothing below
# the failed step runs and the retry timer starts the hook again.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DEST="${PRINTER_DATA_CONFIG:-$HOME/printer_data/config}"
MOONRAKER_URL="${MOONRAKER_URL:-http://127.0.0.1:7125}"
PROFILE=""
DRY_RUN=0
AUTO=0
PYTHON_BIN="${PYTHON:-python3}"
MARKER_NAME=".deployed_profile"
COMMIT_NAME=".deployed_commit"

usage() {
  cat <<'EOF'
Usage: moonraker_update.sh [-p PROFILE] [-d DEST] [-n] [-a]

Deploys the config profile after a repository update.  The systemd path unit
installed by scripts/install_config_update_hook.sh runs it with --auto; a manual
run without --auto deploys too, but leaves the Klipper restart to the operator.

The profile is taken from DEST/.deployed_profile (written by deploy_configs.sh)
and falls back to a byte comparison of DEST/machine.conf with each profile's
render_profile.py --dump-conf output (the form deploy actually writes). Without
a marker and an unambiguous match the script fails; pass -p once on the first
deploy.

  -p, --profile NAME  profile under printers/ (default: auto-detect)
  -d, --dest DIR      live config tree (default: $PRINTER_DATA_CONFIG or
                      ~/printer_data/config)
  -n, --dry-run       run deploy and the ensure step in dry-run mode
  -a, --auto          skip when DEST/.deployed_commit equals the current commit,
                      restart Klipper through Moonraker and stamp the commit
  -h, --help          show this help

Exit status: 0 deployed (or already up to date with --auto), 1 deploy, profile
detection or the Klipper restart failed.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    -p|--profile) PROFILE="${2:?missing value for $1}"; shift 2 ;;
    -d|--dest)    DEST="${2:?missing value for $1}"; shift 2 ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    -a|--auto)    AUTO=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -x "$SCRIPT_DIR/deploy_configs.sh" ]] || \
  die "missing executable $SCRIPT_DIR/deploy_configs.sh"
[[ -f "$SCRIPT_DIR/render_profile.py" ]] || \
  die "missing $SCRIPT_DIR/render_profile.py"
[[ -f "$SCRIPT_DIR/lib/moonraker_conf.py" ]] || \
  die "missing $SCRIPT_DIR/lib/moonraker_conf.py"
DEST="${DEST%/}"
[[ -n "$DEST" ]] || DEST="/"

current_commit() {
  command -v git >/dev/null 2>&1 || return 1
  git -C "$REPO" rev-parse HEAD 2>/dev/null
}

deployed_commit() {
  local stamp="$DEST/$COMMIT_NAME"
  [[ -f "$stamp" ]] || return 1
  tr -d '[:space:]' < "$stamp"
}

detect_profile() {
  local marker="$DEST/$MARKER_NAME"
  local live="$DEST/machine.conf"
  local candidate dump id="" match="" count=0
  if [[ -n "$PROFILE" ]]; then
    [[ -d "$REPO/printers/$PROFILE" ]] || die "unknown profile '$PROFILE'"
    printf '%s\n' "$PROFILE"
    return 0
  fi
  if [[ -f "$marker" ]]; then
    id="$(tr -d '[:space:]' < "$marker")"
    if [[ -n "$id" && -d "$REPO/printers/$id" ]]; then
      printf '%s\n' "$id"
      return 0
    fi
    echo "WARN: marker $marker names '$id', but printers/$id is gone; using machine.conf" >&2
  fi
  if [[ -f "$live" ]]; then
    # deploy writes the rendered dump, not printers/<id>/machine.conf itself, so
    # the fingerprint is compared against render_profile.py --dump-conf.
    dump="$(mktemp "${TMPDIR:-/tmp}/vorons-machine.XXXXXX")"
    for candidate in "$REPO"/printers/*/machine.conf; do
      [[ -f "$candidate" ]] || continue
      id="$(basename -- "$(dirname -- "$candidate")")"
      if ! "$PYTHON_BIN" "$SCRIPT_DIR/render_profile.py" \
          --machine-dir "$REPO/printers/$id" --dump-conf "$dump" >/dev/null 2>&1; then
        echo "WARN: cannot render printers/$id/machine.conf; skipping the fingerprint match" >&2
        continue
      fi
      if cmp -s -- "$live" "$dump"; then
        match="$id"
        count=$((count + 1))
      fi
    done
    rm -f -- "$dump"
  fi
  if (( count == 1 )); then
    printf '%s\n' "$match"
    return 0
  fi
  if (( count > 1 )); then
    die "$live matches $count profiles; pass -p with one of: $(list_profiles)"
  fi
  die "cannot detect the profile: no usable $MARKER_NAME marker and no machine.conf match in $DEST; pass -p on the first deploy"
}

list_profiles() {
  find "$REPO/printers" -mindepth 1 -maxdepth 1 -type d -printf '%f ' 2>/dev/null
}

restart_klipper() {
  command -v curl >/dev/null 2>&1 || {
    echo "ERROR: curl is missing; cannot restart klipper through Moonraker" >&2
    return 1
  }
  if ! curl -fsS --max-time 10 -X POST \
      "$MOONRAKER_URL/machine/services/restart?service=klipper" >/dev/null; then
    echo "ERROR: Moonraker at $MOONRAKER_URL did not accept the klipper restart" >&2
    return 1
  fi
  echo "restarted: klipper (through Moonraker)"
}

wait_for_repo() {
  # The path unit also fires as soon as the fetch writes refs, while Moonraker
  # is still merging and checking out.  git holds index.lock for that window.
  local lock="$REPO/.git/index.lock"
  local tries=0
  while [[ -e "$lock" ]] && (( tries < 60 )); do
    sleep 1
    tries=$((tries + 1))
  done
  [[ ! -e "$lock" ]]
}

commit="$(current_commit || true)"

if (( AUTO && ! DRY_RUN )) && [[ -n "$commit" ]] && \
    deployed="$(deployed_commit)" && [[ "$deployed" == "$commit" ]]; then
  printf 'moonraker_update: commit %s already deployed; nothing to do\n' "${commit:0:8}"
  exit 0
fi

if (( AUTO && ! DRY_RUN )); then
  wait_for_repo || die "repository is locked ($REPO/.git/index.lock); another git operation is running"
fi

profile="$(detect_profile)"

deploy_args=(-p "$profile" -d "$DEST" -b)
if (( DRY_RUN )); then
  deploy_args+=(-n)
fi
"$SCRIPT_DIR/deploy_configs.sh" "${deploy_args[@]}"

ensure_args=(ensure --config "$DEST/moonraker.conf")
if (( DRY_RUN )); then
  ensure_args+=(--dry-run)
fi
ensure_out="$("$PYTHON_BIN" "$SCRIPT_DIR/lib/moonraker_conf.py" "${ensure_args[@]}")"
printf '%s\n' "$ensure_out"
case "$ensure_out" in
  updated:*)
    echo "WARN: the live moonraker.conf changed; restart moonraker to activate the new update entry (not done here: it would kill this hook)."
    ;;
esac

if (( AUTO && ! DRY_RUN )); then
  restart_klipper || exit 1
fi

if (( ! DRY_RUN )) && [[ -n "$commit" ]]; then
  printf '%s\n' "$commit" > "$DEST/$COMMIT_NAME"
fi

mode="deployed"
if (( AUTO )); then
  mode="auto"
fi
if (( DRY_RUN )); then
  mode="dry run"
fi
printf 'moonraker_update: profile=%s commit=%s dest=%s mode=%s\n' \
  "$profile" "${commit:0:8}" "$DEST" "$mode"
if (( ! AUTO && ! DRY_RUN )); then
  echo "NOTE: klipper was not restarted; use --auto or restart it to load the deployed configs."
fi