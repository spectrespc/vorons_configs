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
| `board` | `manta-m5p`, `manta-m8p` (V2.0), `manta-m8p-v1.0`, `manta-m8p-v1.1` | основная плата (по умолчанию: trident → m5p, v24 → m8p) |
| `xy_step` | `0.9`, `1.8` | шаг двигателей X/Y: `0.9` только для 150, иначе `1.8` |
| `xy_driver` | `tmc5160-17HM19-1684`, `tmc5160-LDO-42STH48-2804AC` | драйвер/мотор X/Y; по умолчанию следует за `size` |
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

Правило парка: только 150×150 использует TMC5160 + 17HM19-1684 (0.9°);
все остальные размеры — TMC5160 + LDO-42STH48-2804AC (1.8°, 55 Н·см,
2.8 А/фаза, `run_current: 1.697`). TMC5160 работает в SpreadCycle
(`stealthchop_threshold: 0`), SPI 1 МГц, `driver_TBL/TOFF/HSTRT/HEND/FD3/TPFD =
0/3/7/8/1/2`. `xy_driver` можно задать явно, но по умолчанию он выбирается по
`size`, поэтому `--matrix` проверяет обе связки.

TMC5160 X/Y в репозитории разделены по плате: M8P V2.0 использует общий
**software SPI** на `PG6` (MOSI), `PG7` (MISO), `PG8` (SCLK) с отдельным
CS-пином на драйвер; M5P — аппаратный `spi2`. Аппаратный `spi1` на M8P V2.0
занимает `PA7`, который в этой раскладке является `TH3` (термистор драйвера),
поэтому одновременно `spi1` и `TH3` использовать нельзя.

### Z-драйверы M8P V2.0 и проверенная раскладка слотов

Раскладка Z-слотов — свойство конкретной машины. Общий шаблон
`mechanics/tmc/4z-tmc2209-17hs4401s.cfg` задаёт эталон
(`Z0=MOTOR3`, `Z1=MOTOR5`, `Z2=MOTOR6`, `Z3=MOTOR7`), а профиль может
переопределить секции `[stepper_z*]` и `[tmc2209 stepper_z*]` в
`machine-extras.cfg` (include стоит последним, поэтому значения применяются
поверх каталога).

Проверено на тестовой Voron 2.4 350 (CB2 + Manta M8P V2.0, Klipper
`v0.13.0-816`) 2026-11-15:

- X/Y TMC5160 (software SPI `PG6`/`PG7`/`PG8`, CS на `PC13`/`PE3`): `G28 X`
  и `G28 Y` проходят, регистры читаются.
- На этом стенде Z разведены подряд: `Z0=MOTOR3`, `Z1=MOTOR4`, `Z2=MOTOR5`,
  `Z3=MOTOR6`. Все четыре TMC2209 отвечают по UART (`PB9`, `PB5`, `PG14`,
  `PG10`) и `DUMP_TMC` проходит; переопределение лежит в
  `printers/v24-350/machine-extras.cfg`. `MOTOR7` при такой разводке пустой и
  UART молчит — именно поэтому эталонная раскладка на стенде давала
  `Unable to read tmc uart 'stepper_z3' register IFCNT` и shutdown при первом
  включении Z.
- `STEPPER_BUZZ` для Z0..Z2 проходит. На Z3 (`MOTOR6`) драйвер сообщал
  `OpenLoad_A` в покое и `s2vsb` при движении — дефект разъёма 4-го мотора.
  После исправления подключения `DUMP_TMC` по всем четырём чистый (`GSTAT 0`,
  без `ola`/`olb`/`s2vs`), а контролируемое перемещение Z на +20 и −20 мм на
  токе 0.6 А проходит без ошибок.
- Направления Z в `machine-extras.cfg` — референсный угловой рисунок
  `Z0=DIR_2`, `Z1=!DIR_3`, `Z2=DIR_4`, `Z3=!DIR_5`. Инверсия всех четырёх
  моторов, сделанная 2026-11-15, отменена в тот же день: при ней подъём
  `safe_z_home` на +30 мм вёл портал вниз. Флип всех четырёх моторов не меняет
  относительные знаки зеркальных углов и наклон `QUAD_GANTRY_LEVEL`, меняется
  только абсолютное «вверх/вниз». Подтверждение — небольшое перемещение +Z,
  затем `G28 Z` и `QUAD_GANTRY_LEVEL`.
- Парковка и Z=0 — в центре стола: `[safe_z_home]` с
  `home_xy_position: 175, 175` в `anchors.cfg`. Правило v24: `G28` поднимает
  портал на **30 мм** до парковки X/Y (`z_hop: 30`), чтобы низкий или
  перекошенный портал не протащил сопло по столу; после `G28 Z` портал также
  остаётся на 30 мм. Значение задано и в `geometry/v24-*.cfg` (по умолчанию для
  всей модели), профильный `anchors.cfg` его перекрывает. `speed: 50.0`,
  `z_hop_speed: 15.0`. Якоря `quad_gantry_level` и реальные лимиты ещё не
  замерены.
