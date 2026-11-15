# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [семантическому версионированию](https://semver.org/lang/ru/).
Каждая запись приведена на русском и английском языках.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Every entry is provided in Russian and English.

## [Unreleased]

### Added / Добавлено

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

### Changed / Изменено

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
