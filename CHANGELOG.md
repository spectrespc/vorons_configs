# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [семантическому версионированию](https://semver.org/lang/ru/).
Каждая запись приведена на русском и английском языках.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Every entry is provided in Russian and English.

## [Unreleased]

### Added / Добавлено

- **RU:** Схема `machine.conf` v2: явные ключи всего железа — `kinematics`,
  `z_count`, `leveling`, `xy_motor`, `z_driver`, `z_motor`, `e_motor` рядом с
  `xy_driver` (теперь только микросхема драйвера). `render_profile.py`
  проверяет согласованность с `model` (`MODEL_PROFILE`), шаг `xy_step` по
  `docs/tmc/motors.json`, наличие X/Y-модуля в обеих семьях плат и Z-модуля
  `<z_count>z-<driver>-<motor>.cfg`; при отсутствии пары подсказывает
  `tmc_calc.py --write`, при старых составных значениях (`xy_driver=tmc5160-…`,
  `extruder_motor`) выдаёт миграционную ошибку. Добавлены эталонный
  `scripts/templates/machine.conf.template` с русскими комментариями и
  `docs/PROFILES.md` (слои профиля, таблица ключей, создание профиля, добавление
  пары драйвер/мотор, готовые примеры `trident-150` и `v24-350`).
  `new_machine.sh` генерирует профиль из шаблона и получил флаги `--xy-motor`,
  `--xy-driver`, `--z-driver`, `--z-motor`, `--e-motor`.
  **EN:** `machine.conf` schema v2: explicit keys for the whole hardware —
  `kinematics`, `z_count`, `leveling`, `xy_motor`, `z_driver`, `z_motor`,
  `e_motor` next to `xy_driver` (now only the driver IC). `render_profile.py`
  checks consistency with `model` (`MODEL_PROFILE`), the `xy_step` step angle
  against `docs/tmc/motors.json`, the X/Y module in both board families and the
  Z module `<z_count>z-<driver>-<motor>.cfg`; a missing pair points to
  `tmc_calc.py --write`, and the old combined values (`xy_driver=tmc5160-…`,
  `extruder_motor`) produce an explicit migration error. Added the canonical
  `scripts/templates/machine.conf.template` with Russian comments and
  `docs/PROFILES.md` (profile layers, key table, profile creation, adding a
  driver/motor pair, ready `trident-150` and `v24-350` examples).
  `new_machine.sh` generates the profile from the template and gained
  `--xy-motor`, `--xy-driver`, `--z-driver`, `--z-motor`, `--e-motor`.