- `hold_current` для Z задавать не нужно: `configfile.settings` показывает
  унаследованный максимум `2.0`, но фактический `IHOLD_IRUN` равен
  `ihold=19 irun=19`, то есть в покое моторы держат те же 0.6 А.

Перед парковкой Z и выравниванием стола сопло не должно быть горячее 150 °C
(датчик Z стоит на печатающей головке): `std.macros/homing.cfg` оборачивает
`G28` (только когда в запросе есть Z — голый `G28` или `G28 Z`) и
`QUAD_GANTRY_LEVEL`. Если цель выше 150 °C, она понижается до 150 °C и команда
ждёт `M109`; если цель уже ниже, но сопло горячее 155 °C, команда ждёт
остывания через `TEMPERATURE_WAIT`. `G28 X Y` и `G28 Y` (в `PRINT_END`,
`CANCEL_PRINT`) проверку пропускают и не тормозятся. `BED_MESH_CALIBRATE`
намеренно не обёрнут — сетка снимается на рабочей температуре. Модуль
подключается в `profile.cfg` для модели v24; обёртки переименовывают команды на
`klippy:connect`, поэтому `G28.1` по-прежнему идёт через `[safe_z_home]`
(подъём 30 мм, зонд в центре стола), а `QUAD_GANTRY_LEVEL_BASE` — через модуль
`[quad_gantry_level]`.

Ревизии M8P выбираются осью `board`: `manta-m8p` — V2.0 (STM32H723, 25 МГц,
USB-CAN-мост), `manta-m8p-v1.0` и `manta-m8p-v1.1` — STM32G0B1, 8 МГц,
8 КиБ загрузчик. Все три значения используют общие `fans/manta-m8p/`,
`bed/manta-m8p.cfg`, `mechanics/tmc/manta-m8p/` и `sensors/*/manta-m8p.cfg`;
отличия живут только в файле пинов. v1.0 и v1.1 различаются только
MOTOR6..MOTOR8. CAN-трансивер есть только у v1.1 (`PD12`/`PD13`), поэтому
v1.0 подключается к хосту по USB и не может быть USB-CAN-мостом. На v1.x
mini12864 переводится на software SPI (`display/mini12864-swspi.cfg`): на
`EXP2_6` у них `PB11` (SPI1_MOSI), а не `spi2`. Прошивки:
`config_m8p_v1_usb` (v1.0, чистый USB) и `config_m8p_v1_can` (v1.1,
USB-CAN-мост на `PD12`/`PD13`). Стол на v1.x, как и на V2.0, включается через
`FAN0` (`bed/manta-m8p.cfg`); выделенный выход `HEAT_HB` (`PB7`) остаётся
свободным, пока профиль не переопределит `[heater_bed] heater_pin`. Общий
`sensors/tmc5160/manta-m8p.cfg` читает `TH3` (`PA4`): без термистора драйвера
на этом входе Klipper уходит в shutdown при старте, поэтому датчик нужно
установить либо убрать include.

Термисторы M8P V2.0 в профиле v24: `THB` — стол, `TH0` — Y-frame
(NTC 10K B3950, `sensor_type: ntc10k_3950`; встроенный `Generic 3950` —
это 100K, для 10K-датчика не подходит),
`TH2`/`TH3` — температуры драйверов TMC5160 (`TH2` через
`temperature_fan drivers_fan`, `TH3` через `temperature_sensor tmc5160_1`).
`TH1` не используется. На M5P: `THB` — стол, `TH0` — Y-frame, `TH1` —
`drivers_fan`. Поэтому `bed/`, `sensors/y-frame/` и `drivers_hv_fan/`
выбираются по плате. Таблица 10K/B3950 задана в
`std.configs/sensors/ntc10k-3950.cfg` тремя точками Steinhart-Hart
(10/60/100 °C), ошибка относительно таблицы — менее 0.02 °C.

Вентиляторы v24/M8P: `FAN0` — питание стола (`heater_bed.heater_pin`),
`FAN1` — `filter_fan`, `FAN2` — `psu_fan`, `FAN3` — `board_fan`
(`controller_fan`, 30% при работе и в простое), `FAN4` — `exhaust_fan`.
На M5P прежняя раскладка: `FAN0` — `driver_fan`, `FAN1` — `drivers_fan`,
`filter_fan`/`exhaust_fan` — на `HEAT_HE1`/`HEAT_HE0`. Поэтому `fans/`
содержит каталоги `manta-m5p/` и `manta-m8p/`.

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
│   ├── boards/                 # pinout плат: manta-m5p, manta-m8p (V2.0), manta-m8p-v1.x, toolhead-платы
│   ├── mechanics/              # trident.cfg, v24.cfg, tmc/ (драйверы)
│   ├── motors/                 # xy-step-0.9.cfg, xy-step-1.8.cfg
│   ├── geometry/               # trident-{150..350}.cfg, v24-{150..350}.cfg
│   ├── sensors/                # y-frame/, tmc5160/ (по плате)
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

