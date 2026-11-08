# vorons_configs

Репозиторий конфигураций парка принтеров Voron. Источник истины — этот репозиторий,
а живой каталог Klipper (`~/printer_data/config`) наполняется деплоем выбранного профиля.

## Русский

### Оси парка

Профиль машины задаётся один раз в `printers/<id>/machine.conf`. Деплой читает его,
рендерит `profile.cfg` и валидирует результат; интерактивного выбора при каждом
деплое нет.

| Ключ | Значения | Назначение |
|---|---|---|
| `size` | `150`, `200`, `250`, `300`, `350` | размер стола, мм |
| `model` | `trident`, `v24` | 3Z винты + `z_tilt` / 4Z ремни + `quad_gantry_level` |
| `board` | `manta-m5p`, `manta-m8p` | основная плата (по умолчанию: trident → m5p, v24 → m8p) |
| `xy_step` | `0.9`, `1.8` | шаг двигателей X/Y |
| `toolhead` | модуль из `std.configs/boards/` | плата инструментальной головы |
| `head` | модуль из `std.configs/extruder/heads/` | экструдер/хотэнд |
| `features` | `fans`, `display`, `buttons`, `belay`, `btt_sfs`, `runout`, `extra_extruder`, `host`, `y_frame`, `eddy` | подключаемые подсистемы |
| `frame_w`, `frame_d` | мм | внешняя рама, для проверки якорей |
| `z_base_measured`, `z_leg_measured` | мм | измеренные стороны треугольника стола |

Пример `machine.conf`:

```ini
size=150
model=trident
board=manta-m5p
xy_step=0.9
toolhead=sht36-v3
head=HGX.8T
features=belay,runout,btt_sfs,extra_extruder,fans,display,buttons,host,y_frame
frame_w=310
frame_d=310
z_base_measured=227
z_leg_measured=245
```

### Фичи и extra-extruder

`features` — единственный переключатель подсистем: рендер добавляет include-файлы
только для перечисленных фич. Машины парка бывают с платой SHT42
(`extra_extruder`) и без неё.

- `extra_extruder` подключает `std.configs/extra-extruder.cfg` и требует
  `[mcu ext-extruder]` в `local/uuids.cfg`; без платы эту секцию добавлять
  нельзя — Klipper будет ждать несуществующий CAN-узел.
- `belay` и `btt_sfs` физически подключены к SHT42, поэтому требуют
  `extra_extruder`. Нарушение — ERROR в `render_profile.py` и
  `new_machine.sh`, рендер и деплой не выполняются.
- `local/uuids.cfg`, созданный мастером, содержит `[mcu]` и `[mcu extruder]`
  всегда, а `[mcu ext-extruder]` — только при `extra_extruder`.

### Проверки валидатора

`check_config.py` эмулирует чтение конфигурации Klipper и дополнительно
проверяет ссылки на MCU по исходному тексту опций:

- **ERROR** — pin-префикс `NAME:` (`^NAME:PIN`, `NAME:PIN`), `mcu:` у
  `[board_pins]` или `sensor_mcu:` у `[temperature_sensor]` ссылается на MCU,
  для которого нет `[mcu NAME]` (виртуальные `*_virtual_endstop` исключены).
- **WARNING** — `[mcu NAME]` объявлен, но на него нет ни одной ссылки: признак
  осиротевшей секции от платы, которой на машине нет. Неявный `mcu` и `host`
  предупреждение не вызывают.

### Раскладка репозитория