- **RU:** Новая опция профиля `eddy_f`: внешний вихретоковый щуп FLY-EDDY со
  шлейфом EDDY-F в разъёме EDDY платы SHT36 V3 / Plus V3 (аппаратный I2C
  `i2c1e`, LDC1612 по адресу `42`, датчик температуры на `extruder:gpio28`).
  Модуль `std.configs/sht36-v3.eddy-f.cfg` самодостаточен и не включает
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg`; старая ветка `eddy` (SHT36 Max V3,
  адрес `43`) не тронута. `render_profile.py` и `new_machine.sh` отклоняют
  `eddy` вместе с `eddy_f` (обе объявляют
  `[probe_eddy_current fly_eddy_probe]`), требуют `toolhead=sht36-v3`, а при
  любой eddy-фиче рендер не включает `std.configs/probe.cfg`: Klipper не
  регистрирует `[probe]` и `[probe_eddy_current]` одновременно.
  `check_config.py` считает новый модуль fleet alternative и берёт смещения
  щупа из `[probe_eddy_current ...]`, когда `[probe]` отсутствует. Обновлены
  `machine.conf.template`, `docs/PROFILES.md` и README (новый раздел
  «EDDY-F: внешний FLY-EDDY»).
  **EN:** New `eddy_f` profile option: an external FLY-EDDY probe with the
  EDDY-F FPC harness in the EDDY connector of the SHT36 V3 / Plus V3 toolboard
  (hardware I2C `i2c1e`, LDC1612 at address `42`, temperature sensor on
  `extruder:gpio28`). The `std.configs/sht36-v3.eddy-f.cfg` module is
  self-contained and does not include `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg`;
  the old `eddy` branch (SHT36 Max V3, address `43`) is untouched.
  `render_profile.py` and `new_machine.sh` reject `eddy` together with `eddy_f`
  (both declare `[probe_eddy_current fly_eddy_probe]`), require
  `toolhead=sht36-v3`, and with any eddy feature the renderer no longer includes
  `std.configs/probe.cfg`: Klipper cannot register `[probe]` and
  `[probe_eddy_current]` at the same time. `check_config.py` treats the new
  module as a fleet alternative and reads the probe offsets from
  `[probe_eddy_current ...]` when `[probe]` is absent. Updated
  `machine.conf.template`, `docs/PROFILES.md` and README (new "EDDY-F: external
  FLY-EDDY" section).

- **RU:** Гибридный Z на стенде v24-350: `features=...,eddy_f`, `[stepper_z]`
  паркуется концевиком M3-STOP (`endstop_pin: !SENS_2` в
  `machine-extras.cfg`, `position_endstop: -0.520` — дефолт в seed
  `printer.cfg` до калибровки), а
  `QUAD_GANTRY_LEVEL` и `BED_MESH_CALIBRATE` пробируют FLY-EDDY: Klipper
  выравнивает портал только через объект `probe`. `check_config.py` получил
  проверки: `[probe]` вместе с `probe_eddy_current*` — ERROR (Klipper падает
  на дублирующей регистрации `probe`), физический `endstop_pin` у
  `[stepper_z]` без `position_endstop` — ERROR, `position_endstop` рядом с
  `probe:z_virtual_endstop` — ERROR (Klipper такую опцию не читает). README и `docs/PROFILES.md`
  описывают рецепт гибрида и две калибровки.
  **EN:** Hybrid Z on the v24-350 bench: `features=...,eddy_f`, `[stepper_z]`
  parks on the M3-STOP switch (`endstop_pin: !SENS_2` in
  `machine-extras.cfg`, `position_endstop: -0.520` as the seed `printer.cfg`
  default until calibration), while
  `QUAD_GANTRY_LEVEL` and `BED_MESH_CALIBRATE` probe with FLY-EDDY: Klipper
  levels the gantry only through the `probe` object. `check_config.py` gained
  checks: `[probe]` together with `probe_eddy_current*` is an ERROR (Klipper
  aborts on the duplicate `probe` registration), a physical
  `[stepper_z] endstop_pin` without `position_endstop` is an ERROR, and
  `position_endstop` next to `probe:z_virtual_endstop` is an ERROR (Klipper
  never reads that option there). README and
  `docs/PROFILES.md` document the hybrid recipe and the two calibrations.

- **RU:** Расчёт TMC по фактическому току: `tmc_calc.py --run-current A`
  задаёт `run_current` напрямую, `i_factor` выводится из него
  (`i_factor_effective`), а `--json` и отчёт печатают источник входов
  `tbl_source`/`toff_source` (`cli|module|profile`). `--update-module` без явного
  `--tbl/--toff` сохраняет значение секции. В `machine.conf` добавлены пары
  входов чоппера `xy_tbl/xy_toff`, `z_tbl/z_toff`, `e_tbl/e_toff`
  (`render_profile.py` проверяет TBL 0..3 и TOFF 1..15), шаблон и оба профиля
  обновлены. Новый макрос `std.macros/test_speed_z.cfg` (`TEST_SPEED_Z`) и
  контур `tmc_tune.py --z-test` (лестница `max_z_velocity`/`max_z_accel`,
  `--z-travel/--z-floor/--z-max-velocity/--z-max-accel/--z-max-runs/
  --z-offline-result`) подбирают лимиты Z по отдельным счётчикам каждого
  Z-мотора с детектом перекоса; `bringup.sh` получил этап `z-motion`.
  `check_config.py` закрепил инвариант SpreadCycle (ERROR при активном
  `stealthchop_threshold >= 1000`, WARNING при отсутствии ключа) для всего
  `std.configs/**` и `printers/*/local/**`, а `bringup_tmc.py` отказывает
  stealthchop-секции вместо тихого выбрасывания регистров.
  **EN:** TMC calculation at the actual current: `tmc_calc.py --run-current A`
  sets `run_current` directly, `i_factor` is derived (`i_factor_effective`), and
  `--json` plus the report print the input source `tbl_source`/`toff_source`
  (`cli|module|profile`). `--update-module` keeps the section value when
  `--tbl/--toff` is not given. `machine.conf` gained the chopper input pairs
  `xy_tbl/xy_toff`, `z_tbl/z_toff`, `e_tbl/e_toff` (`render_profile.py` checks
  TBL 0..3 and TOFF 1..15); the template and both profiles are updated. New
  `std.macros/test_speed_z.cfg` (`TEST_SPEED_Z`) and the `tmc_tune.py --z-test`
  loop (ladder over `max_z_velocity`/`max_z_accel`,
  `--z-travel/--z-floor/--z-max-velocity/--z-max-accel/--z-max-runs/
  --z-offline-result`) tune the Z limits from each Z motor's own step counter
  and detect skew; `bringup.sh` gained the `z-motion` stage. `check_config.py`
  enforces the SpreadCycle invariant (ERROR for an active
  `stealthchop_threshold >= 1000`, WARNING for a missing key) across all
  `std.configs/**` and `printers/*/local/**`, and `bringup_tmc.py` refuses a
  StealthChop section instead of silently dropping the registers.

- **RU:** `QUAD_GANTRY_LEVEL` на v24 стал двухпроходным: голый вызов
  (`PRINT_START`, кнопка, `TEST_SPEED`, `tmc_tune.py`) сначала выравнивает
  портал грубым descend-проходом (`RETRY_TOLERANCE=0.25`, `RETRIES=2`), затем
  `_QGL_ZERO_PROBE` измеряет абсолютную высоту стола командой `PROBE` в точке
  `zero_reference_position`, а `_QGL_FINE` запускает точный `METHOD=scan` с
  `HORIZONTAL_MOVE_Z = измеренный Z + descend_z`. Это именно два отдельных
  макроса: шаблон `gcode_macro` рендерится целиком до выполнения G-code и не
  видит результат `PROBE` из того же тела. Если контрольный замер вышел за
  `MAX_ZERO_DEV` (0.5 мм), макрос прерывается до scan-прохода с требованием
  `Z_ENDSTOP_CALIBRATE` + `Z_OFFSET_APPLY_PROBE` (предупреждение — с 0.05 мм).
  Вызов с любым параметром остаётся одним проходом, на физическом `[probe]`
  тоже один descend. Отдельный `G1 Z10` до и после контрольного `PROBE`
  обязателен: с `SAMPLES=1` сопло остаётся на высоте срабатывания.
  **EN:** `QUAD_GANTRY_LEVEL` on v24 is now two-pass: a bare call
  (`PRINT_START`, the button, `TEST_SPEED`, `tmc_tune.py`) levels the gantry
  with a rough descend pass first (`RETRY_TOLERANCE=0.25`, `RETRIES=2`), then
  `_QGL_ZERO_PROBE` measures the absolute bed height with `PROBE` at the
  `zero_reference_position` point, and `_QGL_FINE` starts the precise
  `METHOD=scan` pass with `HORIZONTAL_MOVE_Z = measured Z + descend_z`. They
  are separate macros because a `gcode_macro` template is rendered in full
  before its G-code runs and cannot see a `PROBE` result from the same body.
  If the check probe exceeds `MAX_ZERO_DEV` (0.5 mm), the macro aborts before
  the scan and asks for `Z_ENDSTOP_CALIBRATE` + `Z_OFFSET_APPLY_PROBE` (a
  warning starts at 0.05 mm). A call with any parameter stays a single pass,
  and a physical `[probe]` also keeps the single descend pass. The explicit
  `G1 Z10` before and after the check `PROBE` is required because with
  `SAMPLES=1` the nozzle stays at the trigger height.

- **RU:** Автообновление живых конфигов через Moonraker: `update_manager`
  только тянет репозиторий (Moonraker не исполняет `install_script`), поэтому
  новый `scripts/install_config_update_hook.sh` ставит systemd path/timer
  (`klipper-configs-deploy.path/.timer`), который запускает
  `scripts/moonraker_update.sh --auto` от пользователя принтера. Хук
  определяет профиль по маркеру `~/printer_data/config/.deployed_profile`
  (fallback — побайтное сравнение живого `machine.conf` с рендером
  `render_profile.py --dump-conf` каждого профиля), пропускает работу при
  совпадении `DEST/.deployed_commit` с `HEAD`, деплоит профиль, идемпотентно
  приводит `[update_manager vorons_configs]` в живом `moonraker.conf` к
  канонической записи, перезапускает Klipper через API Moonraker и пишет stamp
  только после успешного перезапуска; ошибка деплоя оставляет прежние живые
  конфиги, таймер повторяет попытку. Новый хелпер
  `scripts/lib/moonraker_conf.py ensure --config FILE` (текстовый upsert, дубли
  на тот же `path:`/`origin:` схлопываются, комментарии и посторонние секции
  сохраняются, есть `selftest`) вызывается и из `deploy_configs.sh`, который
  теперь пишет маркер профиля после фактической записи файлов. Профильные
  `moonraker.conf` и шаблон `new_machine.sh` получили каноническую секцию без
  `managed_services`/`install_script`; устаревшие
  `voron_standart_configs`/`voron_personal_configs` из `v24-350` удалены.
  **EN:** Live configs now update through Moonraker: `update_manager` only
  pulls the repository (Moonraker does not execute `install_script`), so the
  new `scripts/install_config_update_hook.sh` installs systemd path/timer units
  (`klipper-configs-deploy.path/.timer`) that run
  `scripts/moonraker_update.sh --auto` as the printer user. The hook detects
  the profile from the `~/printer_data/config/.deployed_profile` marker
  (fallback: byte comparison of the live `machine.conf` with each profile's
  `render_profile.py --dump-conf` output), skips the work when
  `DEST/.deployed_commit` equals `HEAD`, deploys the profile, idempotently
  normalizes `[update_manager vorons_configs]` in the live `moonraker.conf`,
  restarts Klipper through the Moonraker API and writes the stamp only after a
  successful restart; a deploy failure leaves the previous live configs and the
  timer retries. The new `scripts/lib/moonraker_conf.py ensure --config FILE`
  helper (text upsert, duplicates on the same `path:`/`origin:` collapsed,
  comments and unrelated sections preserved, `selftest` included) is also
  called by `deploy_configs.sh`, which now writes the profile marker after the
  actual file writes. The profile `moonraker.conf` files and the
  `new_machine.sh` template carry the canonical entry without
  `managed_services`/`install_script`; the legacy
  `voron_standart_configs`/`voron_personal_configs` entries in `v24-350` are
  removed.

### Changed / Изменено

- **RU:** `[input_shaper]` стенда v24-350 перекалиброван по методике Klipper
  Measuring Resonances (2026-11-23, lis2dw на sht36-v3, `axes_map: -y,z,-x`):
  X 71.0 Гц `ei` → 51.2 Гц `mzv` (пик 50 Гц в `psd_x`, остаточные вибрации
  0.4 %, сглаживание 0.078), Y 64.0 Гц `2hump_ei` → 38.2 Гц `mzv` (пик 37.3 Гц
  в `psd_y`, 0.0 %, 0.140). Старые значения были сняты до перевода X/Y на
  TMC5160 и не соответствуют текущей механике; `max_accel: 8500` оставлен
  без изменений (при mzv 38.2 Гц Klipper советует не выше 4300 — это осознанный
  компромисс по скорости). Значения лежат в
  `printers/v24-350/local/input.shaper.cfg`, `SAVE_CONFIG` не используется.
  Пять прогонов `TEST_RESONANCES AXIS=Y` дали 33.5–37.3 Гц: пик уезжает вниз и
  размазывается (FWHM 7.8 → 9.4 Гц, вертикальное плечо уходит на 60–65 Гц),
  если замерять на перекошенном портале. После `QUAD_GANTRY_LEVEL` (rough
  1.876 → 0.045 мм, fine 0.0085 мм) пик стал одиночным и острым
  (37.3 Гц, Q ≈ 4.8), поэтому принято значение этой серии, а не среднее 35.7 Гц.
  **EN:** The v24-350 bench `[input_shaper]` was recalibrated with Klipper's
  Measuring Resonances procedure (2026-11-23, lis2dw on sht36-v3,
  `axes_map: -y,z,-x`): X 71.0 Hz `ei` → 51.2 Hz `mzv` (50 Hz peak in
  `psd_x`, 0.4 % residual vibrations, 0.078 smoothing), Y 64.0 Hz `2hump_ei`
  → 38.2 Hz `mzv` (37.3 Hz peak in `psd_y`, 0.0 %, 0.140). The old values were
  taken before X/Y moved to TMC5160 and no longer match the mechanics;
  `max_accel: 8500` is intentionally unchanged (at mzv 38.2 Hz Klipper
  suggests no more than 4300). The values live in
  `printers/v24-350/local/input.shaper.cfg`, `SAVE_CONFIG` is not used.
  Five `TEST_RESONANCES AXIS=Y` runs produced 33.5–37.3 Hz: the peak drifts down
  and smears (FWHM 7.8 → 9.4 Hz, the vertical shoulder moves to 60–65 Hz) when
  the gantry is skewed during the measurement. After `QUAD_GANTRY_LEVEL`
  (rough 1.876 → 0.045 mm, fine 0.0085 mm) the peak became single and sharp
  (37.3 Hz, Q ≈ 4.8), so the value from that series was chosen over the
  35.7 Hz mean.

- **RU:** Лестница +15 % (750/8500 → 1500/15000) на v24-350 (2026-11-23,
  baseline A, без VHIGH, 3 повтора на клетку, критерий 0.1 мм: 32 счётчика
  при 64 микрошагах, 64 при 128). При 64 критерий держит только стартовая
  750/8500, при 128 — непрерывно до 992/11241; 1141/12927 проваливает обе
  серии, выше снова чисто (провалы не монотонны). `diag4` на всех провальных
  клетках даёт `patterns 0/0` и весь сдвиг в `rehome` (до 2544 счётчиков =
  4.0 мм при 128), то есть уезжает привязка гоминга, а не теряются шаги.
  1500 мм/с при 128 — 960 кГц на мотор; Manta M8P выдержал без
  `Timer too close`/`Stepper move too late`. `LOST_STEPS` = 0, CAN без
  `rx_error`/`tx_error`. Применённые 750/8500 и микрошаги 64 не меняются.
  **EN:** A +15 % ladder (750/8500 → 1500/15000) on the v24-350 bench
  (2026-11-23, baseline A, no VHIGH, 3 repeats per cell, 0.1 mm criterion:
  32 counts at 64 microsteps, 64 at 128). At 64 only the starting 750/8500
  holds the criterion; at 128 it holds contiguously up to 992/11241;
  1141/12927 fails both series and the cells above are clean again (the
  failures are not monotonic). `diag4` on every failing cell gives
  `patterns 0/0` and moves the whole drift into `rehome` (up to 2544 counts =
  4.0 mm at 128), i.e. the homing reference moves, the steps are kept.
  1500 mm/s at 128 is 960 kHz per motor; the Manta M8P handled it with no
  `Timer too close`/`Stepper move too late`. `LOST_STEPS` stayed 0, CAN had
  no `rx_error`/`tx_error`. The applied 750/8500 and microsteps 64 stay.

- **RU:** X/Y с 128 микрошагами проверены той же серией +50 % (2026-11-23,
  baseline A, без VHIGH). Клетки 1000/12750, 1125/8500 и 1125/12750 — 3/3,
  1125/10000 — 1/3 (`dy` ≈ -507 счётчиков). `diag4` на 1125/10000 даёт
  `patterns 0/0` и сдвиг rehome до 1535 счётчиков (2.4 мм), то есть предел —
  привязка гоминга, а не разрешение шага. 128 микрошагов — это 640 шагов/мм
  (1125 мм/с = 720 кГц на мотор), Manta M8P выдержал без `Timer too close`.
  Применённый дефолт остаётся 64: 1125/10000 не проходит, а у 64 уже есть
  длинная тепловая и качественная история. **EN:** X/Y at 128 microsteps went
  through the same +50 % series (2026-11-23, baseline A, no VHIGH). The
  1000/12750, 1125/8500 and 1125/12750 cells passed 3/3, 1125/10000 passed
  1/3 (`dy` ≈ -507 counts). `diag4` on 1125/10000 gives `patterns 0/0` and a
  re-home shift of up to 1535 counts (2.4 mm), so the limit is the homing
  reference, not the step resolution. 128 microsteps is 640 steps/mm
  (1125 mm/s = 720 kHz per motor); the Manta M8P handled it with no
  `Timer too close`. The applied default stays 64: 1125/10000 does not pass,
  and 64 already has a long thermal and print-quality history.

- **RU:** В LDO-модулях X/Y (`manta-m5p`, `manta-m8p`) у драйвера Y включён
  `diag1_pin: DIAG_1` по умолчанию — так же, как `DIAG_0` у X. Опция только
  выводит DIAG1 драйвера; `CHOPCONF` и остальные регистры не меняются.
  **EN:** The LDO X/Y modules (`manta-m5p`, `manta-m8p`) now enable
  `diag1_pin: DIAG_1` on the Y driver by default, matching `DIAG_0` on X.
  The option only routes the driver's DIAG1 output; `CHOPCONF` and the other
  registers are unchanged.

- **RU:** Ревью `klipper_tmc_autotune` и замер огибающей +50 % на v24-350
  (2026-11-23). Модуль в парк **не берём**: он переписывает посчитанные
  `tmc_calc.py` регистры поверх конфига на `klippy:ready`, включает
  StealthChop/`interpolate: true`/CoolStep для Z и экструдера (конфликт с
  парковыми инвариантами) и сам держит `VHIGHFS`/`VHIGHCHM` выключенными.
  Из него взята только сверка констант: `ldo-42sth48-2804ah` в его
  `motor_database.cfg` = 0.7 Ом / 0.6 мГн / 2.8 А / 0.42 Н·м, что совпадает
  с `docs/tmc/motors.json`; поэтому мотор парка переименован в
  `LDO-42STH48-2804AH-R` без пересчёта токов и чоппера (обновлены каталожные
  модули `manta-m5p`/`manta-m8p`, ключ `motors.json`, профиль v24-350,
  скрипты и документация; исторические записи CHANGELOG не переписаны).
  Серия +50 % от применённых 750/8500 (1125 мм/с, 12750 мм/с²) на чистом
  baseline: 1125/12750 — 3/3 pass (`|Δ| ≤ 7`), 1000/12750 — 2/3 fail,
  1125/8500 — 1/3 fail, 1125/10000 — 3/3 fail (`|Δ|` до 505 счётчиков МКУ,
  полный шаг 64). `diag4` на провальных клетках дал `patterns 0/0` и сдвиг
  `rehome` ±512 (8 полных шагов): уезжает привязка гоминга после прогона,
  паттерн шаги не теряет. `LOST_STEPS` = 0, TMC 54.9–56.0 °C, CAN
  `bus_state=active` без `rx_error`/`tx_error`. Лимиты `[printer] 750/8500`
  не меняются: монотонно пройденной клетки выше 1125/8500 нет.
  **EN:** Review of `klipper_tmc_autotune` and the +50 % envelope measurement
  on the v24-350 bench (2026-11-23). The module is **not adopted**: it
  overwrites the `tmc_calc.py` registers on `klippy:ready`, enables
  StealthChop/`interpolate: true`/CoolStep for Z and the extruder (a conflict
  with the fleet invariants), and itself keeps `VHIGHFS`/`VHIGHCHM` off. Only
  its constant cross-check is used: `ldo-42sth48-2804ah` in
  `motor_database.cfg` is 0.7 Ohm / 0.6 mH / 2.8 A / 0.42 Nm, matching
  `docs/tmc/motors.json`, so the fleet motor is renamed to
  `LDO-42STH48-2804AH-R` with no current or chopper recalculation (catalog
  modules under `manta-m5p`/`manta-m8p`, the `motors.json` key, the v24-350
  profile, scripts and docs are updated; historical CHANGELOG records are left
  untouched). The +50 % series over the applied 750/8500 (1125 mm/s,
  12750 mm/s^2) on the pure baseline: 1125/12750 passed 3/3 (`|Δ| ≤ 7`),
  1000/12750 failed 2/3, 1125/8500 failed 1/3, 1125/10000 failed 3/3
  (`|Δ|` up to 505 MCU counts, one full step is 64). `diag4` on the failing
  cells reported `patterns 0/0` and a `rehome` shift of ±512 (8 full steps):
  the homing reference moves after the run, the pattern keeps its steps.
  `LOST_STEPS` was 0, TMC temperature 54.9-56.0 C, CAN `bus_state=active`
  with no `rx_error`/`tx_error`. The `[printer] 750/8500` limits stay: there
  is no monotonically passed cell above 1125/8500.

- **RU:** `check_config.py` ловит поломки конфигурации TMC до деплоя.
  Неизвестная опция `driver_*` — теперь **ERROR**: Klipper читает только
  поля из `set_config_field()`, поэтому `driver_THIGH: 40` роняет старт с
  `Option 'driver_THIGH' is not valid in section …`; легальный список берётся
  из `DRIVER_KEYS` в `tmc_calc.py` (единый источник, без второй копии).
  `driver_VHIGHFS: 1` без положительного `high_velocity_threshold` — **ERROR**
  (при `THIGH=0` полный шаг включён на любой скорости, измерительные поездки
  квантуются), `driver_VHIGHCHM: 1` без порога — **WARNING** (постоянный
  высокоскоростной чоппер, upstream называет смену режима на низкой скорости
  «poor and confusing»), порог без включённых битов — **NOTICE**. Проверки
  читают смерженный профиль, поэтому порог в `machine-extras.cfg` и биты в
  каталожном модуле не конфликтуют. `tmc_calc.py --selftest` дополнен кейсом:
  `high_velocity_threshold` и `driver_VHIGHFS/CHM` переживают
  `--update-module` и не попадают в предупреждения о неизвестных ключах.
  **EN:** `check_config.py` now catches TMC configuration breakage before a
  deploy. An unknown `driver_*` option is an **ERROR**: Klipper only reads
  fields registered with `set_config_field()`, so `driver_THIGH: 40` aborts
  startup with `Option 'driver_THIGH' is not valid in section …`; the legal
  list comes from `DRIVER_KEYS` in `tmc_calc.py` (one source, no second copy).
  `driver_VHIGHFS: 1` without a positive `high_velocity_threshold` is an
  **ERROR** (`THIGH=0` means full step at any speed, so probing and mesh moves
  get quantized), `driver_VHIGHCHM: 1` without a threshold is a **WARNING**
  (permanent high-velocity chopper, which upstream calls "poor and confusing"
  at low speed), and a threshold with neither bit enabled is a **NOTICE**. The
  checks read the merged profile, so a threshold in `machine-extras.cfg` and
  the bits in a catalog module do not conflict. `tmc_calc.py --selftest` gained
  a case proving that `high_velocity_threshold` and `driver_VHIGHFS/CHM`
  survive `--update-module` and are not reported as unknown keys.

- **RU:** Полношаговый переход TMC5160 по скорости (THIGH/VHIGHFS/VHIGHCHM)
  проверен на стенде v24-350 2026-11-22 и **не применён**. Механизм
  подтверждён: `SET_TMC_FIELD FIELD=thigh VELOCITY=500` даёт `THIGH=19` на
  обеих осях, биты `vhighfs`/`vhighchm` видны в `CHOPCONF`, `fsactive=1` — в
  9 из 11 сэмплов `DRV_STATUS` в движении и ни разу во всех 11 сэмплах в
  покое. Выигрыша нет: при 64 микрошагах базовая линия (`thigh=0`, биты 0)
  проходит 750/8500, 900/9000 и 900/10000 в 3/3 без потерь (`|Δ| ≤ 35`
  счётчиков МКУ, полный шаг — 64), вариант «только CHM» так же чист (9/9,
  `|Δ| ≤ 31`), а гейт требует провала baseline. Во время C toolhead-MCU
  `extruder` отвалился (за 1 с 6288 `rx_error` и 6333 `tx_retries`, затем
  таймаут), шина при этом осталась жива; причина — отошедший разъём CAN/питания
  на SHT36. После его посадки серия C/D повторена: C 9/9 чисто
  (`|Δ| ≤ 10`), D 9/9, кроме одного прогона 750/8500 со сдвигом +515
  счётчиков по одному мотору (то же редкое событие «~8 полных шагов», что и в
  baseline, без ошибок CAN в этом окне). Дополнительно измерены скорости выше
  1000 мм/с: 1000–1200 мм/с при ускорении 8500 проходят и в baseline, и в full
  step, а 1100/10000 теряет ~8 полных шагов в обеих конфигурациях — выигрыша
  нет; сам паттерн шагов не теряет (смещение появляется после финального
  `G28`, то есть сдвигается привязка гоминга). Данные,
  вывод «не применять» и предупреждение о том, что `INIT_TMC` не сбрасывает
  `vhighfs`/`vhighchm` (только рестарт), записаны в
  `printers/v24-350/machine-extras.cfg` и в README.
  **EN:** The TMC5160 full-step switch on speed (THIGH/VHIGHFS/VHIGHCHM) was
  tested on the v24-350 bench on 2026-11-22 and is **not applied**. The
  mechanism is confirmed: `SET_TMC_FIELD FIELD=thigh VELOCITY=500` gives
  `THIGH=19` on both axes, `vhighfs`/`vhighchm` show up in `CHOPCONF`, and
  `fsactive=1` appeared in 9 of 11 `DRV_STATUS` samples during motion and in
  none of the 11 standstill samples. There is no gain: at microsteps 64 the
  baseline (`thigh=0`, both bits 0) passes 750/8500, 900/9000 and 900/10000
  in 3/3 without loss (`|Δ| ≤ 35` MCU counts, one full step is 64), the
  CHM-only variant is equally clean (9/9, `|Δ| ≤ 31`), and the gate requires a
  baseline failure. During C the `extruder` toolhead MCU dropped out (6288
  `rx_error` and 6333 `tx_retries` within one second, then a timeout) while the
  bus itself stayed alive; the cause was the CAN/power connector on the SHT36
  coming loose during the high-speed runs. After it was re-seated the C/D
  series was repeated: C 9/9 clean (`|Δ| ≤ 10`), D 9/9 apart from one
  750/8500 run with a +515 count shift on one motor (the same rare
  ~8-full-step event seen in baseline, no CAN errors in that window).
  Speeds above 1000 mm/s were measured too: 1000-1200 mm/s at accel 8500 pass
  in both baseline and full step, 1100/10000 loses ~8 full steps in both, so
  full step gives no gain; the pattern itself keeps its steps (the drift shows
  up after the final `G28`, i.e. the homing reference shifts). The data, the "do not apply" conclusion
  and the warning that `INIT_TMC` does not clear `vhighfs`/`vhighchm` (only a
  restart does) are recorded in `printers/v24-350/machine-extras.cfg` and the
  README.

- **RU:** Лимиты `[printer]` подняты до рекомендованных значений для 64
  микрошагов: v24 — `max_velocity: 300 → 750`, `max_accel: 3000 → 8500`;
  trident — `max_velocity: 700 → 750`, `max_accel: 10000 → 8500`. Значения
  взяты из измеренной таблицы `printers/v24-350/machine-extras.cfg`:
  на стенде v24-350 при 64 микрошагах весь диапазон до 900 мм/с и
  10000 мм/с² прошёл без потерь, применено с запасом ~15 %. На самом trident
  замер не повторялся: 750 мм/с при 400 шагах/мм — это 300 кГц, поэтому на
  первых прогонах надо смотреть на ошибки шагового генератора; прежние
  700/10000 были каталожными. Собственные скорости `bed_mesh`, QGL и
  `PRINT_START` не менялись, `RESTORE_DEFAULT_SETTING` вернёт новый
  `max_accel`.
  **EN:** `[printer]` limits raised to the recommended values for 64
  microsteps: v24 - `max_velocity: 300 -> 750`, `max_accel: 3000 -> 8500`;
  trident - `max_velocity: 700 -> 750`, `max_accel: 10000 -> 8500`. The values
  come from the measured table in `printers/v24-350/machine-extras.cfg`: on
  the v24-350 bench at 64 microsteps the whole range up to 900 mm/s and
  10000 mm/s^2 passed without loss, and ~15 % margin is applied. The trident
  itself was not re-measured: 750 mm/s at 400 steps/mm is 300 kHz, so the first
  runs should watch for step-generation errors; the former 700/10000 were
  catalog values. `bed_mesh`, QGL and `PRINT_START` keep their own speeds, and
  `RESTORE_DEFAULT_SETTING` restores the new `max_accel`.

- **RU:** Микрошаг X/Y по умолчанию 32 → 64 в
  `std.configs/mechanics/v24.cfg` и `std.configs/mechanics/trident.cfg`.
  Основание — замеры `TEST_SPEED` на стенде v24-350 (2026-11-22): при 32
  микрошагах в диапазоне 700–900 мм/с × 3000–10000 мм/с² мотор A терял шаги
  (700/10000 воспроизводимо ~0.8 мм, 1000/3000 — до 2.4 мм), при 64 ни одна
  клетка не превысила один полный шаг (максимум смещения 0.17 мм против
  0.22 мм у 32). Один полный шаг остаётся 0.2 мм: 320 шагов/мм у v24,
  400 шагов/мм у trident, то есть 192 кГц при 300 мм/с и 280 кГц при
  700 мм/с — оба значения проверены на Manta M8P. Z и экструдеры не
  изменены, лимиты `[printer]` тоже. Измеренная таблица рекомендованных
  значений для 32/64/128 остаётся в
  `printers/v24-350/machine-extras.cfg`. На самом trident 64 ещё не
  перемерялись.
  **EN:** X/Y microsteps default 32 -> 64 in
  `std.configs/mechanics/v24.cfg` and `std.configs/mechanics/trident.cfg`.
  Based on `TEST_SPEED` on the v24-350 bench (2026-11-22): at 32 microsteps
  inside 700-900 mm/s x 3000-10000 mm/s^2 the A motor lost steps (700/10000
  reproducibly ~0.8 mm, 1000/3000 up to 2.4 mm), while at 64 no cell exceeded
  one full step (worst displacement 0.17 mm against 0.22 mm at 32). One full
  step stays 0.2 mm: 320 steps/mm on v24, 400 steps/mm on trident, i.e.
  192 kHz at 300 mm/s and 280 kHz at 700 mm/s - both verified on the Manta
  M8P. Z and the extruders are unchanged, as are the `[printer]` limits. The
  measured recommendation table for 32/64/128 stays in
  `printers/v24-350/machine-extras.cfg`. The trident itself has not been
  re-measured yet.

- **RU:** Eddy-смещение щупа стало фактом профиля `v24-350`:
  `[probe_eddy_current fly_eddy_probe] x_offset: 0, y_offset: 33` в
  `machine-extras.cfg` (центр катушки за соплом на 33 мм по +Y, замер
  2026-11-21; конвенция Klipper — «щуп минус сопло»). Комментарии
  плейсхолдеров в `std.configs/sht36-v3.eddy.cfg` и `…eddy-f.cfg` переписаны
  под эту конвенцию. `_QGL_ZERO_PROBE` переименован в `_ZERO_REF_PROBE` и
  компенсирует смещение (сопло = точка стола − offset), поэтому guard и
  высота scan считаются по столу в `175,175`, а не в `175,208`. Якоря QGL
  профиля заданы как «точка стола − offset»
  (`points: 50,27 / 50,257 / 300,257 / 300,27`) и симметричны относительно
  175. `BED_MESH_CALIBRATE` на eddy-машинах обёрнут
  (`rename_existing: BED_MESH_CALIBRATE_BASE`): голый вызов делает контрольный
  `PROBE` и scan на `bed_z + descend_z`, `METHOD=...` идёт прямым проходом, а
  явный `HORIZONTAL_MOVE_Z=` перекрывает расчёт. Сетка v24-350 расширена до
  достижимого максимума `mesh_min: 12,35`, `mesh_max: 338,338`,
  `probe_count: 15,14` (передняя граница — ход сопла при `y_offset: 33`,
  задняя и боковые — маржа 12 мм под катушкой; ~8 мин scan-прогона). Guard
  `_QGL_FINE` печатает полный цикл нуля с `SET_GCODE_OFFSET`.
  `check_config.py`: ERROR, если катушка в `points` QGL/z_tilt/resonance или
  `mesh_min`/`mesh_max` выходит за лимиты или стол (проверяются оба набора
  границ), WARNING о ручной компенсации якорей и NOTICE с расчётной
  достижимой зоной, когда сетка меньше 0.8 её площади.
  **EN:** The eddy probe offset became a profile fact on `v24-350`:
  `[probe_eddy_current fly_eddy_probe] x_offset: 0, y_offset: 33` in
  `machine-extras.cfg` (the coil centre sits 33 mm behind the nozzle on +Y,
  measured 2026-11-21; the Klipper convention is "probe minus nozzle"). The
  placeholder comments in `std.configs/sht36-v3.eddy.cfg` and `…eddy-f.cfg`
  were rewritten to that convention. `_QGL_ZERO_PROBE` became `_ZERO_REF_PROBE`
  and compensates the offset (nozzle = bed point - offset), so the guard and
  the scan height are computed for the bed point `175,175` instead of the
  nozzle position `175,208`. The profile's QGL anchors are written as
  "bed point - offset" (`points: 50,27 / 50,257 / 300,257 / 300,27`) and are
  symmetric about 175. `BED_MESH_CALIBRATE` is wrapped on eddy machines
  (`rename_existing: BED_MESH_CALIBRATE_BASE`): a bare call runs a check
  `PROBE` and a scan at `bed_z + descend_z`, `METHOD=...` stays a direct pass,
  and an explicit `HORIZONTAL_MOVE_Z=` overrides the calculated value. The
  v24-350 mesh grew to the reachable maximum `mesh_min: 12,35`,
  `mesh_max: 338,338`, `probe_count: 15,14` (front boundary is the nozzle
  travel at `y_offset: 33`, rear and sides the 12 mm coil margin; ~8 min scan
  run). The `_QGL_FINE` guard prints the full zero cycle including
  `SET_GCODE_OFFSET`. `check_config.py` gained an ERROR when the coil in QGL /
  z_tilt / resonance points or in `mesh_min`/`mesh_max` leaves the limits or
  the bed (both boundary sets are checked), a WARNING about manual anchor
  compensation and a NOTICE with the calculated reachable zone when the mesh
  is below 0.8 of its area.

- **RU:** `deploy_configs.sh` теперь управляет `printer.cfg` до маркера
  `#*# <---------------------- SAVE_CONFIG ---------------------->`: при каждом
  деплое голова файла заменяется копией из `printers/<id>/printer.cfg`, а
  маркер и autosave-блок ниже сохраняются побайтно. Новый
  `scripts/merge_printer_cfg.py` собирает файл и комментирует опции головы,
  которые определяет autosave — иначе Klipper отдаёт приоритет обычному
  конфигу и калибровка теряется. `check_config.py` читает autosave-блок так же,
  как Klipper (снимает префикс `#*# `), поэтому staging и деплой-проверки видят
  калиброванные значения; `printer.cfg` переведён из seed в частично
  управляемые.
  **EN:** `deploy_configs.sh` now manages `printer.cfg` up to the
  `#*# <---------------------- SAVE_CONFIG ---------------------->` marker: every
  deploy replaces the head with `printers/<id>/printer.cfg` and keeps the marker
  and the autosave block below it verbatim. The new
  `scripts/merge_printer_cfg.py` builds that file and comments head options that
  the autosave also defines - otherwise Klipper prefers the regular config and
  the calibration is lost. `check_config.py` reads the autosave block the way
  Klipper does (strips the `#*# ` prefix), so staging and deploy checks see the
  calibrated values; `printer.cfg` moved from seed to partially managed.

- **RU:** В гибридном Z профиля `v24-350` значение `[stepper_z]
  position_endstop` перенесено из `machine-extras.cfg` в seed-файл
  `printer.cfg`: это индивидуальная настройка, и теперь её штатно сохраняет
  `Z_ENDSTOP_CALIBRATE` + `SAVE_CONFIG` (в main-файле строка-плейсхолдер
  комментируется, значение уходит в autosave). Включаемый файл для
  `SAVE_CONFIG` не годится — Klipper падает с `... conflicts with included
  value`. `check_config.py` считает `printer.cfg` слоем-оверрайдом, поэтому
  повторное открытие `[stepper_z]` больше не даёт лишнего WARNING. Дефолт
  seed-файла для этого профиля — `position_endstop: -0.520`; в генератор
  `new_machine.sh` добавлен закомментированный блок-подсказка с тем же
  значением. Новая ERROR в `check_config.py`: `position_endstop` рядом с
  `probe:z_virtual_endstop` (Klipper такую опцию не читает и падает с
  `Option 'position_endstop' is not valid`).
  **EN:** For the `v24-350` hybrid Z the `[stepper_z] position_endstop` value
  moved from `machine-extras.cfg` into the seed `printer.cfg`: it is a
  per-machine setting, and `Z_ENDSTOP_CALIBRATE` + `SAVE_CONFIG` now persists it
  as intended (the placeholder line in the main file is commented out and the
  value lands in the autosave). An included file cannot be used for that —
  Klipper fails with `... conflicts with included value`. `check_config.py`
  treats `printer.cfg` as an override layer, so reopening `[stepper_z]` no
  longer raises a spurious WARNING. The seed default for this profile is
  `position_endstop: -0.520`, and `new_machine.sh` now emits a commented
  hint block with the same value. New ERROR in `check_config.py`:
  `position_endstop` next to `probe:z_virtual_endstop` (Klipper never reads
  that option and aborts with `Option 'position_endstop' is not valid`).

- **RU:** На v24 от 250 мм Z переведён на `17HS19-2004S1` (2.0 A peak →
  1.4142 A RMS, `HSTRT/HEND = 0/0`, `TBL=0`): добавлен модуль
  `4z-tmc2209-17hs19-2004s1.cfg`, профиль `v24-350` переключён на него, а
  `render_profile.py`/`new_machine.sh` выбирают мотор Z по модели и размеру
  (v24 ≥ 250 — `17HS19-2004S1`, иначе `17HS4401S`). Мотор добавлен в
  `docs/tmc/motors.json` с даташитными 2.0 A/1.4 Ом/3.0 мГн.
  **EN:** On v24 from 250 mm the Z motors are `17HS19-2004S1` (2.0 A peak ->
  1.4142 A RMS, `HSTRT/HEND = 0/0`, `TBL=0`): the new
  `4z-tmc2209-17hs19-2004s1.cfg` module is used by the `v24-350` profile, and
  `render_profile.py`/`new_machine.sh` pick the Z motor by model and size
  (v24 >= 250 -> `17HS19-2004S1`, otherwise `17HS4401S`). The motor is in
  `docs/tmc/motors.json` with the datasheet 2.0 A/1.4 Ohm/3.0 mH values.

- **RU:** Ток X/Y и Z считается от пикового значения даташита в RMS:
  `I_RMS = I_peak / √2 ≈ 0.707 · I_peak`. У `tmc_calc.py` появился
  `--current-basis peak` (по умолчанию `rms`), `bringup_tmc.py` и `tmc_tune.py`
  передают его для рельсов. Пересчитаны LDO 2.8 A peak → 1.9799 A RMS, 17HM19
  1.68 A peak → 1.1879 A RMS, Z 17HS4401S 1.7 A peak → 1.2021 A RMS
  (`HSTRT/HEND 0/0`); экструдеры остаются на 0.55/0.60 A RMS. На LDO при
  1.98 A расчёт даёт `HystStart > 20` — предупреждение, а не ошибка.
  **EN:** X/Y and Z currents are derived from the datasheet peak into RMS:
  `I_RMS = I_peak / √2 ≈ 0.707 · I_peak`. `tmc_calc.py` gained
  `--current-basis peak` (default `rms`), and `bringup_tmc.py`/`tmc_tune.py`
  pass it for the rails. Recalculated: LDO 2.8 A peak → 1.9799 A RMS, 17HM19
  1.68 A peak → 1.1879 A RMS, Z 17HS4401S 1.7 A peak → 1.2021 A RMS
  (`HSTRT/HEND 0/0`); the extruders stay at 0.55/0.60 A RMS. On the LDO at
  1.98 A the calculation reports `HystStart > 20`, which is a warning, not an
  error.

- **RU:** Весь парк переведён в SpreadCycle с явным `stealthchop_threshold: 0`
  (X/Y и экструдеры и раньше работали в SpreadCycle по умолчанию Klipper —
  ключа просто не было). Z-модули пересчитаны на номинал 1.7 A
  (`driver_HSTRT/HEND = 0/2`); `TBL=0` задан явно у всех моторов, включая
  17HM19-модули, где ключ был закомментирован. Экструдеры — на фактические
  0.55/0.60 A (`HSTRT/HEND` 7/4 и 7/5), `boards/fly-sb2040.cfg` пересчитан на
  0.672 A. Токи экструдеров не повышаются. Из `bringup.sh` удалена
  захардкоженная строка отчёта про Z 1.7 A; отчёт `bringup_tmc.py` печатает
  TBL/TOFF/HSTRT/HEND и источник тока. `tmc_tune.py` применяет TBL/TOFF из
  профиля, чтобы живой тест не расходился с модулем.
  **EN:** The whole fleet now runs SpreadCycle with an explicit
  `stealthchop_threshold: 0` (X/Y and the extruders already ran SpreadCycle
  because Klipper defaults to it when the key is absent). The Z modules are
  recalculated at the 1.7 A rating (`driver_HSTRT/HEND = 0/2`); `TBL=0` is now
  explicit on every motor, including the 17HM19 modules where the key was
  commented out. The extruders stay at their actual 0.55/0.60 A (`HSTRT/HEND`
  7/4 and 7/5), and `boards/fly-sb2040.cfg` at 0.672 A. Extruder currents are
  not raised. The hardcoded Z 1.7 A report line is removed from `bringup.sh`;
  the `bringup_tmc.py` report prints TBL/TOFF/HSTRT/HEND and the current source.
  `tmc_tune.py` applies TBL/TOFF from the profile so the live test matches the
  module.

- **RU:** `xy_driver` разделён на драйвер+мотор; `extruder_motor` заменён на
  `e_motor`. Z-модуль больше не включается механикой (`trident.cfg`/`v24.cfg`),
  а приходит из манифеста `profile.cfg` по ключам профиля; merged-конфиг обоих
  профилей не изменился. Заголовок `profile.cfg` показывает resolved-карту
  (`X/Y: … | Z×N: … | E: …`). `tmc_calc.py --wire-profile` пишет
  `xy_driver`+`xy_motor` двумя строками и проверяет пару до записи;
  `bringup_tmc.py`/`tmc_tune.py` берут моторы из `xy_motor`/`z_motor`/`e_motor`
  (парсинг имени модуля и `motor_by_module` для этого не нужны). Профили
  `voron-t` и `v24-350` мигрированы на схему v2 и перерендерены. Удалён
  неиспользуемый `mechanics/tmc/xy-tmc2209-17HM19-1684.cfg`: пара без
  модулей в обеих семьях плат больше не является допустимой.
  **EN:** `xy_driver` is split into driver+motor; `extruder_motor` became
  `e_motor`. The Z module is no longer included by the mechanic
  (`trident.cfg`/`v24.cfg`) but comes from the `profile.cfg` manifest through
  the profile keys; the merged config of both profiles is unchanged. The
  `profile.cfg` header shows the resolved map (`X/Y: … | Z×N: … | E: …`).
  `tmc_calc.py --wire-profile` writes `xy_driver`+`xy_motor` as two lines and
  validates the pair before writing; `bringup_tmc.py`/`tmc_tune.py` read the
  motors from `xy_motor`/`z_motor`/`e_motor` (module-name parsing and
  `motor_by_module` are no longer needed for that). The `voron-t` and
  `v24-350` profiles are migrated to schema v2 and re-rendered. The unused
  `mechanics/tmc/xy-tmc2209-17HM19-1684.cfg` is removed: a pair without
  modules in both board families is no longer valid.

- **RU:** `[quad_gantry_level]` модели v24: `retry_tolerance` 0.0075 → 0.015 и
  `retries` 5 → 3. Эти значения принадлежат точному scan-проходу обёртки
  `QUAD_GANTRY_LEVEL`: точный scan на стенде сходится до 0.004 мм, поэтому
  допуск 0.015 мм достижим, а прежние 7.5 мкм на шумном descend-проходе
  не сходились за 230–450 с.
  `horizontal_move_z` (10 мм) и `max_adjust` (10) не изменены — первый
  остаётся запасом безопасности грубого прохода, второй механизмом коррекции
  просевшего портала; грубый проход задаёт свои допуски параметрами команды.
  **EN:** v24 `[quad_gantry_level]`: `retry_tolerance` 0.0075 -> 0.015 and
  `retries` 5 -> 3. These values belong to the fine scan pass of the
  `QUAD_GANTRY_LEVEL` wrapper: the bench scan converges to 0.004 mm, so a
  0.015 mm tolerance is reachable, while the former 7.5 um never converged in
  the noisy descend pass within 230-450 s.
  `horizontal_move_z` (10 mm) and `max_adjust` (10) are unchanged - the first
  stays the safety reserve of the rough pass, the second the recovery
  mechanism for a sagged gantry; the rough pass sets its own tolerances on the
  command line.

### Fixed / Исправлено

- **RU:** `std.configs/extruder/accel/lis2dw.cfg`: неверный `axes_map: x,z,-y`
  вешал вертикальную ось чипа на ось X принтера, поэтому замер `TEST_RESONANCES
  AXIS=X` писал в `psd_x` поперечную компоненту, а реальный пик X уходил в
  `psd_z`. На стенде v24-350 (sht36-v3) проверено 2026-11-23:
  `ACCELEROMETER_QUERY` на неподвижной машине с новым `axes_map: -y,z,-x`
  даёт `z=+9475 mm/s²` (весь вектор тяжести в Z), ход +X даёт отклик только в
  `x`, ход +Y — только в `y`. После исправления шум 2.23/2.16/2.14 и
  воспроизводимые пики 50 Гц (X) и 34 Гц (Y). `boards/ebb36-v1.2.cfg` с тем же
  значением не тронут: другая плата и другая посадка чипа, на железе не
  проверялась.
  **EN:** `std.configs/extruder/accel/lis2dw.cfg`: the wrong
  `axes_map: x,z,-y` attached the chip's vertical axis to the printer X axis,
  so `TEST_RESONANCES AXIS=X` wrote the transverse component into `psd_x`
  while the real X peak landed in `psd_z`. Verified on the v24-350 bench
  (sht36-v3) on 2026-11-23: `ACCELEROMETER_QUERY` on a stationary machine
  with the new `axes_map: -y,z,-x` reports `z=+9475 mm/s²` (the whole gravity
  vector in Z), a +X move responds only in `x`, and a +Y move only in `y`.
  After the fix the noise is 2.23/2.16/2.14 and the peaks are reproducible
  at 50 Hz (X) and 34 Hz (Y). `boards/ebb36-v1.2.cfg` with the same value is
  untouched: different board and chip mount, not verified on hardware.

- **RU:** `[probe] pin: !SENS_2` был объявлен в файлах всех четырёх плат Manta,
  а не только в `std.configs/probe.cfg`. Файл платы включается безусловно,
  поэтому gating eddy-фич (рендер убирал лишь `probe.cfg`) не помогал: Klipper
  падал с `Registering duplicate object 'probe'`. Пин перенесён в
  `std.configs/probe.cfg` (алиас `SENS_2` определён в `[board_pins]` каждой
  платы парка), значения `[probe]` merged-конфига не изменились, а валидатор
  теперь ловит такую пару секций. `boards/fly-sb2040.cfg` не тронут: у него
  самостоятельный `[probe]`.
  **EN:** `[probe] pin: !SENS_2` was declared in the files of all four Manta
  boards instead of only `std.configs/probe.cfg`. A board file is included
  unconditionally, so the eddy feature gating (the renderer dropped only
  `probe.cfg`) did not help: Klipper aborted with
  `Registering duplicate object 'probe'`. The pin moved into
  `std.configs/probe.cfg` (`SENS_2` is a `[board_pins]` alias of every board in
  the fleet), the merged `[probe]` values are unchanged, and the validator now
  catches that section pair. `boards/fly-sb2040.cfg` is untouched: it has its
  own self-contained `[probe]`.

- **RU:** На стенде v24-350 LDC1612 отвечает по I2C-адресу `43`, а не `42`:
  `LDC_CALIBRATE_DRIVE_CURRENT CHIP=fly_eddy_probe` по `42` возвращал
  `START_READ_NACK` и переводил Klipper в shutdown, по `43` — `reg_drive_current:
  15` (на `i2c_speed` 4 МГц и 400 кГц одинаково). Адрес задан перемычкой в
  железе, поэтому переопределён в `printers/v24-350/machine-extras.cfg`:
  `[probe_eddy_current fly_eddy_probe] i2c_address: 43`. README описывает
  проверку адреса и обе раскладки (внешний FLY-EDDY-F — `42`, встроенный чип
  SHT36 Max V3 — `43`).
  **EN:** The v24-350 bench LDC1612 answers at I2C address `43`, not `42`:
  `LDC_CALIBRATE_DRIVE_CURRENT CHIP=fly_eddy_probe` returned
  `START_READ_NACK` at `42` and shut Klipper down, while `43` reported
  `reg_drive_current: 15` (the same at `i2c_speed` 4 MHz and 400 kHz). The
  address is strapped in hardware, so it is overridden in
  `printers/v24-350/machine-extras.cfg`:
  `[probe_eddy_current fly_eddy_probe] i2c_address: 43`. README documents the
  address check and both layouts (external FLY-EDDY-F at `42`, built-in SHT36
  Max V3 chip at `43`).

## [1.4.0] - 2026-11-15

### Added / Добавлено

- **RU:** `scripts/bringup.sh` — конвейер первичной настройки машины:
  `deploy → tmc → motion → pid-e → pid-b → done`. `deploy` развёртывает
  профиль и перезапускает Klipper через Moonraker, `tmc` пересчитывает все
  драйверы на номинал мотора (`tmc_calc.py --update-module`, рейлы `vm_xy`/
  `vm_ze` и `sense_resistor` из живого merged-конфига), `motion` подбирает
  `max_velocity`/`max_accel` (`tmc_tune.py`), `pid-e`/`pid-b` калибруют
  экструдер при 250 °C и стол при 120 °C, патчат `printers/<id>/local/pid.cfg`
  и проверяют удержание 30 с. Состояние (`~/printer_data/.bringup/<id>.json`)
  позволяет продолжить прогон через `--from`, `--only` и `--skip` выбирают
  этапы, `--dry-run` печатает план без команд. Гейты S0: чистый `git status`,
  валидный `machine.conf`, свежий `profile.cfg`, зелёный `deploy --check`,
  `uuids.cfg` без `REPLACE_WITH_`, отсутствие `TODO` в `anchors.cfg` для
  `motion`, Klipper `ready`/idle и нагреватели < 45 °C. Хелперы —
  `scripts/lib/bringup_api.py` (клиент Moonraker на stdlib),
  `bringup_state.py`, `bringup_tmc.py`, `bringup_pid.py`.
  **EN:** `scripts/bringup.sh` — machine commissioning pipeline:
  `deploy → tmc → motion → pid-e → pid-b → done`. `deploy` deploys the profile
  and restarts Klipper through Moonraker, `tmc` recomputes every driver at the
  motor nominal (`tmc_calc.py --update-module`, rails `vm_xy`/`vm_ze` and
  `sense_resistor` read from the live merged config), `motion` searches
  `max_velocity`/`max_accel` (`tmc_tune.py`), `pid-e`/`pid-b` calibrate the
  extruder at 250 °C and the bed at 120 °C, patch
  `printers/<id>/local/pid.cfg` and verify a 30 s hold. The state file
  (`~/printer_data/.bringup/<id>.json`) allows resuming with `--from`;
  `--only`/`--skip` select stages and `--dry-run` prints the plan without
  sending commands. S0 gates: clean `git status`, valid `machine.conf`, fresh
  `profile.cfg`, green `deploy --check`, `uuids.cfg` without `REPLACE_WITH_`,
  no `TODO` in `anchors.cfg` for `motion`, Klipper `ready`/idle and heaters
  < 45 °C. Helpers live in `scripts/lib/bringup_api.py` (stdlib Moonraker
  client), `bringup_state.py`, `bringup_tmc.py`, `bringup_pid.py`.

- **RU:** `scripts/tmc_tune.py` — подбор `max_velocity`/`max_accel` на
  номинальном токе: `SET_TMC_CURRENT`/`SET_TMC_FIELD` из `tmc_calc.py`, лестница
  `TEST_SPEED` (×1.25 до `--max-velocity`/`--max-accel`, по умолчанию ×2 от
  конфига) и бисекция первого провала, вердикт по дельте MCU-позиций
  `GET_POSITION` (порог — один полный шаг, 0.5–1 шаг → повтор), дымовой прогон
  и `TEST_KINEMATICS`, `--apply` пишет модуль и `[printer]` в
  `machine-extras.cfg`. Все пути восстановления токов и лимитов — в `finally`;
  Z вживую не тестируется.
  **EN:** `scripts/tmc_tune.py` — `max_velocity`/`max_accel` search at the
  nominal current: `SET_TMC_CURRENT`/`SET_TMC_FIELD` from `tmc_calc.py`, a
  `TEST_SPEED` ladder (×1.25 up to `--max-velocity`/`--max-accel`, default 2×
  the configured pair) with bisection of the first failure, verdicts from the
  `GET_POSITION` MCU position delta (one full step threshold, 0.5–1 step means
  repeat), a smoke run plus `TEST_KINEMATICS`, and `--apply` writing the module
  and `[printer]` into `machine-extras.cfg`. Current and limit restoration run
  in `finally`; Z is never tested live.

- **RU:** Два рейла питания драйверов: новые обязательные ключи `machine.conf`
  `vm_xy` ∈ {48, 55} и `vm_ze` = 24. Пара `board`/`vm_xy` проверяется по
  таблице `BOARD_VM_XY_MAX` в `render_profile.py` (общая с `check_config.py`):
  48 В для M5P и M8P V1.0/V1.1, 55 В только для M8P V2.0 (HV-вход 24–60 В).
  Профили заполнены: `voron-t` 48/24, `v24-350` 55/24; `new_machine.sh`
  получил `--vm-xy`, `--extruder-motor` и пишет ключи в `machine.conf`.
  **EN:** Two driver supply rails: new mandatory `machine.conf` keys `vm_xy`
  ∈ {48, 55} and `vm_ze` = 24. The `board`/`vm_xy` pair is validated through
  the `BOARD_VM_XY_MAX` table in `render_profile.py` (shared with
  `check_config.py`): 48 V on the M5P and M8P V1.0/V1.1, 55 V only on the M8P
  V2.0 (24-60 V HV input). Profiles are filled in: `voron-t` 48/24, `v24-350`
  55/24; `new_machine.sh` gained `--vm-xy`, `--extruder-motor` and writes the
  keys into `machine.conf`.

- **RU:** `tmc_calc.py --update-module FILE [--sections a,b]` — пересчёт
  существующего модуля на месте: `run_current`, `stealthchop_threshold` и
  `driver_TBL/TOFF/HSTRT/HEND` (в SpreadCycle), с сохранением пинов,
  транспорта, `sense_resistor`, ручных `driver_*` и порядка опций; блок
  расчёта с маркерами переписывается идемпотентно, без `--force` печатается
  diff, режим чоппера берётся из секции. Работает и с `extruder/main.cfg`,
  `extra-extruder.cfg`.
  **EN:** `tmc_calc.py --update-module FILE [--sections a,b]` recomputes an
  existing module in place: `run_current`, `stealthchop_threshold` and
  `driver_TBL/TOFF/HSTRT/HEND` (SpreadCycle), preserving pins, transport,
  `sense_resistor`, hand-written `driver_*` and option order; the marked
  calculation block is rewritten idempotently, without `--force` a diff is
  printed, and the chopper mode comes from the section. It also works on
  `extruder/main.cfg` and `extra-extruder.cfg`.

- **RU:** `docs/tmc/motors.json`: запись мотора экструдера
  `MOONS-CSE14HRA1L410A-01` (NEMA14, 1.0 A, 1.9 Ω, 1.41 мГн, HGX 8T) и
  таблица `motor_by_module` (имя модуля → мотор); ключ `extruder_motor` в
  профилях. `render_profile.py` проверяет имя мотора по базе.
  **EN:** `docs/tmc/motors.json`: the extruder motor entry
  `MOONS-CSE14HRA1L410A-01` (NEMA14, 1.0 A, 1.9 Ohm, 1.41 mH, HGX 8T) and a
  `motor_by_module` table (module name → motor); the `extruder_motor` key is
  set in both profiles. `render_profile.py` validates the motor name against
  the database.

- **RU:** `std.macros/test_kinematics.cfg` (порт gist alienboyxp) включается в
  каждый профиль; `scripts/lib/bringup_api.py`, `bringup_state.py`,
  `bringup_tmc.py`, `bringup_pid.py` — stdlib-хелперы конвейера с офлайн
  самопроверками.
  **EN:** `std.macros/test_kinematics.cfg` (ported from the alienboyxp gist)
  is included by every profile; `scripts/lib/bringup_api.py`,
  `bringup_state.py`, `bringup_tmc.py`, `bringup_pid.py` are the stdlib
  pipeline helpers with offline self-tests.

- **RU:** Поддержка ревизий BTT Manta M8P V1.0 и V1.1 как значений оси
  `board`: `manta-m8p-v1.0`, `manta-m8p-v1.1`. Добавлены файлы пинов
  `boards/manta-m8p-v1.0.cfg`/`-v1.1.cfg` (STM32G0B1, 8 МГц, 8 КиБ загрузчик;
  ревизии различаются только MOTOR6..MOTOR8, CAN-трансивер есть только у v1.1
  на `PD12`/`PD13`), общий дисплейный override
  `display/mini12864-swspi.cfg` (software SPI на EXP2 у v1.x), снапшоты
  прошивок `config_m8p_v1_usb` (чистый USB) и `config_m8p_v1_can`
  (USB-CAN-мост), ветки `update_firmware.sh` (v1.0 собирается, но прошивается
  вручную через `flash_mcu.sh serial`/`dfu`, а `--auto` оставляет маркер
  `pending-main` до ручной прошивки), ось платы в
  `deploy_configs.sh --matrix` и шаблон `uuids.cfg` в `new_machine.sh`.
  Конфиги проверены офлайн (валидация и обе сборки), на железе не проверялись.
  **EN:** Support for the BTT Manta M8P V1.0 and V1.1 revisions as `board`
  values: `manta-m8p-v1.0`, `manta-m8p-v1.1`. New pin files
  `boards/manta-m8p-v1.0.cfg`/`-v1.1.cfg` (STM32G0B1, 8 MHz, 8 KiB bootloader;
  the revisions differ only at MOTOR6..MOTOR8, and only v1.1 has a CAN
  transceiver on `PD12`/`PD13`), a shared `display/mini12864-swspi.cfg`
  override for software SPI on the v1.x EXP2 header, the firmware snapshots
  `config_m8p_v1_usb` (plain USB) and `config_m8p_v1_can` (USB-CAN bridge),
  `update_firmware.sh` branches (v1.0 is built but flashed manually with
  `flash_mcu.sh serial`/`dfu`, and `--auto` leaves a `pending-main` marker
  until the manual flash), the board axis in
  `deploy_configs.sh --matrix`, and the `uuids.cfg` template in
  `new_machine.sh`. The configs were verified offline (validation and both
  builds), not on hardware.

- **RU:** `scripts/update_firmware.sh` пересобирает прошивки по `machine.conf`
  и обновляет MCU после обновления Klipper: сначала `ext-extruder` и `extruder`
  по CAN, последней — главную плату. UUID читаются из развёрнутого
  `std.config.local/uuids.cfg`; есть `--dry-run`, `--auto`, `--force` и защита
  от прошивки во время печати или обновления Moonraker.
  **EN:** `scripts/update_firmware.sh` rebuilds the firmware from
  `machine.conf` and updates the MCUs after a Klipper update: `ext-extruder`
  and `extruder` over CAN first, the main board last. UUIDs come from the
  deployed `std.config.local/uuids.cfg`; `--dry-run`, `--auto`, `--force` and
  guards for an active print or Moonraker update are included.

- **RU:** Подкоманда `flash_mcu.sh bridge` для главной платы в режиме USB-CAN
  bridge: перевод в загрузчик по CAN, загрузка через Katapult-USB или STM32
  DFU по адресу приложения без `mass-erase`, ожидание возвращения `can0`.
  Добавлен `--no-service` для оркестратора.
  **EN:** New `flash_mcu.sh bridge` command for a main board running as a
  USB-CAN bridge: bootloader request over CAN, upload through Katapult-USB or
  STM32 DFU at the application address without `mass-erase`, then wait for
  `can0` to return. `--no-service` was added for the orchestrator.

- **RU:** Раскладка термисторов M8P V2.0 для v24: `THB` — стол, `TH0` —
  Y-frame, `TH2`/`TH3` — драйверы TMC5160 (`TH2` через
  `temperature_fan drivers_fan`, `TH3` через `temperature_sensor tmc5160_1`);
  `TH1` не используется. Y-frame на v24 — NTC 10K B3950; для него добавлен
  `std.configs/sensors/ntc10k-3950.cfg` (`sensor_type: ntc10k_3950`,
  трёхточечный Steinhart-Hart по таблице, ошибка <0.02 °C). Встроенный
  `Generic 3950` — 100K и для этого датчика не подходит.
  `bed.cfg`, `sensors/y-frame.cfg` и `fans/drivers_hv_fan.cfg` заменены
  каталогами с вариантами по плате. На тестовой 2.4 стол (THB) читается
  25.8 °C, Y-frame (TH0, B3950) — 26.0 °C, драйверы (TH2/TH3) — 51.9–53.0 °C.
  **EN:** M8P V2.0 thermistor map for v24: `THB` bed, `TH0` Y-frame,
  `TH2`/`TH3` TMC5160 drivers (`TH2` through `temperature_fan drivers_fan`,
  `TH3` through `temperature_sensor tmc5160_1`); `TH1` is unused.
  `bed.cfg`, `sensors/y-frame.cfg` and `fans/drivers_hv_fan.cfg` became
  per-board directories. The v24 Y-frame is an NTC 10K B3950; a dedicated
  `std.configs/sensors/ntc10k-3950.cfg` defines `sensor_type: ntc10k_3950`
  with a three-point Steinhart-Hart fit (within 0.02 C of the table). The
  built-in `Generic 3950` is a 100K table and does not fit this sensor. On the
  test 2.4 the bed (THB) reads 25.8 C, Y-frame (TH0, B3950) 26.0 C, and the
  drivers (TH2/TH3) 51.9-53.0 C.

- **RU:** Раскладка вентиляторов v24/M8P: `FAN0` — питание стола
  (`heater_bed.heater_pin`), `FAN1` — `filter_fan`, `FAN2` — `psu_fan`,
  `FAN3` — `board_fan` (`controller_fan`, 30%), `FAN4` — `exhaust_fan`;
  `fans/` разделён на `manta-m5p/` и `manta-m8p/`. На тестовой 2.4
  подтверждены пины FAN0–FAN4, Klipper выходит в `ready`.
  **EN:** v24/M8P fan map: `FAN0` bed power (`heater_bed.heater_pin`), `FAN1`
  `filter_fan`, `FAN2` `psu_fan`, `FAN3` `board_fan` (`controller_fan`),
  `FAN4` `exhaust_fan`; `fans/` is split into `manta-m5p/` and `manta-m8p/`.
  On the test 2.4 FAN0-FAN4 pins were verified and Klipper reaches `ready`.

- **RU:** Конфигурации TMC5160 X/Y разделены по плате: M8P V2.0 использует
  общий software SPI `PG6/PG7/PG8` с отдельным CS на драйвер, M5P — `spi2`.
  Аппаратный `spi1` на M8P V2.0 конфликтует с `TH3` (PA7), поэтому с
  термистором драйвера на TH3 он невозможен. На тестовой 2.4 Klipper
  выходит в `ready` с software SPI.
  **EN:** TMC5160 X/Y configs are now board specific: the M8P V2.0 uses the
  shared software SPI bus `PG6/PG7/PG8` with a per-driver CS, while the M5P
  uses `spi2`. Hardware `spi1` on the M8P V2.0 conflicts with `TH3` (PA7), so
  it cannot be combined with the driver thermistor on TH3. The test 2.4
  reaches `ready` with software SPI.

- **RU:** Ось `xy_driver`: только 150×150 использует TMC5160 +
  17HM19-1684 (0.9°), все остальные размеры — TMC5160 +
  LDO-42STH48-2804AC (1.8°, 55 Н·см, 2.8 А/фаза, `run_current: 1.697`).
  Выбор по умолчанию следует за `size`; `--matrix` проверяет обе связки.
  **EN:** New `xy_driver` axis: only 150x150 uses TMC5160 + 17HM19-1684
  (0.9 degree); every other size uses TMC5160 + LDO-42STH48-2804AC
  (1.8 degree, 55 Ncm, 2.8 A/phase, `run_current: 1.697`). The default follows
  `size`, and `--matrix` covers both combinations.

- **RU:** Тестовый профиль `printers/v24-350`: Voron 2.4 350×350, Manta M8P
  V2.0 (STM32H723), SHT36 v3, SHT42 и HGX.8T; UUID взяты из CAN-шины целевой
  машины, локальные PID/input shaper/extruder сохранены; X/Y переведены на
  TMC5160 + LDO-42STH48-2804AC (1.8°), профиль развёрнут на 192.168.52.30.
  **EN:** Test profile `printers/v24-350`: Voron 2.4 350×350, Manta M8P V2.0
  (STM32H723), SHT36 v3, SHT42 and HGX.8T; UUIDs come from the target CAN bus,
  the local PID/input shaper/extruder files are preserved, and X/Y now use
  TMC5160 + LDO-42STH48-2804AC (1.8 degree); deployed to 192.168.52.30.

- **RU:** `scripts/install_update_hook.sh` ставит systemd path- и timer-юниты:
  обновление Klipper запускает пересборку и прошивку, неудачный или
  отложенный запуск повторяется каждые 10 минут; установка помечает текущий
  commit как уже прошитый.
  **EN:** `scripts/install_update_hook.sh` installs systemd path and timer
  units: a Klipper update triggers the rebuild and flash, a failed or deferred
  run is retried every 10 minutes, and installation stamps the current commit
  as already flashed.

- **RU:** Расчёт параметров TMC для Klipper: `docs/tmc/` (вендорские
  калькуляторы `TMC2209_Calculations.xlsx`/`TMC5160_Calculations.xlsx`,
  `CALCS.md` с картой «лист/ячейка → формула», `SOURCES.md` с URL и sha256,
  `motors.json` с даташитными параметрами моторов парка) и новый
  `scripts/tmc_calc.py`. Скрипт считает `run_current` и SpreadCycle-параметры
  (`TOFF`/`TBL`/`HSTRT`/`HEND`, `HystStart_MIN`, предел частоты чоппера), умеет
  StealthChop с автотюнингом, проверяет мотор по пределу IC и диапазону
  питания, печатает готовый stanza Klipper, пишет модуль в
  `std.configs/mechanics/tmc/` (`--write`) и переводит на него ось `xy_driver`
  (`--wire-profile`). Ключи `driver_*` ограничены белым списком, сверенным с
  установленным Klipper; регистры тока Klipper считает сам, поэтому в конфиг
  они не попадают. `--selftest` сверяет формулы с сохранёнными xlsx (±1 LSB).
  `docs/` в деплой не попадает — проверено `deploy_configs.sh --check`.
  **EN:** TMC settings for Klipper: a new `docs/tmc/` tree (vendor
  `TMC2209_Calculations.xlsx`/`TMC5160_Calculations.xlsx` calculators, a
  `CALCS.md` "sheet/cell → formula" map, `SOURCES.md` with URLs and sha256, and
  `motors.json` with datasheet motor data) plus `scripts/tmc_calc.py`. The script
  picks `run_current` and the SpreadCycle values (`TOFF`/`TBL`/`HSTRT`/`HEND`,
  `HystStart_MIN`, chopper frequency limit), supports StealthChop autotuning,
  validates the motor against the IC current and supply limits, prints a ready
  Klipper stanza, writes a module into `std.configs/mechanics/tmc/` (`--write`)
  and switches the `xy_driver` axis to it (`--wire-profile`). `driver_*` keys are
  limited to a whitelist checked against the installed Klipper; current registers
  are derived by Klipper itself, so they never enter the config. `--selftest`
  compares the formulas with the saved xlsx (±1 LSB). `docs/` is never deployed,
  verified with `deploy_configs.sh --check`.

- **RU:** Конвенция доступа к хостам парка: каталог `secrets/` в `.gitignore`,
  шаблон `secrets/hosts.env.example` в репозитории (переменные
  `V24_350_HOST`/`V24_350_SSH_USER`/`V24_350_SSH_PASS`), рабочий
  `secrets/hosts.env` — только локально, права `600`. Пароль никогда не
  попадает в argv: скрипты используют переменную окружения.
  **EN:** Fleet access convention: `secrets/` is gitignored, the repository
  keeps the `secrets/hosts.env.example` template (`V24_350_HOST`,
  `V24_350_SSH_USER`, `V24_350_SSH_PASS`), and the real `secrets/hosts.env`
  stays local with mode `600`. The password never enters argv; scripts read it
  from the environment.

### Changed / Изменено

- **RU:** `std.macros/test_speed.cfg` портирован с upstream (v_20250228):
  `SMALLPATTERNSIZE` читается из `params` (в оригинале голое имя, параметр не
  работал), добавлен `HEAT=1` (прогрев 150/110 °C, совместим с
  `_PROBE_TEMP_GUARD`), `M400` перед каждым `GET_POSITION`, а выравнивание
  портала выбирается по конфигу — `QUAD_GANTRY_LEVEL` на v24 и `Z_TILT_ADJUST`
  на trident (раньше на v24 вызывался `Z_TILT_ADJUST` и падал).
  **EN:** `std.macros/test_speed.cfg` was ported from upstream (v_20250228):
  `SMALLPATTERNSIZE` is read from `params` (upstream reads a bare name, so the
  parameter never worked), `HEAT=1` preheats to 150/110 °C within the
  `_PROBE_TEMP_GUARD` limit, every `GET_POSITION` is preceded by `M400`, and
  gantry levelling follows the config — `QUAD_GANTRY_LEVEL` on v24 and
  `Z_TILT_ADJUST` on trident (the previous macro called `Z_TILT_ADJUST` on v24
  and failed).

- **RU:** `new_machine.sh` валидирует пару плата/`vm_xy` через
  `render_profile.check_voltage` (без дублирования таблицы лимитов) и пишет в
  `machine.conf` `vm_xy`, `vm_ze`, `extruder_motor`; `--matrix` подставляет
  48 В для гипотетических машин. Зависимость фич `fans → host` теперь
  проверяется: `fans/host_fan.cfg` использует пин `host:gpio19`, а `[mcu host]`
  объявляет только фича `host` (раньше профиль с `features=fans` без `host`
  создавался и падал на валидации MCU).
  **EN:** `new_machine.sh` validates the board/`vm_xy` pair through
  `render_profile.check_voltage` (no duplicated limit table) and writes
  `vm_xy`, `vm_ze`, `extruder_motor` into `machine.conf`; `--matrix` uses 48 V
  for hypothetical machines. The `fans → host` feature dependency is now
  validated: `fans/host_fan.cfg` drives `host:gpio19` while `[mcu host]` is
  declared only by the `host` feature (a `features=fans` profile without `host`
  used to be created and then failed the MCU validation).

- **RU:** `render_profile.py` больше не хранит список драйверов X/Y в константе:
  допустимые значения оси `xy_driver` собираются из файлов
  `std.configs/mechanics/tmc/<плата>/xy-*.cfg`, которые есть у всех плат
  семейства. Поведение для текущего парка не изменилось (обе связки на месте,
  `--stale-check` зелёный), но модуль, созданный `tmc_calc.py`, становится
  допустимым значением оси без правки скрипта.
  **EN:** `render_profile.py` no longer keeps the X/Y driver list in a constant:
  the allowed `xy_driver` values are discovered from
  `std.configs/mechanics/tmc/<board>/xy-*.cfg` files present for every board
  family. Fleet behaviour is unchanged (both combinations are found,
  `--stale-check` is green), but a module created by `tmc_calc.py` becomes a
  valid axis value without editing the script.

- **RU:** v24: скорости парковки и выравнивания портала удвоены.
  `mechanics/v24.cfg`: `homing_speed` X/Y 25 → 50, Z 8 → 16 и
  `second_homing_speed` 3 → 6, `[quad_gantry_level] speed` 100 → 200.
  `geometry/v24-*.cfg` и `printers/v24-350/anchors.cfg`:
  `[safe_z_home] speed` 50 → 100, `z_hop_speed` 15 → 30 (подъём на 30 мм
  остаётся). `probe.speed` (3.0) не менялся — это скорость зондирования, её
  удвоение ухудшило бы точность. Trident не затронут. Проверено офлайн
  (`--check`, `check_config.py`). На стенде v24-350 (2026-11-15) прогон
  `G28` → `QUAD_GANTRY_LEVEL` → `BED_MESH_CALIBRATE` на удвоенных скоростях
  выполнен три раза без shutdown, после исправления хоста CAN (см. «Исправлено»);
  скорости оставлены удвоенными.
  **EN:** v24: homing and gantry levelling speeds are doubled.
  `mechanics/v24.cfg`: X/Y `homing_speed` 25 → 50, Z 8 → 16 and
  `second_homing_speed` 3 → 6, `[quad_gantry_level] speed` 100 → 200.
  `geometry/v24-*.cfg` and `printers/v24-350/anchors.cfg`:
  `[safe_z_home] speed` 50 → 100, `z_hop_speed` 15 → 30 (the 30 mm lift is
  unchanged). `probe.speed` (3.0) is untouched — that is the probing speed and
  doubling it would hurt accuracy. The trident is not affected. Verified
  offline (`--check`, `check_config.py`). On the v24-350 bench (2026-11-15)
  `G28` → `QUAD_GANTRY_LEVEL` → `BED_MESH_CALIBRATE` ran three times at the
  doubled speeds without a shutdown after the CAN host fix (see "Fixed"); the
  doubled speeds are kept.

- **RU:** Стенд `printers/v24-350`: инверсия направлений всех четырёх Z-моторов
  отменена — вернулся референсный рисунок `Z0=DIR_2`, `Z1=!DIR_3`, `Z2=DIR_4`,
  `Z3=!DIR_5`. При инверсии первый же подъём `[safe_z_home]` на +30 мм уводил
  портал вниз, то есть абсолютное «вверх» было перевёрнуто; инверсия вводилась
  без прогона `G28` и оказалась неверной. Флип всех четырёх моторов не меняет
  относительные знаки зеркальных углов и наклон `QUAD_GANTRY_LEVEL`. Проверено
  офлайн (`--check`, `check_config.py`); подтверждение — небольшое перемещение
  +Z, затем `G28` и `QUAD_GANTRY_LEVEL` на стенде.
  **EN:** Bench `printers/v24-350`: the inversion of all four Z motor directions
  is reverted — the reference corner pattern is back (`Z0=DIR_2`, `Z1=!DIR_3`,
  `Z2=DIR_4`, `Z3=!DIR_5`). With the inversion the very first `[safe_z_home]`
  +30 mm hop drove the gantry down, i.e. absolute up and down were swapped; the
  inversion was added without a `G28` run and turned out to be wrong. Flipping
  all four motors keeps the relative signs of the mirror-mounted corners and the
  `QUAD_GANTRY_LEVEL` tilt behaviour. Verified offline (`--check`,
  `check_config.py`); confirmation is a small +Z move, then `G28` and
  `QUAD_GANTRY_LEVEL` on the bench.

- **RU:** `std.macros/homing.cfg` снова рабочий и подключается профилем v24:
  датчик Z стоит на печатающей головке, поэтому `G28` (когда в запросе есть Z —
  голый `G28` или `G28 Z`) и `QUAD_GANTRY_LEVEL` обёрнуты температурной
  проверкой «сопло не горячее 150 °C». Если цель выше 150 °C, она понижается и
  команда ждёт `M109`; если цель уже ниже, но сопло горячее 155 °C — ждёт
  `TEMPERATURE_WAIT`. `G28 X Y`/`G28 Y` (в `PRINT_END`, `CANCEL_PRINT`)
  проверку пропускают. Удалён нерабочий `[homing_override]` с `G1 Z30` и
  ссылками на несуществующие макро `PARK` (подъём 30 мм теперь делает
  `[safe_z_home]`); обёртки переименовывают команды на `klippy:connect`, так что
  `G28.1` идёт через `[safe_z_home]`, а `QUAD_GANTRY_LEVEL_BASE` — через
  `[quad_gantry_level]`. `scripts/render_profile.py` добавляет include для
  модели v24 (после `anchors.cfg`/`machine-extras.cfg`), `printers/v24-350/profile.cfg`
  перерендерен. `BED_MESH_CALIBRATE` намеренно не обёрнут. Проверено офлайн
  (`--check`, `check_config.py`); прогон `G28`/`QUAD_GANTRY_LEVEL` — за
  оператором.
  **EN:** `std.macros/homing.cfg` works again and is included by the v24
  profile: the Z probe is mounted on the toolhead, so `G28` (when Z is part of
  the request — a bare `G28` or `G28 Z`) and `QUAD_GANTRY_LEVEL` are wrapped in
  a "nozzle not hotter than 150 °C" guard. If the target is above 150 °C it is
  lowered and the command waits with `M109`; if the target is already lower but
  the nozzle is hotter than 155 °C, it waits via `TEMPERATURE_WAIT`. `G28 X Y`
  and `G28 Y` (in `PRINT_END`, `CANCEL_PRINT`) skip the guard. The broken
  `[homing_override]` with `G1 Z30` and references to the nonexistent `PARK`
  macro is gone (the 30 mm lift now comes from `[safe_z_home]`); the wrappers
  rename commands on `klippy:connect`, so `G28.1` goes through `[safe_z_home]`
  and `QUAD_GANTRY_LEVEL_BASE` through `[quad_gantry_level]`.
  `scripts/render_profile.py` adds the include for the v24 model (after
  `anchors.cfg`/`machine-extras.cfg`) and `printers/v24-350/profile.cfg` is
  re-rendered. `BED_MESH_CALIBRATE` is deliberately not wrapped. Verified
  offline (`--check`, `check_config.py`); a `G28`/`QUAD_GANTRY_LEVEL` run is
  left to the operator.

- **RU:** v24: перед парковкой X/Y портал теперь поднимается на 30 мм вместо
  15. `[safe_z_home]` получил `z_hop: 30` в `geometry/v24-{150,200,250,300,350}.cfg`
  (значение по умолчанию для всей модели) и в `printers/v24-350/anchors.cfg`
  (перекрывает геометрию; координаты центра стола не менялись). `G28` и
  `G28 X Y` поднимают портал на 30 мм до поиска X/Y, после `G28 Z` портал
  также остаётся на 30 мм; `z_hop_speed: 15.0`. Механизм даёт `safe_z_home`
  (при неотпаркованной Z он «обнуляет» её и поднимает на `z_hop`), отдельный
  `homing_override` не нужен и с `safe_z_home` несовместим. `mechanics/trident.cfg`
  и `printers/voron-t/anchors.cfg` не менялись (`z_hop: 15`). Проверено офлайн
  (`--check`, `--matrix`, `check_config.py`); прогон `G28` — за оператором.
  **EN:** v24: the gantry now lifts 30 mm instead of 15 before homing X/Y.
  `[safe_z_home]` gains `z_hop: 30` in
  `geometry/v24-{150,200,250,300,350}.cfg` (the model-wide default) and in
  `printers/v24-350/anchors.cfg` (overrides the geometry file; the bed-centre
  coordinates are unchanged). `G28` and `G28 X Y` lift the gantry by 30 mm
  before the X/Y search, and after `G28 Z` the gantry also stays 30 mm up;
  `z_hop_speed: 15.0`. The mechanism is `safe_z_home` (with Z unhomed it zeroes
  Z and hops by `z_hop`); a separate `homing_override` is not needed and cannot
  coexist with `safe_z_home`. `mechanics/trident.cfg` and
  `printers/voron-t/anchors.cfg` are unchanged (`z_hop: 15`). Verified offline
  (`--check`, `--matrix`, `check_config.py`); the `G28` run is left to the
  operator.

- **RU:** `mechanics/v24.cfg`: `rotation_distance` осей X и Y исправлен с `32`
  на `40` — у v24 на X/Y стоят шкивы GT2 20T (20 · 2 мм = 40 мм на оборот), а
  не 16T. С `32` любое перемещение выполнялось на 25 % больше заказанного
  (100 мм по команде давали ~125 мм по факту), что ломает и парковку, и
  размеры печати. Проверено офлайн (`--check`, `check_config.py`), на стенде
  подтверждается `configfile.settings.stepper_x/y.rotation_distance = 40.0`;
  контрольное перемещение с линейкой — за оператором. `mechanics/trident.cfg`
  не менялся.
  **EN:** `mechanics/v24.cfg`: the X and Y `rotation_distance` is corrected from
  `32` to `40` — the v24 uses GT2 20T pulleys on X/Y (20 * 2 mm = 40 mm per
  revolution), not 16T. With `32` every move travelled 25% further than
  commanded (100 mm requested gave ~125 mm actual), which breaks both homing
  and print dimensions. Verified offline (`--check`, `check_config.py`) and
  confirmed on the bench by
  `configfile.settings.stepper_x/y.rotation_distance = 40.0`; the ruler check
  of a test move is left to the operator. `mechanics/trident.cfg` is unchanged.

- **RU:** Вход `[probe]` у всей семьи Manta M8P перенесён на `SENS_2`
  (M3-STOP, разъём с маркировкой «Z stop»): `pin: !SENS_2` в
  `boards/manta-m8p.cfg` (раскрывается в `PF2`) и в
  `boards/manta-m8p-v1.0.cfg`/`-v1.1.cfg` (`PF5`). Это совпадает с
  конвенцией `boards/manta-m5p.cfg` и освобождает референсные входы
  M4-STOP/PF1 (V2.0) и M4-STOP/PC0 (V1.x). Комментарии о раскладке
  драйверов и о перемычке NPN/PNP обновлены; `mechanics/v24.cfg`
  (`endstop_pin: probe:z_virtual_endstop`) не менялся. Проверено офлайн
  (`deploy_configs.sh --check`, `check_config.py --machine` и
  `--stale-check`: `profile.cfg` не перерисовывался); на стенде
  подтверждается `QUERY_PROBE`, физические прогоны `PROBE`/`G28 Z`/`QGL`
  ещё впереди.
  **EN:** The `[probe]` input of the whole Manta M8P family moved to `SENS_2`
  (M3-STOP, the connector labelled "Z stop"): `pin: !SENS_2` in
  `boards/manta-m8p.cfg` (resolves to `PF2`) and in
  `boards/manta-m8p-v1.0.cfg`/`-v1.1.cfg` (`PF5`). This matches the
  `boards/manta-m5p.cfg` convention and frees the reference M4-STOP/PF1
  (V2.0) and M4-STOP/PC0 (V1.x) inputs. The driver-map and NPN/PNP jumper
  comments were updated; `mechanics/v24.cfg`
  (`endstop_pin: probe:z_virtual_endstop`) is unchanged. Verified offline
  (`deploy_configs.sh --check`, `check_config.py --machine` and
  `--stale-check`: `profile.cfg` was not re-rendered); on the bench it is
  confirmed by `QUERY_PROBE`, while the physical `PROBE`/`G28 Z`/`QGL` runs
  are still pending.

- **RU:** Стенд `printers/v24-350`: направления всех четырёх Z-моторов
  инвертированы в `machine-extras.cfg` (`Z0=!DIR_2`, `Z1=DIR_3`, `Z2=!DIR_4`,
  `Z3=DIR_5`) — при разводке MOTOR3..MOTOR6 стенду нужна обратная полярность.
  Инвертированы сразу все четыре, поэтому относительная картина знаков
  зеркальных углов и поведение `QUAD_GANTRY_LEVEL` по наклону не меняются,
  меняется только абсолютное «вверх/вниз». В `anchors.cfg` добавлен
  `[safe_z_home]` с `home_xy_position: 175, 175` (центр стола 350×350) и
  параметрами по образцу trident-150 (`speed: 50.0`, `z_hop: 15`,
  `z_hop_speed: 15.0`): `G28 Z` и Z=0 теперь в центре стола. Проверено офлайн
  (`--check` и `check_config.py`); на железе ожидает прогона `G28 Z` и
  `QUAD_GANTRY_LEVEL`, а `z_offset` из общего `probe.cfg` унаследован от
  voron-t и требует перекалибровки на стенде.
  **EN:** Bench `printers/v24-350`: all four Z motor directions are inverted in
  `machine-extras.cfg` (`Z0=!DIR_2`, `Z1=DIR_3`, `Z2=!DIR_4`, `Z3=DIR_5`)
  because the bench needs the opposite polarity with this MOTOR3..MOTOR6
  wiring. All four are flipped together, so the relative sign pattern of the
  mirror-mounted corners and the `QUAD_GANTRY_LEVEL` tilt behaviour are
  unchanged; only the absolute up/down direction flips. `anchors.cfg` gains a
  `[safe_z_home]` block with `home_xy_position: 175, 175` (bed centre of the
  350x350 bed) and trident-150 values (`speed: 50.0`, `z_hop: 15`,
  `z_hop_speed: 15.0`), so `G28 Z` and Z=0 now happen at the bed centre.
  Verified offline (`--check` and `check_config.py`); on hardware it awaits a
  `G28 Z` and `QUAD_GANTRY_LEVEL` run, and the `z_offset` inherited from the
  shared `probe.cfg` comes from voron-t and needs recalibration on the bench.

### Fixed / Исправлено

- **RU:** Главная плата в режиме USB-CAN bridge больше не прошивается через
  `can`: `can0` предоставляет она сама, и прошивка оборвала бы интерфейс.
  Таблица в README и комментарии скриптов исправлены на `bridge`.
  **EN:** A main board running as a USB-CAN bridge is no longer flashed over
  `can`: the board itself provides `can0`, so the upload would cut the
  interface. The README table and script comments now use `bridge`.

- **RU:** `std.configs/boards/manta-m8p.cfg`: алиасы `BLT_SENS` и `PS_ON` были
  выровнены не как продолжение `aliases`, из-за чего Klipper падал с
  `Option 'blt_sens' is not valid in section 'board_pins'`. Исправлено при
  тестовом развёртывании v24-350 на M8P V2.0.
  **EN:** `std.configs/boards/manta-m8p.cfg`: the `BLT_SENS` and `PS_ON`
  aliases were not indented as part of `aliases`, so Klipper failed with
  `Option 'blt_sens' is not valid in section 'board_pins'`. Fixed during the
  v24-350 deployment on an M8P V2.0.

- **RU:** `printers/v24-350/machine-extras.cfg` переопределяет раскладку Z-слотов
  под фактическую разводку стенда: `Z0=MOTOR3`, `Z1=MOTOR4`, `Z2=MOTOR5`,
  `Z3=MOTOR6` вместо эталонных MOTOR3/5/6/7. До этого первый `STEPPER_BUZZ` или
  включение Z уводило принтер в shutdown с
  `Unable to read tmc uart 'stepper_z3' register IFCNT`, потому что на `MOTOR7`
  драйвера нет, а два оставшихся Z-драйвера обслуживали чужие моторы. Проверено
  на железе: все четыре TMC2209 отвечают по UART (`PB9`, `PB5`, `PG14`, `PG10`),
  `DUMP_TMC` проходит, Z0..Z2 жужжат без ошибок. Дефект Z3/`MOTOR6`
  (`OpenLoad_A` в покое, `s2vsb` при движении) оказался разъёмом 4-го мотора:
  после исправления подключения `DUMP_TMC` по всем четырём чистый (`GSTAT 0`,
  без `ola`/`olb`/`s2vs`), контролируемое перемещение Z на +20 и −20 мм на
  0.6 А проходит без ошибок. `G28 Z` и `QUAD_GANTRY_LEVEL` ещё не прогонялись.
  README дополнен проверенной таблицей и порядком проверки.
  **EN:** `printers/v24-350/machine-extras.cfg` overrides the Z slot layout to
  match the bench wiring: `Z0=MOTOR3`, `Z1=MOTOR4`, `Z2=MOTOR5`, `Z3=MOTOR6`
  instead of the reference MOTOR3/5/6/7. Before this, the first `STEPPER_BUZZ`
  or Z enable shut the printer down with
  `Unable to read tmc uart 'stepper_z3' register IFCNT`, because `MOTOR7` has no
  driver while two further Z drivers were driving the wrong motors. Verified on
  hardware: all four TMC2209 answer over UART (`PB9`, `PB5`, `PG14`, `PG10`),
  `DUMP_TMC` passes, and Z0..Z2 buzz without errors. The Z3/`MOTOR6` defect
  (`OpenLoad_A` at standstill, `s2vsb` while moving) was the 4th motor
  connector: after the connection was fixed `DUMP_TMC` is clean on all four
  (`GSTAT 0`, no `ola`/`olb`/`s2vs`) and a controlled Z move of +20 and −20 mm
  at 0.6 A completes without errors. `G28 Z` and `QUAD_GANTRY_LEVEL` have not
  been run yet. README now carries the verified map and test order.

- **RU:** Стенд v24-350 (192.168.52.30): найдена и устранена причина shutdown
  `MCU 'mcu' shutdown: Timer too close` при `G28`/`QUAD_GANTRY_LEVEL`. Причин
  две, они независимы:
  1. В Klipper `v0.13.0-816-gee2c6fb6` нет upstream-фикса `29d4ec2`
     («trdispatch: Fix signed comparison when extending trsync timeout»):
     в `klippy/chelper/trdispatch.c` знаковое `int64_t`-сравнение могло
     отправить MCU `trsync_set_timeout` с уже прошедшим clock. Фикс применён
     на стенде и на voron-t через `git cherry-pick --no-commit 29d4ec2`
     (в дереве файл помечен как modified, chelper пересобирается при старте
     Klipper, MCU перепрошивать не нужно). Пока правка лежит в индексе,
     репозиторий Klipper считается изменённым и Moonraker отказывает в
     обновлении (`Update aborted, repo has been modified`), поэтому перед
     обновлением правку снимают через `git restore --staged --worktree`
     (порядок — в README).
  2. Хост CAN: `/etc/network/interfaces` поднимал `txqueuelen 1024` командой
     `ifconfig`, которой в системе нет (net-tools не установлен). Из-за этого
     `ifup@can0` падал с кодом 1, а TX-очередь оставалась 10 кадров; за день
     накопилось более 1200 сообщений `Got error -1 in can write: (105)No buffer
     space available` (`bytes_retransmit=2228`, `retransmit_seq=5331`) —
     часть `trsync_set_timeout` не доходила до MCU с первого раза. Команда
     заменена на `up ip link set dev can0 txqueuelen 1024` (iproute2);
     интерфейс переподнимать не потребовалось.
  Проверка на стенде: три прогона `G28` → `QUAD_GANTRY_LEVEL` →
  `BED_MESH_CALIBRATE` на удвоенных скоростях без shutdown; счётчик
  `Timer too close` не вырос (4), новых `No buffer space available` нет
  (1244 → 1244), `bytes_retransmit`/`retransmit_seq` застыли на 2558/357.
  Отдельно зафиксировано: зонд стенда шумит (`Probe samples exceed tolerance`
  почти на каждой точке), из-за чего `QUAD_GANTRY_LEVEL` идёт 230–450 с, а
  сетка 10×10 — около 20 мин; якоря QGL остаются каталожными.
  **EN:** Bench v24-350 (192.168.52.30): the cause of
  `MCU 'mcu' shutdown: Timer too close` during `G28`/`QUAD_GANTRY_LEVEL` was
  found and fixed. There are two independent causes:
  1. Klipper `v0.13.0-816-gee2c6fb6` lacks the upstream fix `29d4ec2`
     ("trdispatch: Fix signed comparison when extending trsync timeout"): the
     signed `int64_t` comparison in `klippy/chelper/trdispatch.c` could send the
     MCU a `trsync_set_timeout` whose clock had already passed. The fix was
     applied on the bench and on voron-t with
     `git cherry-pick --no-commit 29d4ec2` (the file shows as modified, chelper
     rebuilds on the next Klipper start, no MCU reflash needed). While the
     change sits in the index the Klipper repository counts as modified and
     Moonraker refuses to update it (`Update aborted, repo has been modified`),
     so the change is dropped with `git restore --staged --worktree` before an
     update (the order is in the README).
  2. CAN host: `/etc/network/interfaces` raised `txqueuelen 1024` through
     `ifconfig`, which does not exist here (net-tools is not installed). As a
     result `ifup@can0` failed with exit code 1 and the TX queue stayed at
     10 frames; over one day this produced more than 1200
     `Got error -1 in can write: (105)No buffer space available` messages
     (`bytes_retransmit=2228`, `retransmit_seq=5331`), so some
     `trsync_set_timeout` frames did not reach the MCU on the first try. The
     line now uses `up ip link set dev can0 txqueuelen 1024` (iproute2); the
     interface did not have to be bounced.
  Verified on the bench: three runs of `G28` → `QUAD_GANTRY_LEVEL` →
  `BED_MESH_CALIBRATE` at the doubled speeds with no shutdown; the
  `Timer too close` counter did not grow (4), no new
  `No buffer space available` lines appeared (1244 → 1244), and
  `bytes_retransmit`/`retransmit_seq` stayed at 2558/357. Separately noted: the
  bench probe is noisy (`Probe samples exceed tolerance` on almost every
  point), so `QUAD_GANTRY_LEVEL` takes 230–450 s and a 10x10 mesh about
  20 minutes; the QGL anchors are still the catalog values.

## [1.3.0] - 2026-11-08

### Added / Добавлено

- **RU:** Фича `extra_extruder` стала осью парка: `belay` и `btt_sfs` требуют
  её (их датчики физически на SHT42), иначе `render_profile.py` и
  `new_machine.sh` завершаются с ERROR. Шаблон `local/uuids.cfg` в мастере
  содержит `[mcu]` и `[mcu extruder]` всегда, `[mcu ext-extruder]` — только с
  `extra_extruder`; мастер спрашивает фичи в интерактивном терминале.
  **EN:** The `extra_extruder` feature became a fleet axis: `belay` and
  `btt_sfs` require it (their sensors are physically on the SHT42), otherwise
  `render_profile.py` and `new_machine.sh` exit with an ERROR. The wizard's
  `local/uuids.cfg` template always has `[mcu]` and `[mcu extruder]`, and
  `[mcu ext-extruder]` only with `extra_extruder`; the wizard asks for features
  on an interactive terminal.

- **RU:** `check_config.py` проверяет ссылки на MCU: ERROR для pin-префикса
  `NAME:`, `mcu:` у `[board_pins]` и `sensor_mcu:` без `[mcu NAME]`; WARNING
  для объявленного, но нигде не использованного `[mcu NAME]` (осиротевшая
  плата); неявный `mcu` и `host` исключены.
  **EN:** `check_config.py` validates MCU references: ERROR for a `NAME:` pin
  prefix, `mcu:` in `[board_pins]` and `sensor_mcu:` without `[mcu NAME]`;
  WARNING for a declared but unreferenced `[mcu NAME]` (orphaned board); the
  implicit `mcu` and `host` are exempt.

- **RU:** `deploy_configs.sh --matrix` прогоняет 20 комбинаций: `full` и `lite`
  (без `extra_extruder,belay,btt_sfs`) для каждого model × size.
  **EN:** `deploy_configs.sh --matrix` runs 20 combinations: `full` and `lite`
  (without `extra_extruder,belay,btt_sfs`) for every model × size.

- **RU:** `build_mcu.sh` получил `--clean`, `--menuconfig`, `-j N`,
  `--src DIR` (Klipper или Katapult) и `--print-bin`; артефакты складываются в
  `<src>/out/<config>`.
  **EN:** `build_mcu.sh` gained `--clean`, `--menuconfig`, `-j N`, `--src DIR`
  (Klipper or Katapult) and `--print-bin`; artifacts go to `<src>/out/<config>`.

- **RU:** `flash_mcu.sh` переписан на подкоманды `can`, `query`, `serial`,
  `dfu`, `linux` с preflight Katapult/`python3-serial`, обязательным UUID
  (`-u` или интерактивный ввод), `--dry-run`, остановкой и восстановлением
  `klipper` вокруг CAN-прошивки, подтверждением `mass-erase` для DFU и
  идемпотентным `linux --setup`.
  **EN:** `flash_mcu.sh` was rewritten with `can`, `query`, `serial`, `dfu` and
  `linux` subcommands, Katapult/`python3-serial` preflight, a mandatory UUID
  (`-u` or interactive prompt), `--dry-run`, stopping and restoring `klipper`
  around CAN flashing, a `mass-erase` confirmation for DFU and an idempotent
  `linux --setup`.

- **RU:** В репозиторий добавлены снапшоты сборки `config_m8p_v2` (STM32H723,
  приложение с 0x8020000) и `config_linux` (process MCU).
  **EN:** Build snapshots `config_m8p_v2` (STM32H723, application at 0x8020000)
  and `config_linux` (process MCU) were added to the repository.

### Changed / Изменено

- **RU:** `config_m5p_v1` и `config_sht42_katapult.v1` приведены к текущим
  Kconfig: добавлены производные опции (`WANT_TRIGGER_ANALOG`,
  `NEED_SOS_FILTER`, оптимизация Katapult), удалена устаревшая
  `WANT_LOAD_CELL_PROBE`; все конфиги собираются.
  **EN:** `config_m5p_v1` and `config_sht42_katapult.v1` were refreshed to the
  current Kconfig: derived options added (`WANT_TRIGGER_ANALOG`,
  `NEED_SOS_FILTER`, Katapult optimization), the obsolete
  `WANT_LOAD_CELL_PROBE` removed; every config builds.

- **RU:** README описывает ось `extra_extruder` (с/без SHT42), зависимости
  фич, MCU-проверки валидатора и раздел «Прошивка контроллеров» с таблицей
  соответствия и предупреждением о `dfu mass-erase`.
  **EN:** README documents the `extra_extruder` axis (with/without SHT42),
  feature dependencies, validator MCU checks and a "Flashing controllers"
  section with the mapping table and a `dfu mass-erase` warning.

### Fixed / Исправлено

- **RU:** Запись sysctl в `flash_mcu.sh` использует `sudo tee` вместо
  неработающего `sudo echo "..." > /etc/sysctl.d/...` (редирект выполнялся без
  root).
  **EN:** The sysctl write in `flash_mcu.sh` uses `sudo tee` instead of the
  broken `sudo echo "..." > /etc/sysctl.d/...` (the redirect ran without root).

- **RU:** `build_mcu.sh` передаёт `OUT` с завершающим слэшем: Klipper трактует
  его как префикс, иначе объекты попадали в `out/<config>src/`.
  **EN:** `build_mcu.sh` passes `OUT` with a trailing slash: Klipper treats it
  as a prefix, otherwise objects landed in `out/<config>src/`.

## [1.2.0] - 2026-11-08

### Added / Добавлено

- **RU:** Оси парка в `printers/<id>/machine.conf`: `size`, `model`, `board`,
  `xy_step`, `toolhead`, `head`, `features`, рама и измеренные стороны
  треугольника. Каталоги `std.configs/{boards,mechanics,motors,geometry}/`
  покрывают комбинации 150–350 мм, Trident/2.4 и M5P/M8P.
  **EN:** Fleet axes in `printers/<id>/machine.conf`: `size`, `model`, `board`,
  `xy_step`, `toolhead`, `head`, `features`, frame and measured triangle sides.
  The `std.configs/{boards,mechanics,motors,geometry}/` catalogs cover the
  150–350 mm, Trident/2.4 and M5P/M8P combinations.

- **RU:** `scripts/render_profile.py` (детерминированный рендер `profile.cfg`) и
  `scripts/new_machine.sh` (мастер заведения профиля с оффлайн-валидацией).
  **EN:** `scripts/render_profile.py` (deterministic `profile.cfg` rendering) and
  `scripts/new_machine.sh` (profile creation wizard with offline validation).

- **RU:** В деплой добавлены `--render`, `--check`, `--matrix`, `--axis K=V`,
  `--prune/--no-prune`, сравнение закоммиченного `profile.cfg` со свежим рендером,
  staging-валидация и отказ при `print_stats.state ∈ {printing, paused}`.
  **EN:** Deploy gained `--render`, `--check`, `--matrix`, `--axis K=V`,
  `--prune/--no-prune`, committed-vs-rendered `profile.cfg` staleness check,
  staging validation and refusal when `print_stats.state ∈ {printing, paused}`.

- **RU:** В валидатор добавлены `--machine`, `--stale-check`, каталогные
  whitelist'ы, подавление диагностики для слоёв-override и геометрические
  инварианты: mesh/zero-reference/safe-z/points/probe_points в пределах хода,
  `z_positions` в раме, сверка сторон треугольника ±2 мм и предупреждение об
  отсутствии метки `# замер YYYY-MM-DD`.
  **EN:** The validator gained `--machine`, `--stale-check`, catalog whitelists,
  override-layer diagnostic suppression and geometry invariants: mesh,
  zero-reference, safe-z, points and probe_points within travel, `z_positions`
  inside the frame, triangle-side check with ±2 mm tolerance and a warning when
  the `# замер YYYY-MM-DD` marker is missing.

- **RU:** `std.configs/boards/manta-m8p.cfg` по эталону
  `Voron2_M8P-v2.0_config.cfg`, модуль `std.configs/system.cfg`,
  `std.configs/sensors/y-frame.cfg`, `motors/xy-step-{0.9,1.8}.cfg` и
  `mechanics/tmc/` для альтернативных драйверов.
  **EN:** `std.configs/boards/manta-m8p.cfg` based on the
  `Voron2_M8P-v2.0_config.cfg` reference, `std.configs/system.cfg`,
  `std.configs/sensors/y-frame.cfg`, `motors/xy-step-{0.9,1.8}.cfg` and
  `mechanics/tmc/` for alternative drivers.

### Changed / Изменено

- **RU:** `std.configs/gantry/` разобран на мехáнику, моторы и геометрию;
  `pinout/` переименован в `boards/`; `printer.cfg` стал seed-заглушкой,
  `profile.cfg` генерируется и коммитится, а `machine.conf`, `anchors.cfg` и
  `machine-extras.cfg` деплоятся как managed.
  **EN:** `std.configs/gantry/` split into mechanics, motors and geometry;
  `pinout/` renamed to `boards/`; `printer.cfg` became a seed stub, `profile.cfg`
  is generated and committed, and `machine.conf`, `anchors.cfg` and
  `machine-extras.cfg` are deployed as managed files.

- **RU:** При первом деплое после 1.1.0 старый managed-манифест `printer.cfg`
  заменяется seed-заглушкой с резервной копией; существующий блок `SAVE_CONFIG`
  переносится без потери значений. `collect_local.sh` дополнительно сохраняет
  autosave-блок в `printers/<id>/autosave.snapshot.cfg` (record only).
  **EN:** On the first deploy after 1.1.0 the old managed `printer.cfg` manifest
  is replaced by the seed stub with a backup; an existing `SAVE_CONFIG` block is
  carried over without losing values. `collect_local.sh` additionally records the
  autosave block in `printers/<id>/autosave.snapshot.cfg` (record only).

- **RU:** Пин пробы и отключение SD-слотов M5P перенесены в модуль платы:
  `[probe] pin` теперь board-specific, `sd_disable.cfg` подключается из
  `boards/manta-m5p.cfg`.
  **EN:** The probe pin and M5P SD-slot disable moved into the board module:
  `[probe] pin` is now board-specific and `sd_disable.cfg` is included by
  `boards/manta-m5p.cfg`.

### Fixed / Исправлено

- **RU:** `bed_mesh zero_reference_position` исправлен с `125, 235` на `75, 135`
  (= `safe_z_home.home_xy_position`): прежняя Y была вне хода 156 мм и вызывала
  `Move out of range` при `BED_MESH_CALIBRATE`.
  **EN:** `bed_mesh zero_reference_position` fixed from `125, 235` to `75, 135`
  (= `safe_z_home.home_xy_position`): the old Y was outside the 156 mm travel and
  caused `Move out of range` during `BED_MESH_CALIBRATE`.

- **RU:** `z_tilt.z_positions` заменены на измеренный треугольник
  `(-38.5, 18)`, `(75, 235.1)`, `(188.5, 18)` (база 227 мм, стороны 245 мм)
  вместо унаследованных 250/219.
  **EN:** `z_tilt.z_positions` replaced with the measured triangle
  `(-38.5, 18)`, `(75, 235.1)`, `(188.5, 18)` (227 mm base, 245 mm legs)
  instead of the inherited 250/219.

## [1.1.0] - 2026-11-07

### Added / Добавлено

- **RU:** Профильная раскладка `printers/<профиль>/`: `printer.cfg`, `macros.cfg`,
  `moonraker.conf`, seed-файлы сервисов и `local/` для UUID, PID и input shaper.
  Живой каталог теперь наполняется деплоем профиля, а git живёт только в `~/vorons_configs`.
  **EN:** Profile layout `printers/<profile>/`: `printer.cfg`, `macros.cfg`,
  `moonraker.conf`, service seed files and `local/` for UUIDs, PID and input shaper.
  The live directory is now populated by deploying a profile, and git lives only
  in `~/vorons_configs`.

- **RU:** Скрипты `scripts/check_config.py` (офлайн-проверка include и слияния секций
  с семантикой Klipper), `collect_local.sh` (перенос `std.config.local/*.cfg` в профиль),
  `build_mcu.sh` и `flash_mcu.sh` (обобщение старых однострочников сборки и прошивки).
  **EN:** Scripts `scripts/check_config.py` (offline include/merge validation with
  Klipper semantics), `collect_local.sh` (copy `std.config.local/*.cfg` into the profile),
  `build_mcu.sh` and `flash_mcu.sh` (generalize the old build/flash one-liners).

- **RU:** Новые общие модули `std.configs/sd_disable.cfg`,
  `std.configs/display/mini12864.cfg`, `std.configs/extruder/accel/lis2dw.cfg`;
  переименованы `std.configs/extruder/main.cfg`, `extruder/heads/`,
  `std.macros/test_speed.cfg` и `std.macros/filament_load_unload.cfg`.
  **EN:** New shared modules `std.configs/sd_disable.cfg`,
  `std.configs/display/mini12864.cfg`, `std.configs/extruder/accel/lis2dw.cfg`;
  renamed `std.configs/extruder/main.cfg`, `extruder/heads/`,
  `std.macros/test_speed.cfg` and `std.macros/filament_load_unload.cfg`.

### Changed / Изменено

- **RU:** `deploy_configs.sh` требует `-p/--printer`, разделяет managed- и seed-файлы,
  поддерживает `-n`, `-b`, `-d` и больше не выкладывает `std.compil.configs/`.
  **EN:** `deploy_configs.sh` now requires `-p/--printer`, distinguishes managed and
  seed files, supports `-n`, `-b`, `-d` and no longer deploys `std.compil.configs/`.

- **RU:** В `moonraker.conf` оставлена одна запись `[update_manager vorons_configs]`
  без `managed_services`, чтобы обновление не перезапускало Klipper с невыложенными
  конфигами; запись `voron_personal_configs` удалена.
  **EN:** `moonraker.conf` keeps a single `[update_manager vorons_configs]` entry
  without `managed_services`, so an update cannot restart Klipper onto undeployed
  configs; the `voron_personal_configs` entry was removed.

- **RU:** `CURENT_HOME_Z`/`CURENT_RUN_Z` переименованы в `CURRENT_*`.
  **EN:** `CURENT_HOME_Z`/`CURENT_RUN_Z` renamed to `CURRENT_*`.

- **RU:** Общие pinout-модули больше не содержат `[mcu ...]` и CAN-UUID;
  идентификаторы живут в `printers/<профиль>/local/uuids.cfg`.
  **EN:** Shared pinout modules no longer contain `[mcu ...]` sections or CAN UUIDs;
  identifiers live in `printers/<profile>/local/uuids.cfg`.

- **RU:** Исправлены пути `/home/biqu/` в `crowsnest.conf` на `/home/spectre/`.
  **EN:** Fixed `/home/biqu/` paths in `crowsnest.conf` to `/home/spectre/`.

### Removed / Удалено

- **RU:** Сторонние файлы `mainsail.cfg`, `timelapse.cfg`, `print_area_bed_mesh.cfg`,
  локальный `.moonraker.conf.bkp`, все `std.compil.configs/*.old`,
  однострочники `compil_ext_extruder.sh`/`update_ext_extruder.sh`, а также `.git`
  из живого каталога после успешного деплоя.
  **EN:** Third-party files `mainsail.cfg`, `timelapse.cfg`, `print_area_bed_mesh.cfg`,
  the local `.moonraker.conf.bkp`, all `std.compil.configs/*.old`,
  the `compil_ext_extruder.sh`/`update_ext_extruder.sh` one-liners, and `.git`
  from the live directory after a successful deploy.

### Fixed / Исправлено

- **RU:** B1: дубль `[static_digital_output disable_SD]` больше не перекрывает PC1.
  Оба пина (`PC0, PC1`) пока управляются одной секцией как безопасный вариант до
  подтверждения электрики SD-слотов.
  **EN:** B1: the duplicate `[static_digital_output disable_SD]` no longer masks PC1.
  Both pins (`PC0, PC1`) are driven from one section as the safe fallback until the
  SD-slot wiring is confirmed.

- **RU:** B2: три определения `[resonance_tester]` сведены в один модуль
  `std.configs/extruder/accel/lis2dw.cfg` вместе с `[lis2dw]`.
  **EN:** B2: the three `[resonance_tester]` definitions are consolidated into
  `std.configs/extruder/accel/lis2dw.cfg` together with `[lis2dw]`.

- **RU:** B3: битые include ветки Eddy подтверждены валидатором; include
  `sht36-v3.eddy.cfg` остаётся закомментированным, пока с машины-донора не перенесены
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg`.
  **EN:** B3: the broken Eddy includes are reproduced by the validator; the
  `sht36-v3.eddy.cfg` include stays commented until
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` are copied from the donor machine.

- **RU:** B4: сборка и прошивка MCU вынесены в переносимые скрипты с shebang и
  без захардкоженного UUID.
  **EN:** B4: MCU build and flashing moved into portable scripts with a shebang
  and without a hardcoded UUID.

- **RU:** B5: удалены устаревшие `*.old` и опечаточные конфиги сборки, которые
  раньше попадали в рантайм.
  **EN:** B5: removed stale `*.old` and typo'd build configs that used to reach
  the runtime tree.

- **RU:** B6: `crowsnest.conf` больше не ссылается на пути пользователя `biqu`.
  **EN:** B6: `crowsnest.conf` no longer points at the `biqu` user's paths.

## [1.0.0] - 2026-10-25

### Added / Добавлено

- **RU:** Первый публичный снимок конфигураций принтера Voron T: `printer.cfg`,
  `macros.cfg`, `moonraker.conf`, `mainsail.cfg`, `crowsnest.conf`,
  `KlipperScreen.conf`, `timelapse.cfg`, `sonar.conf`, `print_area_bed_mesh.cfg`
  и `telegram.conf`, а также каталоги `std.configs/`, `std.config.local/`,
  `std.macros/` и `std.compil.configs/`.
  **EN:** Initial public snapshot of the Voron T printer configuration:
  `printer.cfg`, `macros.cfg`, `moonraker.conf`, `mainsail.cfg`, `crowsnest.conf`,
  `KlipperScreen.conf`, `timelapse.cfg`, `sonar.conf`, `print_area_bed_mesh.cfg`
  and `telegram.conf`, plus the `std.configs/`, `std.config.local/`,
  `std.macros/` and `std.compil.configs/` directories.

- **RU:** Скрипт `deploy_configs.sh` для выкладки конфигов в `~/printer_data/config`
  с сохранением структуры каталогов: копирует `*.cfg`, `*.conf` и содержимое
  `std.compil.configs/`, поддерживает предпросмотр (`-n`), резервное копирование
  перезаписываемых файлов (`-b`) и прерывается при ошибке чтения источника, чтобы
  не оставить частично обновлённый набор конфигов.
  **EN:** `deploy_configs.sh` script to deploy configs into `~/printer_data/config`
  while preserving the directory structure: copies `*.cfg`, `*.conf` and the
  contents of `std.compil.configs/`, supports a dry run (`-n`), backs up overwritten
  files (`-b`) and aborts on source read errors to avoid a partially updated
  config set.

- **RU:** Двуязычный `README.md` с описанием состава репозитория и развёртывания
  конфигов.
  **EN:** Bilingual `README.md` describing the repository contents and config
  deployment.

- **RU:** `.gitignore` исключает локальные резервные копии (`*.bkp`) и архивы
  конфигов (`*.zip`).
  **EN:** `.gitignore` excludes local backups (`*.bkp`) and config archives
  (`*.zip`).