# 3. Матрица 40 комбинаций: (trident + 3 платы v24) × size × (full | lite без SHT42)
./scripts/deploy_configs.sh -p voron-t --matrix
./scripts/deploy_configs.sh -p voron-t --check --axis model=v24 --axis size=350
./scripts/deploy_configs.sh -p voron-t --check --axis board=manta-m8p-v1.1

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
| `scripts/deploy_configs.sh -p <профиль>` | деплой; `--render`, `--check`, `--matrix` (full/lite, по платам), `--axis K=V`, `-n`, `-b`, `-d`, `--no-prune` |
| `scripts/render_profile.py --machine-dir <профиль> [--write]` | рендер `profile.cfg` из `machine.conf` |
| `scripts/check_config.py` | офлайн-парсер: `--config-dir`, `--merged`, `--machine`, `--stale-check` |
| `scripts/collect_local.sh -p <профиль>` | `std.config.local/*.cfg` → профиль + autosave-снимок |
| `scripts/new_machine.sh` | мастер заведения профиля (фичи, UUID-шаблон) |
| `scripts/build_mcu.sh -c <config> [--src DIR] [-o out] [--clean] [-j N] [--print-bin]` | сборка `klipper.bin`, `katapult.bin` или `klipper.elf` |
| `scripts/flash_mcu.sh [can\|bridge\|query\|serial\|dfu\|linux] ...` | прошивка контроллера |
| `scripts/update_firmware.sh [-p профиль] [--dry-run] [--auto]` | пересборка и прошивка всех MCU после обновления Klipper |
| `scripts/install_update_hook.sh [--profile профиль] [--dry-run]` | установка systemd path/timer хука (нужен sudo) |

### Прошивка контроллеров

Сборка и прошивка разделены: `build_mcu.sh` собирает бинарник из снапшота
Kconfig в `std.compil.configs/`, `flash_mcu.sh` доставляет его на плату и сам
останавливает/восстанавливает Klipper.

Перед первой прошивкой:

```bash
git clone https://github.com/Arksine/katapult ~/katapult
sudo apt install python3-serial          # нужен flashtool.py
sudo apt install dfu-util                # нужен для DFU-ветки bridge
```

UUID читается из `local/uuids.cfg` или `flashtool.py -i can0 -q`, но вводится
при каждом запуске: аргументом `-u <12 hex>` или интерактивным запросом. В
скриптах UUID не хардкодится. `--dry-run` печатает команды и ничего не меняет.