```text
vorons_configs/
├── printers/
│   └── voron-t/
│       ├── machine.conf        # оси и фичи машины (единственный источник выбора)
│       ├── profile.cfg         # ГЕНЕРИРУЕТСЯ из machine.conf, коммитится
│       ├── printer.cfg         # seed: [include profile.cfg] + std.config.local/*
│       ├── anchors.cfg         # managed: измеренные якоря и фактические лимиты
│       ├── machine-extras.cfg  # managed: машинные override (idle_timeout и т.п.)
│       ├── macros.cfg          # managed: макросы профиля
│       ├── moonraker.conf      # managed
│       ├── local/              # UUID, PID, input shaper, extruder → std.config.local/
│       └── KlipperScreen.conf, crowsnest.conf, sonar.conf, telegram.conf  # seed
├── std.configs/
│   ├── boards/                 # pinout плат: manta-m5p, manta-m8p, toolhead-платы
│   ├── mechanics/              # trident.cfg, v24.cfg, tmc/ (драйверы)
│   ├── motors/                 # xy-step-0.9.cfg, xy-step-1.8.cfg
│   ├── geometry/               # trident-{150..350}.cfg, v24-{150..350}.cfg
│   ├── sensors/                # y-frame.cfg
│   ├── system.cfg              # статика Klipper: respond, exclude_object, ...
│   └── fans/ display/ buttons/ extruder/ ...  # подсистемы
├── std.macros/                 # общие макросы
├── std.compil.configs/         # конфиги сборки MCU (НЕ деплоятся)
└── scripts/                    # deploy/render/check/collect/build/flash
```

### Слои и переопределения

- В общих модулях (`std.configs/**`, `std.macros/**`) нет машинного: UUID, PID,
  токов, измеренных якорей и фактических лимитов.
- Переопределять ранее заданные секции и опции разрешено только слоям
  `anchors.cfg`, `machine-extras.cfg` и `std.config.local/`. Валидатор не считает
  их повторные определения ошибкой.
- `anchors.cfg` содержит только измеренные факты: `z_positions`, `points`,
  `safe_z_home`, `zero_reference_position`, реальные `position_max`/`max_z`.
  Каждый замер помечается строкой `# замер YYYY-MM-DD`; без неё валидатор выдаёт
  предупреждение.
- `geometry/*.cfg` — каталожные значения по размеру стола. Их можно использовать
  для гипотетической машины, пока якоря не измерены, но не выдавать за факт.

### Модель деплоя

Git-репозиторий живёт только в `~/vorons_configs`. Живой каталог
`~/printer_data/config` не является git-клоном.

- **managed** — перезаписываются при каждом деплое: `profile.cfg`, `machine.conf`,
  `anchors.cfg`, `machine-extras.cfg`, `macros.cfg`, `moonraker.conf`,
  `local/*.cfg` → `std.config.local/`, весь `std.configs/` и `std.macros/`.
- **seed** — создаются только если файла ещё нет: `printer.cfg`,
  `KlipperScreen.conf`, `crowsnest.conf`, `sonar.conf`, `telegram.conf`.
  `printer.cfg` — seed, потому что Klipper дописывает в него блок `SAVE_CONFIG`;
  при первом деплое после 1.1.0 старый манифест автоматически заменяется
  заглушкой (с резервной копией, а существующий autosave-блок переносится).
- `std.compil.configs/` в живой каталог не выкладывается: это исходники прошивок.
- `--prune` (по умолчанию) удаляет только известные устаревшие пути:
  `std.configs/{gantry,pinout,tc.ext}/`, корневой `printers/` (осколок 1.1.0),
  `*.old`, `*.bkp`.

### Рабочий цикл

```bash
# 1. Изменить оси/фичи и перерендерить манифест
cd ~/vorons_configs
$EDITOR printers/voron-t/machine.conf
./scripts/deploy_configs.sh -p voron-t --render
python3 scripts/check_config.py --stale-check
git add printers/voron-t/profile.cfg && git commit -m "Change voron-t axes" && git push

# 2. Оффлайн-проверка без записи в живой каталог
./scripts/deploy_configs.sh -p voron-t --check

# 3. Матрица 20 комбинаций: 10 model × size × (full | lite без SHT42)
./scripts/deploy_configs.sh -p voron-t --matrix
./scripts/deploy_configs.sh -p voron-t --check --axis model=v24 --axis size=350

# 4. Деплой на принтере
./scripts/deploy_configs.sh -p voron-t -b
sudo systemctl restart klipper moonraker

# 5. Забрать локальный тюнинг и autosave-снимок
./scripts/collect_local.sh -p voron-t
git add printers/voron-t/local printers/voron-t/autosave.snapshot.cfg
git commit -m "Tune voron-t" && git push
```

