#!/usr/bin/env bash
# bringup.sh: first-run commissioning pipeline for one printer profile.
#
# Stages (fixed order):
#   deploy  deploy the profile and restart Klipper
#   tmc     recompute every TMC driver at the motor nominal (tmc_calc), redeploy
#   motion  find max_velocity/max_accel with TEST_SPEED (tmc_tune), apply
#   z-motion find max_z_velocity/max_z_accel with TEST_SPEED_Z (tmc_tune), apply
#   pid-e   PID_CALIBRATE the extruder at 250 C, patch local/pid.cfg, verify
#   pid-b   PID_CALIBRATE the bed at 120 C, patch local/pid.cfg, verify
#   done    summary and a suggested commit message (committing is manual)
#
# The repository stays the source of truth: every stage writes into
# ~/vorons_configs, deploys, restarts Klipper through Moonraker and re-reads the
# result. Note that Klipper's state is committed by the owner, never by this
# script.
#
# State is kept in ~/printer_data/.bringup/<id>.json so an interrupted run can
# be resumed with --from. Use --dry-run to print the plan without sending a
# single command.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LIB="$SCRIPT_DIR/lib"
PYTHON_BIN="${PYTHON:-python3}"
DEST="${DEST:-$HOME/printer_data/config}"
URL="${MOONRAKER_URL:-http://127.0.0.1:7125}"
PROFILE=""
FROM=""
ONLY=""
SKIP=""
YES=0
DRY_RUN=0
STATE_DIR="${BRINGUP_STATE_DIR:-$HOME/printer_data/.bringup}"
HOLD_SECONDS="${BRINGUP_HOLD_SECONDS:-30}"
STAGES=(deploy tmc motion z-motion pid-e pid-b done)
DIED=0

usage() {
  cat <<'EOF'
Usage: bringup.sh -p PROFILE [options]

Первичная настройка машины: deploy -> tmc -> motion -> z-motion -> pid-e -> pid-b -> done.
Каждый этап пишет изменения в git-клон ~/vorons_configs, деплоит профиль и
перезапускает Klipper через Moonraker. Коммит и push делает владелец.

  -p, --profile ID   профиль printers/<ID> (обязательно)
      --url URL      Moonraker (по умолчанию http://127.0.0.1:7125)
      --dest DIR     живой каталог Klipper (~/printer_data/config)
      --from STAGE   начать с этапа (deploy|tmc|motion|z-motion|pid-e|pid-b|done)
      --only STAGE   выполнить только этот этап
      --skip LIST    пропустить этапы (через запятую, можно повторять)
      --state-dir D  каталог состояния (по умолчанию ~/printer_data/.bringup)
      --yes          не спрашивать подтверждение перед движением
      --dry-run      напечатать план, команды не отправлять
  -h, --help         эта справка

Гейты (без них этап не запускается):
  * git status клона пуст (есть что откатить через git checkout);
  * machine.conf валиден, committed profile.cfg не устарел, deploy --check зелёный;
  * uuids.cfg без REPLACE_WITH_;
  * anchors.cfg без TODO для этапов motion/z-motion;
  * Moonraker: Klipper ready, печать не идёт, нагреватели < 45 C.

Откат: git -C ~/vorons_configs checkout . && scripts/deploy_configs.sh -p ID -b,
затем POST /machine/restart (на Moonraker v0.10 — /machine/services/restart).
EOF
}

die() {
  DIED=1
  fail_current_stage
  echo "ERROR: $*" >&2
  exit 1
}
step() { printf '\n=== %s\n' "$*"; }
ok() { printf 'OK: %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

CURRENT_STAGE=""
fail_current_stage() {
  if [[ -n "$CURRENT_STAGE" ]] && (( ! DRY_RUN )); then
    state finish --stage "$CURRENT_STAGE" --status fail >/dev/null 2>&1 || true
  fi
}

on_error() {
  local rc=$?
  (( DIED )) && exit "$rc"
  echo "ERROR: команда завершилась с кодом $rc" >&2
  fail_current_stage
  if (( ! DRY_RUN )); then
    api log-tail 30 2>/dev/null || true
  fi
  exit "$rc"
}
trap on_error ERR

while (($#)); do
  case "$1" in
    -p|--profile) PROFILE="${2:?missing value for $1}"; shift 2 ;;
    --url)         URL="${2:?missing value for $1}"; shift 2 ;;
    --dest)        DEST="${2:?missing value for $1}"; shift 2 ;;
    --from)        FROM="${2:?missing value for $1}"; shift 2 ;;
    --only)        ONLY="${2:?missing value for $1}"; shift 2 ;;
    --skip)        SKIP="${SKIP:+$SKIP,}${2:?missing value for $1}"; shift 2 ;;
    --state-dir)   STATE_DIR="${2:?missing value for $1}"; shift 2 ;;
    --yes)         YES=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$PROFILE" ]] || { usage >&2; exit 2; }