| Секция Klipper | Конфиг | Метод | Примечание |
|---|---|---|---|
| `mcu` (M5P, trident) | `config_m5p_v1` | `bridge` | USB-CAN bridge: `can0` создаёт сама плата |
| `mcu` (M8P V2.0, v24) | `config_m8p_v2` | `bridge` | первая установка Katapult — `dfu` |
| `mcu` (M8P V1.1) | `config_m8p_v1_can` | `bridge` | USB-CAN bridge на `PD12`/`PD13`; первая установка — `dfu` |
| `mcu` (M8P V1.0) | `config_m8p_v1_usb` | `serial` | только USB, CAN-трансивера нет; `dfu` — первичная установка загрузчика |
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
scripts/flash_mcu.sh bridge -u <uuid> -f ~/klipper/out/config_m5p_v1/klipper.bin
scripts/flash_mcu.sh serial -f ~/klipper/out/config_sht36_v3/klipper.bin
scripts/flash_mcu.sh dfu -f ~/katapult/out/config_sht42_katapult.v1/katapult.bin
scripts/flash_mcu.sh linux --setup      # разовые системные шаги
scripts/flash_mcu.sh linux             # make flash
```

- `can` останавливает `klipper`, если сервис активен, и восстанавливает его
  прежнее состояние после прошивки; `query` сервис не трогает.
- `bridge` нужен для главной платы в режиме USB-CAN bridge: `can0` предоставляет
  она сама, поэтому прошить её через этот же CAN нельзя. Команда переводит плату
  в загрузчик по CAN (`-r`), затем загружает приложение через Katapult-USB или
  STM32 DFU по адресу `CONFIG_FLASH_APPLICATION_ADDRESS` (без `mass-erase`) и
  ждёт возвращения `can0`.
- `--no-service` отключает остановку/запуск Klipper в `can` и `bridge`: его
  использует `update_firmware.sh`, который управляет сервисом один раз на всю
  последовательность.
- `dfu` делает `mass-erase` и стирает загрузчик: только первичная установка
  Katapult на чистую плату. Скрипт требует ввести `yes`; повторные обновления
  приложения идут через `can`/`bridge`.
- `linux --setup` идемпотентно ставит `klipper-mcu.service`, пишет
  `10-disable-rt-group-limit.conf` через `sudo tee` (редирект `sudo echo >` не
  работает), применяет sysctl и добавляет пользователя в группу `tty`. Без
  `--setup` выполняются только сборка и `make flash`.
- `python3-serial` и `~/katapult` проверяются до прошивки; при отсутствии
  скрипт печатает команды установки и завершается.

### Обновление MCU при обновлении Klipper

`update_firmware.sh` собирает прошивки по `machine.conf` и прошивает их в
безопасном порядке: сначала `ext-extruder` и `extruder` по CAN, последней —
главную плату через `bridge`. UUID берутся из развёрнутого
`std.config.local/uuids.cfg`, в скрипте они не хардкодятся.

Исключение — `board=manta-m8p-v1.0`: у платы нет CAN-трансивера, она
доступна только по USB. Скрипт собирает `config_m8p_v1_usb`, не требует
`canbus_uuid` у `[mcu]`, пропускает CAN-узлы при отсутствии `can0` (для них
нужен внешний CAN-адаптер) и **не прошивает** главную плату: после прогона он
печатает команду `flash_mcu.sh serial -f …` (или `dfu` для первой установки
загрузчика). В режиме `--auto` скрипт пишет маркер
`~/.cache/klipper-firmware/pending-main` и повторяет напоминание о ручной
прошивке при каждом запуске, пока маркер не удалён после `flash_mcu.sh serial`.

```bash
scripts/update_firmware.sh --dry-run     # только план
scripts/update_firmware.sh               # сборка и прошивка
scripts/update_firmware.sh --auto        # режим systemd: пропуск по stamp
```

Автоматический хук ставится один раз:

```bash
sudo scripts/install_update_hook.sh --profile voron-t
```

Он создаёт `klipper-firmware-update.path` (следит за `.git/HEAD` и
`.git/refs/heads` Klipper) и `klipper-firmware-update.timer` (повтор каждые
10 минут). При обновлении Klipper сервис ждёт, пока Moonraker закончит
обновление и принтер не печатает, собирает три прошивки, останавливает
Klipper, прошивает платы, запускает Klipper и записывает commit в stamp.
Если идёт печать или обновление, запуск откладывается и повторяется таймером.
Установка хука не прошивает сразу: текущий commit помечается как уже
прошитый. Удаление: `sudo scripts/install_update_hook.sh --uninstall`.

Ограничение: загрузчик главной платы должен поддерживать USB (Katapult-USB)
или ROM DFU. Katapult, настроенный только на CAN, после `-r` заберёт `can0` с
собой, и плату придётся вывести из загрузчика вручную.

### Секреты

- Не коммитить реальный `bot_token`/`chat_id` в `telegram.conf`: в репозитории заглушка.
- Репозиторий приватный; `local/` (UUID, PID, input shaper) коммитится осознанно.
- `KlipperScreen.conf` содержит автогенерируемый блок `#~#`, поэтому он seed.

### Известные ограничения

- `boards/manta-m8p-v1.0.cfg` и `boards/manta-m8p-v1.1.cfg` собраны по эталонам
  Voron (`Voron2_M8P-v1.0/1.1_config.cfg`) и Klipper
  (`generic-bigtreetech-manta-m8p-v1.0/1.1.cfg`) и проверены офлайн (`--check`
  и сборка обеих прошивок); на железе они не проверялись. Перед вводом машины
  проверить направления DIR, перемычку NPN/PNP входа probe (`PF5`, M3-STOP /
  SENS_2) и то, что дисплей живёт на software SPI.
- v1.0 без CAN-трансивера: toolhead и extra extruder на CAN требуют внешнего
  USB-CAN-адаптера, а главная плата никогда не прошивается автоматически
  (только `flash_mcu.sh serial`/`dfu`). После обновления Klipper это ручной шаг,
  даже при установленном systemd-хуке.