`collect_local.sh` записывает блок `SAVE_CONFIG` из живого `printer.cfg` в
`printers/<id>/autosave.snapshot.cfg` только для истории. Перенос этих значений в
`local/` — ручной шаг: они не должны дублировать опции, уже заданные include-файлами.

### Новая машина

```bash
./scripts/new_machine.sh -p v24-250 --size 250 --model v24 \
  --features fans,display,buttons,host,y_frame
```

Мастер создаёт `machine.conf`, seed-заглушку `printer.cfg`, `anchors.cfg` с TODO,
`machine-extras.cfg`, `macros.cfg`, `moonraker.conf`, `local/`, рендерит
`profile.cfg` и валидирует профиль. В интерактивном терминале он спрашивает
список фич (или принимает `--features`); `belay`/`btt_sfs` без
`extra_extruder` отклоняются. Дальше нужно заполнить `local/uuids.cfg` и
измеренные якоря.

### Скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/deploy_configs.sh -p <профиль>` | деплой; `--render`, `--check`, `--matrix` (full/lite), `--axis K=V`, `-n`, `-b`, `-d`, `--no-prune` |
| `scripts/render_profile.py --machine-dir <профиль> [--write]` | рендер `profile.cfg` из `machine.conf` |
| `scripts/check_config.py` | офлайн-парсер: `--config-dir`, `--merged`, `--machine`, `--stale-check` |
| `scripts/collect_local.sh -p <профиль>` | `std.config.local/*.cfg` → профиль + autosave-снимок |
| `scripts/new_machine.sh` | мастер заведения профиля (фичи, UUID-шаблон) |
| `scripts/build_mcu.sh -c <config> [--src DIR] [-o out] [--clean] [-j N] [--print-bin]` | сборка `klipper.bin`, `katapult.bin` или `klipper.elf` |
| `scripts/flash_mcu.sh [can\|query\|serial\|dfu\|linux] ...` | прошивка контроллера |

### Прошивка контроллеров

Сборка и прошивка разделены: `build_mcu.sh` собирает бинарник из снапшота
Kconfig в `std.compil.configs/`, `flash_mcu.sh` доставляет его на плату и сам
останавливает/восстанавливает Klipper.

Перед первой прошивкой:

```bash
git clone https://github.com/Arksine/katapult ~/katapult
sudo apt install python3-serial          # нужен flashtool.py
```

UUID читается из `local/uuids.cfg` или `flashtool.py -i can0 -q`, но вводится
при каждом запуске: аргументом `-u <12 hex>` или интерактивным запросом. В
скриптах UUID не хардкодится. `--dry-run` печатает команды и ничего не меняет.

| Секция Klipper | Конфиг | Метод | Примечание |
|---|---|---|---|
| `mcu` (trident) | `config_m5p_v1` | `can` | M5P, Katapult |
| `mcu` (v24) | `config_m8p_v2` | `can` | M8P, первая прошивка — `dfu` (Katapult) |
| `extruder` | `config_sht36_v3` | `can` | toolhead |
| `ext-extruder` | `config_sht42_v1` | `can` | загрузчик `config_sht42_katapult.v1` → `dfu` |
| `host` | `config_linux` | `linux` | process MCU, `make flash` |