PROFILE_DIR="$REPO/printers/$PROFILE"
[[ -d "$PROFILE_DIR" ]] || die "профиль не найден: $PROFILE_DIR"
[[ -f "$PROFILE_DIR/machine.conf" ]] || die "нет machine.conf в $PROFILE_DIR"
STATE_FILE="$STATE_DIR/$PROFILE.json"
API=("$PYTHON_BIN" "$LIB/bringup_api.py" --url "$URL")
STATE=("$PYTHON_BIN" "$LIB/bringup_state.py" --file "$STATE_FILE" --profile "$PROFILE")
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bringup.XXXXXX")"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT

api() { "${API[@]}" "$@"; }
state() { "${STATE[@]}" "$@"; }

stage_index() {
  local wanted=$1 index=0 stage
  for stage in "${STAGES[@]}"; do
    if [[ "$stage" == "$wanted" ]]; then
      echo "$index"
      return 0
    fi
    index=$((index + 1))
  done
  echo 255
}

validate_stage() {
  local name=$1 value=$2
  [[ -n "$value" ]] || return 0
  if [[ "$(stage_index "$value")" -eq 255 ]]; then
    echo "ERROR: неизвестный этап $name=$value" >&2
    exit 2
  fi
}

validate_stage --from "$FROM"
validate_stage --only "$ONLY"
if [[ -n "$SKIP" ]]; then
  IFS=',' read -r -a _skipped <<< "$SKIP"
  for skipped in "${_skipped[@]}"; do
    validate_stage --skip "$skipped"
  done
fi

# ---------------------------------------------------------------- selection

STATE_STAGE=""
if [[ -f "$STATE_FILE" ]]; then
  STATE_STAGE="$(state show | sed -n 's/^stage=//p')"
fi

START_INDEX=0
if [[ -n "$ONLY" ]]; then
  START_INDEX="$(stage_index "$ONLY")"
elif [[ -n "$FROM" ]]; then
  START_INDEX="$(stage_index "$FROM")"
elif [[ -n "$STATE_STAGE" ]] && [[ "$STATE_STAGE" != "done" ]]; then
  START_INDEX=$(( $(stage_index "$STATE_STAGE") + 1 ))