- `boards/manta-m8p.cfg` собран по эталону `Voron2_M8P-v2.0_config.cfg` и
  проверен на тестовой 2.4 350: конфиг загружается, все MCU подключаются, X/Y
  и Z-драйверы отвечают (см. раздел «Z-драйверы M8P V2.0»). Раскладка Z-слотов
  у машин разная и задаётся в `machine-extras.cfg` профиля; на стенде
  v24-350 дефект разъёма 4-го Z-мотора устранён: `DUMP_TMC` по всем четырём
  чистый, перемещение Z на ±20 мм на 0.6 А проходит. Направления Z —
  референсные (инверсия от 2026-11-15 отменена: подъём на 30 мм вёл портал
  вниз), точка парковки и Z=0 — центр стола 175,175;
  `G28 Z` и `QUAD_GANTRY_LEVEL` там пока не прогонялись, якоря QGL и реальные
  лимиты не замерены. `z_offset` в общем `probe.cfg` (`-0.400`) снят на
  voron-t и на стенде требует перекалибровки до первой печати.
  Вход probe у всей семьи M8P перенесён на `SENS_2` (M3-STOP, разъём с
  маркировкой «Z stop»): `PF2` у V2.0, `PF5` у V1.x; референсные M4-STOP/PF1
  (V2.0) и PC0 (V1.x) свободны. На стенде зонд должен быть переставлен на
  M3-STOP — если проводка осталась в M4-STOP, `QUERY_PROBE` не увидит
  срабатывание, а `G28 Z` уедет в стол.
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
| `board` | `manta-m5p`, `manta-m8p` (V2.0), `manta-m8p-v1.0`, `manta-m8p-v1.1` | main board (default: trident → m5p, v24 → m8p) |
| `xy_step` | `0.9`, `1.8` | X/Y step angle: `0.9` only at 150 mm, otherwise `1.8` |
| `xy_driver` | `tmc5160-17HM19-1684`, `tmc5160-LDO-42STH48-2804AC` | X/Y driver/motor; follows `size` by default |
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

Fleet rule: only 150x150 uses TMC5160 + 17HM19-1684 (0.9 degree);
every other size uses TMC5160 + LDO-42STH48-2804AC (1.8 degree, 55 Ncm,
2.8 A/phase, `run_current: 1.697`). TMC5160 runs in SpreadCycle
(`stealthchop_threshold: 0`), SPI at 1 MHz, with
`driver_TBL/TOFF/HSTRT/HEND/FD3/TPFD = 0/3/7/8/1/2`. `xy_driver` may be set
explicitly, but by default it follows `size`, so `--matrix` covers both
combinations.

TMC5160 X/Y configs are split by board: the M8P V2.0 uses the shared
**software SPI** bus on `PG6` (MOSI), `PG7` (MISO), `PG8` (SCLK) with a separate
CS pin per driver; the M5P uses hardware `spi2`. Hardware `spi1` on the M8P V2.0
reserves `PA7`, which is `TH3` (the driver thermistor) in this layout, so `spi1`
and `TH3` cannot be used together.

### M8P V2.0 Z drivers and the verified slot layout

The Z slot layout is a property of each machine. The shared
`mechanics/tmc/4z-tmc2209-17hs4401s.cfg` module defines the reference
(`Z0=MOTOR3`, `Z1=MOTOR5`, `Z2=MOTOR6`, `Z3=MOTOR7`), and a profile may override
the `[stepper_z*]` and `[tmc2209 stepper_z*]` sections in `machine-extras.cfg`
(the include is last, so its values win over the catalog).

Verified on the test Voron 2.4 350 (CB2 + Manta M8P V2.0, Klipper
`v0.13.0-816`) on 2026-11-15:

- X/Y TMC5160 (software SPI `PG6`/`PG7`/`PG8`, CS on `PC13`/`PE3`): `G28 X`
  and `G28 Y` pass and the registers read back.
- On this harness Z is wired contiguously: `Z0=MOTOR3`, `Z1=MOTOR4`,
  `Z2=MOTOR5`, `Z3=MOTOR6`. All four TMC2209 answer over UART (`PB9`, `PB5`,
  `PG14`, `PG10`) and `DUMP_TMC` passes; the override lives in
  `printers/v24-350/machine-extras.cfg`. With this wiring `MOTOR7` is empty and
  its UART is silent, which is why the reference layout produced
  `Unable to read tmc uart 'stepper_z3' register IFCNT` and a shutdown on the
  first Z enable.
- `STEPPER_BUZZ` passes for Z0..Z2. On Z3 (`MOTOR6`) the driver used to report
  `OpenLoad_A` at standstill and `s2vsb` while moving, which turned out to be a
  bad connector on the 4th motor. After the connector was fixed `DUMP_TMC` is
  clean on all four (`GSTAT 0`, no `ola`/`olb`/`s2vs`), and a controlled Z move
  of +20 and −20 mm at 0.6 A completes without errors.
- The Z directions in `machine-extras.cfg` follow the reference corner
  pattern `Z0=DIR_2`, `Z1=!DIR_3`, `Z2=DIR_4`, `Z3=!DIR_5`. The all-four
  inversion made on 2026-11-15 was reverted the same day: with it the
  `safe_z_home` +30 mm hop drove the gantry down. Flipping all four motors
  together keeps the relative signs of the mirror-mounted corners and the
  `QUAD_GANTRY_LEVEL` tilt behaviour, and only changes the absolute up/down
  direction. Confirmation is a small +Z move, then `G28 Z` and
  `QUAD_GANTRY_LEVEL`.