```bash
# Сборка (артефакты в ~/klipper/out/<config>)
scripts/build_mcu.sh -c std.compil.configs/config_sht36_v3 --clean -j4 --print-bin
scripts/build_mcu.sh -c std.compil.configs/config_sht42_katapult.v1 --src ~/katapult
scripts/build_mcu.sh -c std.compil.configs/config_linux --print-bin   # klipper.elf

# Прошивка
scripts/flash_mcu.sh query
scripts/flash_mcu.sh can -u <uuid> -f ~/klipper/out/config_sht36_v3/klipper.bin
scripts/flash_mcu.sh serial -f ~/klipper/out/config_sht36_v3/klipper.bin
scripts/flash_mcu.sh dfu -f ~/katapult/out/config_sht42_katapult.v1/katapult.bin
scripts/flash_mcu.sh linux --setup      # разовые системные шаги
scripts/flash_mcu.sh linux             # make flash
```

- `can` останавливает `klipper`, если сервис активен, и восстанавливает его
  прежнее состояние после прошивки; `query` сервис не трогает.
- `dfu` делает `mass-erase` и стирает загрузчик: только первичная установка
  Katapult на чистую плату. Скрипт требует ввести `yes`; повторные обновления
  приложения идут через `can`.
- `linux --setup` идемпотентно ставит `klipper-mcu.service`, пишет
  `10-disable-rt-group-limit.conf` через `sudo tee` (редирект `sudo echo >` не
  работает), применяет sysctl и добавляет пользователя в группу `tty`. Без
  `--setup` выполняются только сборка и `make flash`.
- `python3-serial` и `~/katapult` проверяются до прошивки; при отсутствии
  скрипт печатает команды установки и завершается.

### Секреты

- Не коммитить реальный `bot_token`/`chat_id` в `telegram.conf`: в репозитории заглушка.
- Репозиторий приватный; `local/` (UUID, PID, input shaper) коммитится осознанно.
- `KlipperScreen.conf` содержит автогенерируемый блок `#~#`, поэтому он seed.

### Известные ограничения

- `boards/manta-m8p.cfg` собран по эталону `Voron2_M8P-v2.0_config.cfg`, но на
  железе не проверялся: только оффлайн-валидация до сборки 2.4.
- `anchors.cfg` для voron-t содержит унаследованные `max_z 105` и лимиты `153/156`;
  они помечены TODO до замера по физическим упорам. Правая сторона треугольника
  принята равной 245 мм по измерению левой.
- Маржа `bed_mesh` для размеров кроме 150 — каталожное значение `0.3·S` до
  замеров на конкретных машинах.
