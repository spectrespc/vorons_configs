# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [семантическому версионированию](https://semver.org/lang/ru/).
Каждая запись приведена на русском и английском языках.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Every entry is provided in Russian and English.

## [Unreleased]

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