- Parking and Z=0 are at the bed centre: `[safe_z_home]` with
  `home_xy_position: 175, 175` in `anchors.cfg`. The v24 rule: `G28` lifts the
  gantry by **30 mm** before homing X/Y (`z_hop: 30`), so a low or tilted
  gantry cannot drag the nozzle across the bed; after `G28 Z` the gantry also
  stays 30 mm up. The value is also set in `geometry/v24-*.cfg` as the default
  for the whole model, and the profile `anchors.cfg` overrides it.
  `speed: 50.0`, `z_hop_speed: 15.0`. The `quad_gantry_level` anchors and the
  real limits are not measured yet.
- `hold_current` is not needed for Z: `configfile.settings` shows the inherited
  maximum `2.0`, but the actual `IHOLD_IRUN` is `ihold=19 irun=19`, i.e. the
  motors hold the same 0.6 A.

The nozzle must not be hotter than 150 °C while Z is homed or the gantry is
levelled (the Z probe is mounted on the toolhead): `std.macros/homing.cfg`
wraps `G28` (only when Z is part of the request — a bare `G28` or `G28 Z`) and
`QUAD_GANTRY_LEVEL`. If the target is above 150 °C it is lowered to 150 °C and
the command waits with `M109`; if the target is already lower but the nozzle is
hotter than 155 °C, the command waits for cooldown via `TEMPERATURE_WAIT`.
`G28 X Y` and `G28 Y` (in `PRINT_END`, `CANCEL_PRINT`) skip the check and are
not delayed. `BED_MESH_CALIBRATE` is deliberately not wrapped — a mesh is taken
at print temperature. The module is included by `profile.cfg` for the v24
model; the wrappers rename the commands on `klippy:connect`, so `G28.1` still
goes through `[safe_z_home]` (30 mm lift, probe at the bed centre) and
`QUAD_GANTRY_LEVEL_BASE` through the `[quad_gantry_level]` module.

M8P revisions are selected with the `board` axis: `manta-m8p` is V2.0
(STM32H723, 25 MHz, USB-CAN bridge), while `manta-m8p-v1.0` and
`manta-m8p-v1.1` are STM32G0B1, 8 MHz, 8 KiB bootloader. All three use the
shared `fans/manta-m8p/`, `bed/manta-m8p.cfg`, `mechanics/tmc/manta-m8p/` and
`sensors/*/manta-m8p.cfg` modules; the differences live only in the pin file.
V1.0 and V1.1 differ only at MOTOR6..MOTOR8. Only V1.1 has a CAN transceiver
(`PD12`/`PD13`), so V1.0 talks to the host over USB and cannot run as a
USB-CAN bridge. On v1.x the mini12864 moves to software SPI
(`display/mini12864-swspi.cfg`) because `EXP2_6` is `PB11` (SPI1_MOSI), not
`spi2`. Firmware: `config_m8p_v1_usb` (V1.0, plain USB) and `config_m8p_v1_can`
(V1.1, USB-CAN bridge on `PD12`/`PD13`). As on V2.0, the v1.x bed is switched
through `FAN0` (`bed/manta-m8p.cfg`); the dedicated `HEAT_HB` (`PB7`) output
stays free until a profile overrides `[heater_bed] heater_pin`. The shared
`sensors/tmc5160/manta-m8p.cfg` reads `TH3` (`PA4`): without a driver
thermistor on that input Klipper shuts down at startup, so fit the sensor or
drop the include.

M8P V2.0 thermistors in the v24 profile: `THB` is the bed, `TH0` the Y-frame
(NTC 10K B3950, `sensor_type: ntc10k_3950`; the built-in `Generic 3950` is a
100K table and does not fit a 10K sensor),
and `TH2`/`TH3` are the two TMC5160 driver temperatures (`TH2` through
`temperature_fan drivers_fan`, `TH3` through `temperature_sensor tmc5160_1`).
`TH1` is unused. The M5P uses `THB` bed, `TH0` Y-frame, `TH1` `drivers_fan`;
therefore `bed/`, `sensors/y-frame/` and `drivers_hv_fan/` are selected by
board. The 10K/B3950 table lives in `std.configs/sensors/ntc10k-3950.cfg` as a
three-point Steinhart-Hart fit (10/60/100 C), within 0.02 C of the table.

v24/M8P fans: `FAN0` is the bed power output (`heater_bed.heater_pin`), `FAN1`
is `filter_fan`, `FAN2` is `psu_fan`, `FAN3` is `board_fan` (`controller_fan`,
30% while active and idle), and `FAN4` is `exhaust_fan`. The M5P keeps its old
layout: `FAN0` `driver_fan`, `FAN1` `drivers_fan`, and `filter_fan`/`exhaust_fan`
on `HEAT_HE1`/`HEAT_HE0`. That is why `fans/` has `manta-m5p/` and
`manta-m8p/` directories.

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
│   ├── boards/                 # board pinouts: manta-m5p, manta-m8p (V2.0), manta-m8p-v1.x, toolhead boards
│   ├── mechanics/              # trident.cfg, v24.cfg, tmc/ (drivers)
│   ├── motors/                 # xy-step-0.9.cfg, xy-step-1.8.cfg
│   ├── geometry/               # trident-{150..350}.cfg, v24-{150..350}.cfg
│   ├── sensors/                # y-frame/, tmc5160/ (per board)
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