elif [[ "$STATE_STAGE" == "done" ]]; then
  START_INDEX=${#STAGES[@]}
fi

stage_enabled() {
  local stage=$1
  if [[ -n "$ONLY" ]]; then
    [[ "$stage" == "$ONLY" ]]
    return
  fi
  if [[ ",$SKIP," == *",$stage,"* ]]; then
    return 1
  fi
  [[ "$(stage_index "$stage")" -ge "$START_INDEX" ]]
}

# ---------------------------------------------------------------- pre-flight

GATE_FAILURES=()
gate_fail() { GATE_FAILURES+=("$1"); }

release_gates() {
  if ((${#GATE_FAILURES[@]} == 0)); then
    return 0
  fi
  echo "Гейты не пройдены:" >&2
  local item
  for item in "${GATE_FAILURES[@]}"; do
    printf '  - %s\n' "$item" >&2
  done
  if (( DRY_RUN )); then
    warn "dry-run: гейты не блокируют (в реальном прогоне bringup остановился бы)"
    return 0
  fi
  die "pre-flight не пройден: устраните пункты выше"
}

stage_preflight() {
  step "S0 pre-flight ($PROFILE)"
  local dirty rendered uuids
  if [[ -d "$REPO/.git" ]]; then
    dirty="$(git -C "$REPO" status --porcelain)"
    if [[ -n "$dirty" ]]; then
      gate_fail "git status не пуст (нужен чистый клон для отката):"$'\n'"$dirty"
    fi
  else
    gate_fail "нет git-клона: $REPO"
  fi

  rendered="$TMP_DIR/profile.expected"
  if ! "$PYTHON_BIN" "$REPO/scripts/render_profile.py" \
      --machine-dir "$PROFILE_DIR" --output "$rendered" >/dev/null 2>&1; then
    gate_fail "machine.conf не проходит валидацию (render_profile.py)"
  elif ! cmp -s "$rendered" "$PROFILE_DIR/profile.cfg"; then
    gate_fail "profile.cfg устарел: ./scripts/deploy_configs.sh -p $PROFILE --render"
  fi

  if ! "$REPO/scripts/deploy_configs.sh" -p "$PROFILE" --check >/dev/null 2>&1; then
    gate_fail "deploy_configs.sh --check не проходит (staging невалиден)"
  fi

  uuids="$DEST/std.config.local/uuids.cfg"
  if [[ ! -f "$uuids" ]]; then
    gate_fail "нет $uuids (сначала выполните deploy)"
  elif grep -q "REPLACE_WITH_" "$uuids"; then
    gate_fail "$uuids содержит REPLACE_WITH_ (впишите реальные UUID)"
  fi

  if grep -q "TODO" "$PROFILE_DIR/anchors.cfg" 2>/dev/null; then
    if stage_enabled motion || stage_enabled z-motion; then
      gate_fail "anchors.cfg содержит TODO: этапы motion/z-motion запрещены до измерений"
    else
      warn "anchors.cfg содержит TODO (этапы motion/z-motion пропущены, это допустимо)"
    fi
  fi

  if (( DRY_RUN )); then
    echo "dry-run: Moonraker не опрашивается (Klipper ready/idle/нагреватели <45 C)"
  else
    if ! api preflight --max-temp 45 > "$TMP_DIR/preflight.txt" 2>"$TMP_DIR/preflight.err"; then
      gate_fail "Moonraker/Klipper: $(tr '\n' ' ' < "$TMP_DIR/preflight.err")"
    else
      sed -n 's/^\(klipper_state\|print_state\|extruder\|heater_bed\)=/\1=/p' \
        "$TMP_DIR/preflight.txt"
    fi
  fi
  release_gates
  return 0
}

restart_klipper() {
  local timeout=${1:-60}
  api restart >/dev/null
  if ! api wait-ready --wait "$timeout" >/dev/null; then
    warn "Klipper не вышел в ready за ${timeout} с; последние строки klippy.log:"
    api log-tail 50 2>/dev/null || true
    return 1
  fi
  ok "Klipper ready"
}

deploy_and_restart() {
  "$REPO/scripts/deploy_configs.sh" -p "$PROFILE" -d "$DEST" -b
  restart_klipper 60
}

# ---------------------------------------------------------------- stages

stage_deploy() {
  step "S1 deploy: $PROFILE"
  if (( DRY_RUN )); then
    echo "plan: deploy_configs.sh -p $PROFILE -d $DEST -b"
    echo "plan: POST /machine/restart (fallback /machine/services/restart), ждать state=ready (60 с)"
    return 0
  fi
  deploy_and_restart
}

stage_tmc() {
  step "S2 tmc: номинальные токи и чоппер всех драйверов"
  if (( DRY_RUN )); then
    echo "plan: bringup_tmc.py plan --profile $PROFILE --repo $REPO --dest $DEST"
    echo "plan: bringup_tmc.py apply -> tmc_calc.py --update-module ... --force"
    echo "plan: deploy_configs.sh -b, restart, wait ready"
    return 0
  fi
  "$PYTHON_BIN" "$LIB/bringup_tmc.py" plan --profile "$PROFILE" \
    --repo "$REPO" --dest "$DEST"
  "$PYTHON_BIN" "$LIB/bringup_tmc.py" apply --profile "$PROFILE" \
    --repo "$REPO" --dest "$DEST" || die "расчёт TMC не применён"
  if git -C "$REPO" diff --quiet -- std.configs; then
    ok "модули TMC уже на номинале, deploy не нужен"
    return 0
  fi
  git -C "$REPO" diff --stat -- std.configs
  deploy_and_restart
  ok "TMC-модули пересчитаны (ток и чоппер) и развёрнуты"
}

stage_motion() {
  step "S3 motion: подбор max_velocity/max_accel"
  local tune_args=(--profile "printers/$PROFILE" --url "$URL" --run --apply
                   --iterations 2)
  if (( YES )); then
    tune_args+=(--yes)
  fi
  if (( DRY_RUN )); then
    printf 'plan: tmc_tune.py %s\n' "${tune_args[*]}"
    return 0
  fi
  if (( ! YES )); then
    if [[ ! -t 0 ]]; then
      die "этап motion требует подтверждения оператора (--yes в неинтерактивном режиме)"
    fi
    echo "ВНИМАНИЕ: принтер будет двигаться на предельных скоростях."
    read -r -p "Оператор у E-stop? Продолжить? [y/N] " answer
    case "$answer" in
      y|Y|yes|Yes|да|Да) ;;
      *) die "оператор не подтвердил этап motion" ;;
    esac
  fi
  if ! "$PYTHON_BIN" "$SCRIPT_DIR/tmc_tune.py" "${tune_args[@]}"; then
    die "motion-этап не завершён (Klipper shutdown или ошибка tmc_tune); PID-этапы не запускаются"
  fi
  return 0
}

stage_z_motion() {
  step "S4 z-motion: подбор max_z_velocity/max_z_accel"
  local model
  local tune_args=(--profile "printers/$PROFILE" --url "$URL" --run
                   --apply --z-test --iterations 2 --dest "$DEST")
  model="$(sed -n 's/^model=//p' "$PROFILE_DIR/machine.conf" | head -n 1)"
  if [[ "$model" == "trident" ]]; then
    warn "trident/z_tilt: перекос ловится по трём Z-моторам слабее, чем на v24; следите за гантри вручную"
  fi
  if (( YES )); then
    tune_args+=(--yes)
  fi
  if (( DRY_RUN )); then
    printf 'plan: tmc_tune.py %s\n' "${tune_args[*]}"
    return 0
  fi
  if (( ! YES )); then
    if [[ ! -t 0 ]]; then
      die "этап z-motion требует подтверждения оператора (--yes в неинтерактивном режиме)"
    fi
    echo "ВНИМАНИЕ: Z-портал будет двигаться на предельных скоростях."
    read -r -p "Оператор у E-stop? Продолжить? [y/N] " answer
    case "$answer" in
      y|Y|yes|Yes|да|Да) ;;
      *) die "оператор не подтвердил этап z-motion" ;;
    esac
  fi
  if ! "$PYTHON_BIN" "$SCRIPT_DIR/tmc_tune.py" "${tune_args[@]}"; then
    die "z-motion-этап не завершён (перекос Z, Klipper shutdown или ошибка tmc_tune)"
  fi
  return 0
}