- Ветка Eddy (`std.configs/sht36-v3.eddy.cfg`) выключена; макросы
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` ещё не перенесены с машины-донора.
- Прошивка проверена офлайн (`--dry-run` и реальные сборки): CAN/serial/DFU
  требуют `~/katapult` и `python3-serial` и запускаются вручную из консоли.

## English

Repository of configuration files for my Voron printer fleet. The repository is the
source of truth; the live Klipper directory (`~/printer_data/config`) is populated by
deploying one printer profile.

### Fleet axes

A machine profile is defined once in `printers/<id>/machine.conf`. Deploy reads it,
renders `profile.cfg` and validates the result; there is no interactive choice on
every deploy.

| Key | Values | Purpose |
|---|---|---|
| `size` | `150`, `200`, `250`, `300`, `350` | bed size, mm |
| `model` | `trident`, `v24` | 3Z leadscrews + `z_tilt` / 4Z belts + `quad_gantry_level` |
| `board` | `manta-m5p`, `manta-m8p` | main board (default: trident → m5p, v24 → m8p) |
| `xy_step` | `0.9`, `1.8` | X/Y motor step angle |
| `toolhead` | module under `std.configs/boards/` | toolhead board |
| `head` | module under `std.configs/extruder/heads/` | extruder/hotend |
| `features` | `fans`, `display`, `buttons`, `belay`, `btt_sfs`, `runout`, `extra_extruder`, `host`, `y_frame`, `eddy` | optional subsystems |
| `frame_w`, `frame_d` | mm | outer frame, used for anchor sanity checks |
| `z_base_measured`, `z_leg_measured` | mm | measured bed triangle sides |

Example `machine.conf`:

```ini
size=150
model=trident
board=manta-m5p
xy_step=0.9
toolhead=sht36-v3
head=HGX.8T
features=belay,runout,btt_sfs,extra_extruder,fans,display,buttons,host,y_frame
frame_w=310
frame_d=310
z_base_measured=227
z_leg_measured=245
```

### Features and the extra extruder

`features` is the only subsystem switch: the renderer emits include files only
for the listed features. Fleet machines come with the SHT42 board
(`extra_extruder`) and without it.

- `extra_extruder` includes `std.configs/extra-extruder.cfg` and requires
  `[mcu ext-extruder]` in `local/uuids.cfg`; do not add that section on a
  machine without the board, or Klipper will wait for a missing CAN node.
- `belay` and `btt_sfs` are physically wired to the SHT42, so they require
  `extra_extruder`. A violation is an ERROR in `render_profile.py` and
  `new_machine.sh`; rendering and deploy stop.
- The `local/uuids.cfg` created by the wizard always contains `[mcu]` and
  `[mcu extruder]`, and `[mcu ext-extruder]` only with `extra_extruder`.

### Validator checks

`check_config.py` emulates Klipper's config reader and additionally verifies MCU
references against the original option text:

- **ERROR** — a pin prefix `NAME:` (`^NAME:PIN`, `NAME:PIN`), `mcu:` in
  `[board_pins]` or `sensor_mcu:` in `[temperature_sensor]` that names an MCU
  without a `[mcu NAME]` section (virtual `*_virtual_endstop` pins are ignored).
- **WARNING** — `[mcu NAME]` is declared but nothing references it, which
  signals an orphaned section from a board the machine does not have. The
  implicit `mcu` and `host` never produce this warning.

### Repository layout

```text
vorons_configs/
├── printers/
│   └── voron-t/
│       ├── machine.conf        # machine axes and features (single source of choice)
│       ├── profile.cfg         # GENERATED from machine.conf, committed
│       ├── printer.cfg         # seed: [include profile.cfg] + std.config.local/*
│       ├── anchors.cfg         # managed: measured anchors and real limits
│       ├── machine-extras.cfg  # managed: machine overrides (idle_timeout, ...)
│       ├── macros.cfg          # managed: profile macros
│       ├── moonraker.conf      # managed
│       ├── local/              # UUIDs, PID, input shaper, extruder → std.config.local/
│       └── KlipperScreen.conf, crowsnest.conf, sonar.conf, telegram.conf  # seed
├── std.configs/
│   ├── boards/                 # board pinouts: manta-m5p, manta-m8p, toolhead boards
│   ├── mechanics/              # trident.cfg, v24.cfg, tmc/ (drivers)
│   ├── motors/                 # xy-step-0.9.cfg, xy-step-1.8.cfg
│   ├── geometry/               # trident-{150..350}.cfg, v24-{150..350}.cfg
│   ├── sensors/                # y-frame.cfg
│   ├── system.cfg              # static Klipper sections: respond, exclude_object, ...
│   └── fans/ display/ buttons/ extruder/ ...  # subsystems
├── std.macros/                 # shared macros
├── std.compil.configs/         # MCU build configs (NOT deployed)
└── scripts/                    # deploy/render/check/collect/build/flash
```

### Layers and overrides

- Shared modules (`std.configs/**`, `std.macros/**`) contain no machine data: no
  UUIDs, PID values, currents, measured anchors or real limits.
- Only `anchors.cfg`, `machine-extras.cfg` and `std.config.local/` may reopen
  sections. The validator does not treat their repeated definitions as errors.
- `anchors.cfg` holds measured facts only: `z_positions`, `points`, `safe_z_home`,
  `zero_reference_position`, real `position_max`/`max_z`. Every measurement is marked
  with `# замер YYYY-MM-DD`; otherwise the validator warns.
- `geometry/*.cfg` contains catalog values for a bed size. They may be used for a
  hypothetical machine before anchors are measured, but must not be presented as
  measured facts.

### Deployment model

The git repository lives only in `~/vorons_configs`. The live directory
`~/printer_data/config` is not a git clone.

- **managed** — overwritten on every deploy: `profile.cfg`, `machine.conf`,
  `anchors.cfg`, `machine-extras.cfg`, `macros.cfg`, `moonraker.conf`,
  `local/*.cfg` → `std.config.local/`, all of `std.configs/` and `std.macros/`.
- **seed** — created only when missing: `printer.cfg`, `KlipperScreen.conf`,
  `crowsnest.conf`, `sonar.conf`, `telegram.conf`. `printer.cfg` is a seed because
  Klipper appends `SAVE_CONFIG` output to it; on the first deploy after 1.1.0 the
  old manifest is replaced automatically (with a backup, and an existing autosave
  block is carried over).
- `std.compil.configs/` is never deployed: it holds firmware build configs.
- `--prune` (default) removes only known legacy paths:
  `std.configs/{gantry,pinout,tc.ext}/`, the root `printers/` leftover from 1.1.0,
  `*.old`, `*.bkp`.

### Workflow

```bash
# 1. Change axes/features and regenerate the manifest
cd ~/vorons_configs
$EDITOR printers/voron-t/machine.conf
./scripts/deploy_configs.sh -p voron-t --render
python3 scripts/check_config.py --stale-check
git add printers/voron-t/profile.cfg && git commit -m "Change voron-t axes" && git push

# 2. Offline check, nothing is written to the live tree
./scripts/deploy_configs.sh -p voron-t --check

# 3. Matrix of 20 combos: 10 model x size x (full | lite without SHT42)
./scripts/deploy_configs.sh -p voron-t --matrix
./scripts/deploy_configs.sh -p voron-t --check --axis model=v24 --axis size=350

# 4. Deploy on the printer
./scripts/deploy_configs.sh -p voron-t -b
sudo systemctl restart klipper moonraker

# 5. Collect local tuning and the autosave snapshot
./scripts/collect_local.sh -p voron-t
git add printers/voron-t/local printers/voron-t/autosave.snapshot.cfg
git commit -m "Tune voron-t" && git push
```

`collect_local.sh` records the `SAVE_CONFIG` block from the live `printer.cfg` into
`printers/<id>/autosave.snapshot.cfg` for history only. Moving those values into
`local/` is a manual step: they must not duplicate options already set by includes.

### New machine

```bash
./scripts/new_machine.sh -p v24-250 --size 250 --model v24 \
  --features fans,display,buttons,host,y_frame
```

The wizard creates `machine.conf`, a seed `printer.cfg`, a TODO `anchors.cfg`,
`machine-extras.cfg`, `macros.cfg`, `moonraker.conf`, `local/`, renders
`profile.cfg` and validates the profile. On an interactive terminal it asks for
the feature list (or accepts `--features`); `belay`/`btt_sfs` without
`extra_extruder` are rejected. Next, fill `local/uuids.cfg` and the measured
anchors.

### Scripts

| Script | Purpose |
|---|---|
| `scripts/deploy_configs.sh -p <profile>` | deploy; `--render`, `--check`, `--matrix` (full/lite), `--axis K=V`, `-n`, `-b`, `-d`, `--no-prune` |
| `scripts/render_profile.py --machine-dir <profile> [--write]` | render `profile.cfg` from `machine.conf` |
| `scripts/check_config.py` | offline parser: `--config-dir`, `--merged`, `--machine`, `--stale-check` |
| `scripts/collect_local.sh -p <profile>` | `std.config.local/*.cfg` → profile + autosave snapshot |
| `scripts/new_machine.sh` | profile creation wizard (features, UUID template) |
| `scripts/build_mcu.sh -c <config> [--src DIR] [-o out] [--clean] [-j N] [--print-bin]` | build `klipper.bin`, `katapult.bin` or `klipper.elf` |
| `scripts/flash_mcu.sh [can\|query\|serial\|dfu\|linux] ...` | flash one controller |

### Flashing controllers

Building and flashing are separate: `build_mcu.sh` builds a binary from a Kconfig
snapshot in `std.compil.configs/`, and `flash_mcu.sh` delivers it to the board,
stopping and restoring Klipper itself.

Before the first flash:

```bash
git clone https://github.com/Arksine/katapult ~/katapult
sudo apt install python3-serial          # required by flashtool.py
```

The UUID comes from `local/uuids.cfg` or `flashtool.py -i can0 -q`, but is
entered on every run: with `-u <12 hex>` or at the interactive prompt. No script
hardcodes a UUID. `--dry-run` prints the commands and changes nothing.

| Klipper section | Config | Method | Note |
|---|---|---|---|
| `mcu` (trident) | `config_m5p_v1` | `can` | M5P, Katapult |
| `mcu` (v24) | `config_m8p_v2` | `can` | M8P, first flash via `dfu` (Katapult) |
| `extruder` | `config_sht36_v3` | `can` | toolhead |
| `ext-extruder` | `config_sht42_v1` | `can` | bootloader `config_sht42_katapult.v1` → `dfu` |
| `host` | `config_linux` | `linux` | process MCU, `make flash` |

```bash
# Build (artifacts in ~/klipper/out/<config>)
scripts/build_mcu.sh -c std.compil.configs/config_sht36_v3 --clean -j4 --print-bin
scripts/build_mcu.sh -c std.compil.configs/config_sht42_katapult.v1 --src ~/katapult
scripts/build_mcu.sh -c std.compil.configs/config_linux --print-bin   # klipper.elf

# Flash
scripts/flash_mcu.sh query
scripts/flash_mcu.sh can -u <uuid> -f ~/klipper/out/config_sht36_v3/klipper.bin
scripts/flash_mcu.sh serial -f ~/klipper/out/config_sht36_v3/klipper.bin
scripts/flash_mcu.sh dfu -f ~/katapult/out/config_sht42_katapult.v1/katapult.bin
scripts/flash_mcu.sh linux --setup      # one-time host setup
scripts/flash_mcu.sh linux             # make flash
```

- `can` stops `klipper` when the service is active and restores its previous
  state after flashing; `query` leaves the service alone.
- `dfu` performs a `mass-erase`, which wipes the bootloader: use it only for the
  first Katapult install on a blank board. The script requires typing `yes`;
  later application updates go through `can`.
- `linux --setup` idempotently installs `klipper-mcu.service`, writes
  `10-disable-rt-group-limit.conf` through `sudo tee` (a `sudo echo >` redirect
  does not work), applies sysctl and adds the user to the `tty` group. Without
  `--setup` only the build and `make flash` run.
- `python3-serial` and `~/katapult` are checked before flashing; when missing,
  the script prints the install commands and exits.

### Secrets

- Never commit a real `bot_token`/`chat_id` in `telegram.conf`; the repository keeps a
  placeholder.
- The repository is private; `local/` (UUIDs, PID, input shaper) is committed deliberately.
- `KlipperScreen.conf` contains a generated `#~#` block, which is why it is a seed file.

### Known limitations

- `boards/manta-m8p.cfg` follows the `Voron2_M8P-v2.0_config.cfg` reference but has
  not been validated on hardware: offline validation only until the 2.4 is built.
- voron-t `anchors.cfg` keeps inherited `max_z 105` and `153/156` limits, marked TODO
  until the physical stops are measured. The right triangle side is assumed 245 mm
  from the measured left side.
- `bed_mesh` margin for sizes other than 150 is the catalog value `0.3·S` until each
  machine is measured.
- The Eddy branch (`std.configs/sht36-v3.eddy.cfg`) is disabled; the
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` files have not been copied from the donor
  machine yet.
- Flashing is validated offline (`--dry-run` plus real builds): CAN/serial/DFU
  need `~/katapult` and `python3-serial` and are run manually from a console.