# 3. Matrix of 40 combos: (trident + 3 v24 boards) x size x (full | lite without SHT42)
./scripts/deploy_configs.sh -p voron-t --matrix
./scripts/deploy_configs.sh -p voron-t --check --axis model=v24 --axis size=350
./scripts/deploy_configs.sh -p voron-t --check --axis board=manta-m8p-v1.1

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
| `scripts/deploy_configs.sh -p <profile>` | deploy; `--render`, `--check`, `--matrix` (full/lite, per board), `--axis K=V`, `-n`, `-b`, `-d`, `--no-prune` |
| `scripts/render_profile.py --machine-dir <profile> [--write]` | render `profile.cfg` from `machine.conf` |
| `scripts/check_config.py` | offline parser: `--config-dir`, `--merged`, `--machine`, `--stale-check` |
| `scripts/collect_local.sh -p <profile>` | `std.config.local/*.cfg` → profile + autosave snapshot |
| `scripts/new_machine.sh` | profile creation wizard (features, UUID template) |
| `scripts/build_mcu.sh -c <config> [--src DIR] [-o out] [--clean] [-j N] [--print-bin]` | build `klipper.bin`, `katapult.bin` or `klipper.elf` |
| `scripts/flash_mcu.sh [can\|bridge\|query\|serial\|dfu\|linux] ...` | flash one controller |
| `scripts/update_firmware.sh [-p profile] [--dry-run] [--auto]` | rebuild and flash all MCUs after a Klipper update |
| `scripts/install_update_hook.sh [--profile profile] [--dry-run]` | install the systemd path/timer hook (needs sudo) |

### Flashing controllers

Building and flashing are separate: `build_mcu.sh` builds a binary from a Kconfig
snapshot in `std.compil.configs/`, and `flash_mcu.sh` delivers it to the board,
stopping and restoring Klipper itself.

Before the first flash:

```bash
git clone https://github.com/Arksine/katapult ~/katapult
sudo apt install python3-serial          # required by flashtool.py
sudo apt install dfu-util                # required for the bridge DFU path
```

The UUID comes from `local/uuids.cfg` or `flashtool.py -i can0 -q`, but is
entered on every run: with `-u <12 hex>` or at the interactive prompt. No script
hardcodes a UUID. `--dry-run` prints the commands and changes nothing.