pid_stage() {
  local heater=$1 target=$2 section=$3 timeout=$4 label=$5
  step "$label: PID_CALIBRATE $heater TARGET=$target"
  local heat_gcode sensor cursor pid_file pid_values changed
  case "$heater" in
    extruder)  heat_gcode="M104 S$target"; sensor="extruder" ;;
    heater_bed) heat_gcode="M140 S$target"; sensor="heater_bed" ;;
    *) die "unknown heater $heater" ;;
  esac
  pid_file="$TMP_DIR/pid-$heater.json"

  if (( DRY_RUN )); then
    echo "plan: PID_CALIBRATE HEATER=$heater TARGET=$target (timeout ${timeout} с)"
    echo "plan: bringup_pid.py parse -> patch printers/$PROFILE/local/pid.cfg"
    echo "plan: deploy -b, restart; затем '$heat_gcode' + TEMPERATURE_WAIT"
    echo "plan: verify-hold ${HOLD_SECONDS} с (±1.5 C), затем M104/M140 S0 и M107"
    return 0
  fi

  # Klipper executes gcode/script synchronously: this POST returns when the
  # calibration is finished, so the HTTP timeout is the calibration budget.
  cursor="$(api cursor)"
  if ! api --timeout "$((timeout + 120))" \
      gcode "PID_CALIBRATE HEATER=$heater TARGET=$target" >/dev/null; then
    warn "PID_CALIBRATE $heater прерван; нагреватель мог остаться включённым!"
    warn "проверьте принтер и при необходимости нажмите аварийный стоп"
    api --timeout 15 gcode "M104 S0" >/dev/null 2>&1 || true
    api --timeout 15 gcode "M140 S0" >/dev/null 2>&1 || true
    die "PID_CALIBRATE $heater не завершился за ${timeout} с"
  fi
  api store --count 1000 > "$pid_file"
  if [[ "$(api info | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["state"])')" != "ready" ]]; then
    api gcode "M104 S0" >/dev/null 2>&1 || true
    api gcode "M140 S0" >/dev/null 2>&1 || true
    die "Klipper не в состоянии ready после PID_CALIBRATE $heater"
  fi

  pid_values="$("$PYTHON_BIN" "$LIB/bringup_pid.py" parse --since "$cursor" < "$pid_file")" \
    || die "в gcode_store нет строки pid_Kp/pid_Ki/pid_Kd"
  eval "$pid_values"
  ok "PID $heater: Kp=$kp Ki=$ki Kd=$kd"

  changed="$("$PYTHON_BIN" "$LIB/bringup_pid.py" patch \
    --file "$PROFILE_DIR/local/pid.cfg" --section "$section" \
    --kp "$kp" --ki "$ki" --kd "$kd" | sed -n 's/^changed=//p')" \
    || die "не удалось записать $PROFILE_DIR/local/pid.cfg"
  if [[ "$changed" == "1" ]]; then
    git -C "$REPO" diff --stat -- "printers/$PROFILE/local/pid.cfg"
    deploy_and_restart
  else
    ok "pid.cfg уже содержит эти значения, deploy не нужен"
  fi

  step "$label: верификация удержания $target C"
  # Same synchronous barrier: TEMPERATURE_WAIT blocks until the heater is there.
  if ! api --timeout "$((timeout + 120))" gcode "$heat_gcode
