# Changelog

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [семантическому версионированию](https://semver.org/lang/ru/).
Каждая запись приведена на русском и английском языках.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).
Every entry is provided in Russian and English.

## [Unreleased]

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