| Klipper section | Config | Method | Note |
|---|---|---|---|
| `mcu` (M5P, trident) | `config_m5p_v1` | `bridge` | USB-CAN bridge: the board itself provides `can0` |
| `mcu` (M8P V2.0, v24) | `config_m8p_v2` | `bridge` | first Katapult install via `dfu` |
| `mcu` (M8P V1.1) | `config_m8p_v1_can` | `bridge` | USB-CAN bridge on `PD12`/`PD13`; first install via `dfu` |
| `mcu` (M8P V1.0) | `config_m8p_v1_usb` | `serial` | USB only, no CAN transceiver; `dfu` for the first bootloader install |
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
scripts/flash_mcu.sh bridge -u <uuid> -f ~/klipper/out/config_m5p_v1/klipper.bin
scripts/flash_mcu.sh serial -f ~/klipper/out/config_sht36_v3/klipper.bin
scripts/flash_mcu.sh dfu -f ~/katapult/out/config_sht42_katapult.v1/katapult.bin
scripts/flash_mcu.sh linux --setup      # one-time host setup
scripts/flash_mcu.sh linux             # make flash
```

- `can` stops `klipper` when the service is active and restores its previous
  state after flashing; `query` leaves the service alone.
- `bridge` is for a main board running as a USB-CAN bridge: `can0` is provided
  by that board, so it cannot be flashed over the same CAN interface. The
  command resets it into the bootloader over CAN (`-r`), uploads the application
  through Katapult-USB or STM32 DFU at `CONFIG_FLASH_APPLICATION_ADDRESS`
  (without `mass-erase`) and waits for `can0` to return.
- `--no-service` suppresses the Klipper stop/start in `can` and `bridge`; it is
  used by `update_firmware.sh`, which manages the service once for the whole
  sequence.
- `dfu` performs a `mass-erase`, which wipes the bootloader: use it only for the
  first Katapult install on a blank board. The script requires typing `yes`;
  later application updates go through `can`/`bridge`.
- `linux --setup` idempotently installs `klipper-mcu.service`, writes
  `10-disable-rt-group-limit.conf` through `sudo tee` (a `sudo echo >` redirect
  does not work), applies sysctl and adds the user to the `tty` group. Without
  `--setup` only the build and `make flash` run.
- `python3-serial` and `~/katapult` are checked before flashing; when missing,
  the script prints the install commands and exits.

### Updating MCUs when Klipper updates

`update_firmware.sh` derives the builds from `machine.conf` and flashes them in
the safe order: `ext-extruder` and `extruder` over CAN first, the main board
last through `bridge`. UUIDs are read from the deployed
`std.config.local/uuids.cfg`, never hardcoded in the script.

The exception is `board=manta-m8p-v1.0`: that board has no CAN transceiver and
is reachable over USB only. The script builds `config_m8p_v1_usb`, does not
require a `canbus_uuid` for `[mcu]`, skips the CAN nodes when `can0` is absent
(they need an external CAN adapter), and does **not** flash the main board:
after the run it prints `flash_mcu.sh serial -f …` (or `dfu` for the first
bootloader install). In `--auto` mode the script writes a
`~/.cache/klipper-firmware/pending-main` marker and repeats the manual-flash
reminder on every run until the marker is removed after `flash_mcu.sh serial`.

```bash
scripts/update_firmware.sh --dry-run     # plan only
scripts/update_firmware.sh               # build and flash
scripts/update_firmware.sh --auto        # systemd mode: skip by stamp
```

Install the automatic hook once:

```bash
sudo scripts/install_update_hook.sh --profile voron-t
```

It creates `klipper-firmware-update.path` (watches Klipper `.git/HEAD` and
`.git/refs/heads`) and `klipper-firmware-update.timer` (retries every
10 minutes). After a Klipper update the service waits for Moonraker and the
printer to be idle, builds the three firmwares, stops Klipper, flashes the
boards, starts Klipper and records the commit in a stamp. A running print or
update defers the run and the timer retries it. Installing the hook does not
flash immediately: the current commit is stamped as already flashed. Remove
with `sudo scripts/install_update_hook.sh --uninstall`.

Limitation: the main board's bootloader must support USB (Katapult-USB) or ROM
DFU. A CAN-only Katapult would take `can0` down after `-r` and require manual
recovery.

### Secrets

- Never commit a real `bot_token`/`chat_id` in `telegram.conf`; the repository keeps a
  placeholder.
- The repository is private; `local/` (UUIDs, PID, input shaper) is committed deliberately.
- `KlipperScreen.conf` contains a generated `#~#` block, which is why it is a seed file.

### Known limitations

- `boards/manta-m8p-v1.0.cfg` and `boards/manta-m8p-v1.1.cfg` follow the Voron
  (`Voron2_M8P-v1.0/1.1_config.cfg`) and Klipper
  (`generic-bigtreetech-manta-m8p-v1.0/1.1.cfg`) references and were verified
  offline (`--check` plus both firmware builds); they have not been tested on
  hardware. Before commissioning, check the DIR directions, the NPN/PNP jumper
  of the probe input (`PF5`, M3-STOP / SENS_2) and that the display works on
  software SPI.
- V1.0 has no CAN transceiver: CAN toolhead and extra extruder need an external
  USB-CAN adapter, and the main board is never flashed automatically (only
  `flash_mcu.sh serial`/`dfu`). After a Klipper update this stays a manual step
  even with the systemd hook installed.
- `boards/manta-m8p.cfg` follows the `Voron2_M8P-v2.0_config.cfg` reference and
  was tested on a 2.4 350: the config loads, every MCU connects, and the X/Y and
  Z drivers answer (see "M8P V2.0 Z drivers"). Each machine has its own Z slot
  layout, set in the profile's `machine-extras.cfg`; on the v24-350 bench the
  4th Z motor connector defect is fixed (`DUMP_TMC` clean on all four, a ±20 mm
  Z move at 0.6 A passes). The Z directions are the reference ones (the
  2026-11-15 inversion was reverted: the 30 mm hop drove the gantry down); the
  parking point / Z=0 is the bed centre 175,175; `G28 Z` and
  `QUAD_GANTRY_LEVEL` have not been run there yet, and the QGL anchors and real
  limits are not measured. The `z_offset` in the shared `probe.cfg` (`-0.400`)
  comes from voron-t and needs recalibration on the bench before the first
  print. The probe input of the whole M8P family moved to `SENS_2` (M3-STOP,
  the connector labelled "Z stop"): `PF2` on V2.0, `PF5` on V1.x; the reference
  M4-STOP/PF1 (V2.0) and PC0 (V1.x) inputs stay free. On the bench the probe
  must be rewired to M3-STOP — if it is still in M4-STOP, `QUERY_PROBE` will
  not see a trigger and `G28 Z` will drive into the bed.
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