TEMPERATURE_WAIT SENSOR=$sensor MINIMUM=$((target - 1))" >/dev/null; then
    api --timeout 15 gcode "M104 S0" >/dev/null 2>&1 || true
    api --timeout 15 gcode "M140 S0" >/dev/null 2>&1 || true
    die "нагрев до $target C не завершился за ${timeout} с"
  fi
  eval "$(api verify-hold --sensor "$sensor" --target "$target" --hold "$HOLD_SECONDS")"
  ok "выборка: samples=$samples min=$min max=$max mean=$mean"
  if (( overshoot_warn )); then
    warn "перелёт $overshoot C > 5 C: возможен перегрев, повторите калибровку"
  fi
  if (( ! within_tolerance )); then
    warn "температура вышла за ±1.5 C: проверьте вентилятор/мощность нагревателя"
  fi
  api gcode "M104 S0" >/dev/null 2>&1 || true
  api gcode "M140 S0" >/dev/null 2>&1 || true
  api gcode "M107" >/dev/null 2>&1 || true
  ok "$label завершён, нагреватели выключены"
}

stage_pid_e() { pid_stage extruder 250 extruder 1500 "S5 pid-e"; }
stage_pid_b() { pid_stage heater_bed 120 heater_bed 2700 "S6 pid-b"; }

stage_done() {
  step "S7 finalize: сводка для коммита"
  local vm_xy vm_ze velocity accel pid_list status
  vm_xy="$(sed -n 's/^vm_xy=//p' "$PROFILE_DIR/machine.conf" | head -n 1)"
  vm_ze="$(sed -n 's/^vm_ze=//p' "$PROFILE_DIR/machine.conf" | head -n 1)"
  pid_list=""
  for status in pid_e pid_b; do
    if [[ "$(state show | sed -n "s/^status_${status}=//p")" == "ok" ]]; then
      case "$status" in
        pid_e) pid_list="${pid_list}e " ;;
        pid_b) pid_list="${pid_list}bed " ;;
      esac
    fi
  done
  pid_list="${pid_list:-—}"
  velocity="—"
  accel="—"
  if (( ! DRY_RUN )); then
    eval "$(api query printer | "$PYTHON_BIN" -c '
import json, sys
data = json.load(sys.stdin).get("printer", {})
print("velocity=%s" % data.get("max_velocity", "?"))
print("accel=%s" % data.get("max_accel", "?"))
')"
    git -C "$REPO" diff --stat
  fi
  cat <<EOF

Изменения (проверьте и закоммитьте вручную):
  git -C $REPO status --porcelain
  git -C $REPO diff

Предлагаемое сообщение коммита:
  bringup($PROFILE): tmc@${vm_xy}/${vm_ze}, v/a=${velocity}/${accel}, pid ${pid_list}

Деплой уже выполнен; push и тег версии — по команде владельца.
EOF
  return 0
}

# ---------------------------------------------------------------- driver

run_stage() {
  local stage=$1
  CURRENT_STAGE="$stage"
  if (( ! DRY_RUN )); then
    state begin --stage "$stage" \
      --repo-head "$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || true)" >/dev/null
  fi
  "stage_${stage//-/_}"
  if (( ! DRY_RUN )); then
    state finish --stage "$stage" --status ok >/dev/null
  fi
  CURRENT_STAGE=""
}

printf 'bringup: профиль=%s репозиторий=%s живой каталог=%s\n' \
  "$PROFILE" "$REPO" "$DEST"
if (( DRY_RUN )); then
  echo "DRY-RUN: команды не отправляются, файлы не меняются"
fi
if [[ -n "$STATE_STAGE" ]]; then
  echo "состояние: последний завершённый этап=$STATE_STAGE"
fi

PENDING=0
for stage in "${STAGES[@]}"; do
  if stage_enabled "$stage"; then
    PENDING=$((PENDING + 1))
  fi
done
if (( PENDING == 0 )); then
  ok "нечего выполнять: профиль $PROFILE уже на этапе ${STATE_STAGE:-done}"
  exit 0
fi

stage_preflight

for stage in "${STAGES[@]}"; do
  if ! stage_enabled "$stage"; then
    continue
  fi
  run_stage "$stage"
done

ok "bringup $PROFILE завершён"