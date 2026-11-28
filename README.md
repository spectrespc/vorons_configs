# vorons_configs

Репозиторий конфигураций парка принтеров Voron. Источник истины — этот репозиторий,
а живой каталог Klipper (`~/printer_data/config`) наполняется деплоем выбранного профиля.

## Русский

### Оси парка

Профиль машины задаётся один раз в `printers/<id>/machine.conf`. Деплой читает его,
рендерит `profile.cfg` и валидирует результат; интерактивного выбора при каждом
деплое нет. Полный справочник ключей, правила согласованности и эталон создания
профиля — [`docs/PROFILES.md`](docs/PROFILES.md).

| Ключ | Значения | Назначение |
|---|---|---|
| `size` | `150`, `200`, `250`, `300`, `350` | размер стола, мм |
| `model` | `trident`, `v24` | archetype: 3Z винты + `z_tilt` / 4Z ремни + `quad_gantry_level` |
| `kinematics` | `corexy` | тип кинематики; сверяется с `model` |
| `z_count` | `3`, `4` | число моторов Z; сверяется с `model` |
| `leveling` | `z_tilt`, `quad_gantry_level` | выравнивание стола; сверяется с `model` |
| `board` | `manta-m5p`, `manta-m8p` (V2.0), `manta-m8p-v1.0`, `manta-m8p-v1.1` | основная плата |
| `xy_step` | `0.9`, `1.8` | шаг двигателей X/Y: `0.9` только для 150; сверяется с мотором |
| `xy_motor` | ключ из `docs/tmc/motors.json` | мотор X/Y: `17HM19-1684` (0.9°) или `LDO-42STH48-2804AH-R` (1.8°) |
| `xy_driver` | `tmc5160`, `tmc2209` | микросхема драйвера X/Y; модуль `xy-<driver>-<motor>.cfg` должен быть в обеих семьях плат |
| `z_motor` | ключ из `docs/tmc/motors.json` | мотор Z (парк: `17HS4401S`; v24 от 250 мм — `17HS19-2004S1`) |
| `z_driver` | `tmc2109`, `tmc2209` | микросхема драйвера Z; модуль `<z_count>z-<driver>-<motor>.cfg` |
| `e_motor` | ключ из `docs/tmc/motors.json` | мотор экструдера; драйвер задан платой toolhead |
| `toolhead` | модуль из `std.configs/boards/` | плата инструментальной головы |
| `head` | модуль из `std.configs/extruder/heads/` | экструдер/хотэнд |
| `vm_xy` | `48` (по умолчанию), `55` | питание драйверов X/Y; 55 В допустимы только на `manta-m8p` (V2.0, HV-вход 24–60 В) |
| `vm_ze` | `24` | питание Z и обоих экструдеров; другие значения отклоняются |
| `xy_tbl`, `xy_toff` | TBL `0..3`, TOFF `1..15` (дефолт `0`/`3`) | входы чоппера X/Y |
| `z_tbl`, `z_toff` | TBL `0..3`, TOFF `1..15` (дефолт `0`/`3`) | входы чоппера Z |
| `e_tbl`, `e_toff` | TBL `0..3`, TOFF `1..15` (дефолт `0`/`3`) | входы чоппера обоих экструдеров |
| `features` | `fans`, `display`, `buttons`, `belay`, `btt_sfs`, `runout`, `extra_extruder`, `host`, `y_frame`, `eddy`, `eddy_f` | подключаемые подсистемы |
| `frame_w`, `frame_d` | мм | внешняя рама, для проверки якорей |
| `z_base_measured`, `z_leg_measured` | мм | измеренные стороны треугольника стола (trident) |

Пример `machine.conf`:

```ini
size=150
model=trident
kinematics=corexy
z_count=3
leveling=z_tilt
board=manta-m5p
xy_step=0.9
xy_motor=17HM19-1684
xy_driver=tmc5160
z_motor=17HS4401S
z_driver=tmc2109
e_motor=MOONS-CSE14HRA1L410A-01
toolhead=sht36-v3
head=HGX.8T
vm_xy=48
vm_ze=24
features=belay,runout,btt_sfs,extra_extruder,fans,display,buttons,host,y_frame
frame_w=310
frame_d=310
z_base_measured=227
z_leg_measured=245
```

Правило парка: только 150×150 использует TMC5160 + 17HM19-1684 (0.9°);
все остальные размеры — TMC5160 + LDO-42STH48-2804AH-R (1.8°, 42 Н·см,
2.8 А пик → `run_current: 1.9799` RMS). TMC5160 работает в SpreadCycle
(`stealthchop_threshold: 0`), SPI 1 МГц, `driver_TBL/TOFF/HSTRT/HEND/FD3/TPFD =
0/3/7/15/1/2`. Z: `17HS4401S` (1.7 А пик → 1.2021 А RMS) на trident и v24
до 250 мм, `17HS19-2004S1` (2.0 А пик → 1.4142 А RMS) на v24 от 250 мм.
Пара `xy_driver`+`xy_motor` проверяется по факту модулей в
`std.configs/mechanics/tmc/manta-m5p/` **и** `.../manta-m8p/`; Z-пара — по
модулю `<z_count>z-<driver>-<motor>.cfg`. Новые модули генерирует
`scripts/tmc_calc.py` (см. ниже), а `--wire-profile` записывает ключи
`xy_driver`/`xy_motor` двумя строками.

Питание драйверов разделено на два рейла: `vm_xy` (X/Y) и `vm_ze` (Z и оба
экструдера, всегда 24 В). Пары `board`/`vm_xy` проверяют и `render_profile.py`,
и `check_config.py` по одной таблице `BOARD_VM_XY_MAX`: 48 В для M5P и
M8P V1.0/V1.1, 55 В только для M8P V2.0 с HV-перемычкой. Профили парка:
`voron-t` — 48/24, `v24-350` — 55/24.

Заголовок сгенерированного `profile.cfg` показывает resolved-карту железа:

```
# X/Y: tmc5160+17HM19-1684 @vm_xy=48 | Z×3: tmc2109+17HS4401S @vm_ze=24 | E: tmc2209(sht36-v3)+MOONS-CSE14HRA1L410A-01
```

TMC5160 X/Y в репозитории разделены по плате: M8P V2.0 использует общий
**software SPI** на `PG6` (MOSI), `PG7` (MISO), `PG8` (SCLK) с отдельным
CS-пином на драйвер; M5P — аппаратный `spi2`. Аппаратный `spi1` на M8P V2.0
занимает `PA7`, который в этой раскладке является `TH3` (термистор драйвера),
поэтому одновременно `spi1` и `TH3` использовать нельзя.

### Z-драйверы M8P V2.0 и проверенная раскладка слотов

Раскладка Z-слотов — свойство конкретной машины. Общий шаблон
`mechanics/tmc/4z-tmc2209-17hs4401s.cfg` задаёт эталон
(`Z0=MOTOR3`, `Z1=MOTOR5`, `Z2=MOTOR6`, `Z3=MOTOR7`); модуль подключается
манифестом из пары `z_driver`+`z_motor` профиля, а не механикой. Профиль может
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
  всей модели), профильный `anchors.cfg` его перекрывает. `speed: 100.0`,
  `z_hop_speed: 30.0`. Якоря `quad_gantry_level` и реальные лимиты ещё не
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
обёрнут отдельно (см. «`BED_MESH_CALIBRATE` по умолчанию = scan» ниже), но
намеренно **не** через этот guard: сетка снимается на рабочей температуре, при
этом обёртка активируется только на eddy-машинах. Модуль
подключается в `profile.cfg` для модели v24; обёртки переименовывают команды на
`klippy:connect`, поэтому `G28.1` по-прежнему идёт через `[safe_z_home]`
(подъём 30 мм, зонд в центре стола), а `QUAD_GANTRY_LEVEL_BASE` — через модуль
`[quad_gantry_level]`.

Вызов `QUAD_GANTRY_LEVEL` без параметров на eddy-машине — два прохода. Сначала
грубый descend с `RETRY_TOLERANCE=0.25` и `RETRIES=2`: в этом режиме
пробирование останавливается на `descend_z` выше стола, поэтому просевший
задний угол портала не вдавливается в стол. Затем `_ZERO_REF_PROBE` измеряет
абсолютную высоту стола командой `PROBE` в точке `zero_reference_position`
(центр осей, если сетки нет); сопло встаёт в «точка стола − offset», потому что
это координаты стола, а не позиция сопла. `_QGL_FINE` запускает точный
`METHOD=scan` с `HORIZONTAL_MOVE_Z = измеренный Z + descend_z`: физический
зазор всегда равен `descend_z`, каким бы ни был абсолютный нуль. Если
контрольный замер отличается от нуля больше чем на `MAX_ZERO_DEV` (0.5 мм),
макрос прерывается **до** scan-прохода и печатает полный цикл калибровки
(`Z_ENDSTOP_CALIBRATE` + `SAVE_CONFIG` → `PROBE` →
`SET_GCODE_OFFSET Z=<минус показание>` → `Z_OFFSET_APPLY_PROBE` →
`SAVE_CONFIG`); расхождение больше 0.05 мм печатается предупреждением.
Проходов именно два отдельных макроса, потому что шаблон `gcode_macro`
рендерится целиком до выполнения G-code и не может использовать результат
`PROBE`, полученный в том же теле. Точный проход требует eddy-ветку
(`eddy_f`/`eddy`); на физическом `[probe]` остаётся один descend, а вызов с
любым параметром (например, `QUAD_GANTRY_LEVEL RETRY_TOLERANCE=0.015`) —
один проход, как раньше.

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
- `fans` требует `host`: `fans/host_fan.cfg` использует пин `host:gpio19`, а
  `[mcu host]` объявляется только файлом фичи `host`.
- `eddy` и `eddy_f` — вихретоковые щупы. Они взаимоисключающие, требуют
  `toolhead=sht36-v3` и убирают `std.configs/probe.cfg` (см. раздел
  «EDDY-F: внешний FLY-EDDY»).
- `local/uuids.cfg`, созданный мастером, содержит `[mcu]` и `[mcu extruder]`
  всегда, а `[mcu ext-extruder]` — только при `extra_extruder`.

### EDDY-F: внешний FLY-EDDY

Опция `eddy_f` подключает внешний вихретоковый щуп FLY-EDDY со шлейфом
**EDDY-F (FPC)** в разъём EDDY платы SHT36 V3 / Plus V3. Модуль —
`std.configs/sht36-v3.eddy-f.cfg`: аппаратный I2C `i2c1e`, LDC1612 по адресу
`42`, датчик температуры на `extruder:gpio28` (`Generic 3950`). Встроенный чип
SHT36 **Max** V3 живёт по адресу `43` — это отдельная фича `eddy`.

Включение — в `printers/<id>/machine.conf`:

```ini
toolhead=sht36-v3
features=...,eddy_f
```

- `eddy` и `eddy_f` взаимоисключающие: обе объявляют
  `[probe_eddy_current fly_eddy_probe]`, поэтому рендер и `new_machine.sh`
  отклоняют такую пару.
- Любая eddy-фича требует `toolhead=sht36-v3`: пины живут на MCU `extruder`.
- Адрес LDC1612 задан strap-перемычкой в железе: `42` — у внешнего FLY-EDDY-F
  из модуля, `43` — у встроенного чипа SHT36 Max V3. Поэтому адрес —
  машинный факт и при другом чипе переопределяется в
  `machine-extras.cfg` профиля:

  ```ini
  [probe_eddy_current fly_eddy_probe]
  i2c_address: 43
  ```

  Проверка адреса — `LDC_CALIBRATE_DRIVE_CURRENT CHIP=fly_eddy_probe`: успех
  печатает `reg_drive_current: N`, неверный адрес даёт
  `MCU 'extruder' I2C request to addr 42 reports error START_READ_NACK` и
  shutdown. На стенде v24-350 чип отвечает по `43` (проверено 2026-11-18),
  override стоит в его `machine-extras.cfg`; рабочий `i2c_speed` там же
  остаётся `4000000`.
- При `eddy_f` (как и при `eddy`) рендерер **не включает**
  `std.configs/probe.cfg`: Klipper не даёт одновременно зарегистрировать
  `[probe]` и `[probe_eddy_current]`. Z-хоуминг остаётся на
  `probe:z_virtual_endstop` из механики, `[safe_z_home]` не меняется (вариант
  с аппаратным концевиком — в «Гибриде» ниже).
- `x_offset`/`y_offset` в модуле — плейсхолдеры `0`; конвенция Klipper:
  **позиция щупа минус позиция сопла** (подробно — в «Гибриде» ниже). Измеренные
  значения живут в `printers/<profile>/machine-extras.cfg`, как и override
  `i2c_address`: это факт конкретной машины. Катушку ставят в 2–3 мм над
  соплом, а `descend_z: 2.5` — зазор сопло–стол, на котором останавливается
  пробирование. Собственного `z_offset` у eddy нет: в текущем Klipper это лишь
  устаревший псевдоним `descend_z`, и обе опции вместе недопустимы (старт
  падает с `Option 'z_offset' is not valid`); калибровка
  `PROBE_EDDY_CURRENT_CALIBRATE` + `SAVE_CONFIG` сохраняет таблицу частот
  `calibrate`.
- Нужен свежий Klipper с `probe_eddy_current` (`descend_z`, `rapid_scan`).
  Калибровка обязательна до первой печати: `LDC_CALIBRATE_DRIVE_CURRENT` и
  `PROBE_EDDY_CURRENT_CALIBRATE`; макросы
  `_LDC_CALIBRATE_DRIVE_CURRENT`/`PROBE_EDDY_CURRENT_CALIBRATE_AUTO` из
  документации Mellow оператор добавляет временно.
- Справочные значения взяты из документации Mellow «Использование EDDY»
  (FLY-SHT36 V3, `mellow.klipper.cn`): `i2c_speed: 4000000`,
  `frequency: 40000000` (кварц 40 МГц) и `descend_z: 2.5` при катушке в 2–3 мм
  над соплом; там же таблица адресов — внешний FLY-EDDY на V3/Plus V3 это
  `42`, встроенный LDC1612 у SHT36 Max V3 — `43`.
- Шлейф FPC подключать только при снятом питании платы.

#### Гибрид: концевик для Z, eddy для QGL/bed_mesh

`QUAD_GANTRY_LEVEL` в Klipper работает только через объект `probe`
(`quad_gantry_level.py` делает `lookup_object('probe')`), поэтому выровнять
портал по аппаратному концевику нельзя. Гибрид разделяет роли: `G28 Z`
паркуется по концевику M3-STOP (`SENS_2`), а `QUAD_GANTRY_LEVEL` и
`BED_MESH_CALIBRATE` пробируют eddy-щупом.

Рецепт — `endstop_pin` в `machine-extras.cfg` профиля (`[stepper_z]` там уже
переопределён пинами Z-моторов), а сам `position_endstop` — в `printer.cfg`
этого профиля (машинный файл, управляется до маркера `SAVE_CONFIG`):

```ini
# machine-extras.cfg
[stepper_z]
endstop_pin: !SENS_2

# printer.cfg — дефолт профиля, затем калибровка
[stepper_z]
position_endstop: -0.520
```

`position_endstop` обязателен: Klipper принимает его отсутствие только при
`probe:z_virtual_endstop`, иначе отказывается грузить секцию. `descend_z: 2.5`
в eddy-модуле остаётся страховкой пробирования (номинальный зазор
сопло–стол, на котором попытка останавливается).

Почему значение живёт в `printer.cfg`, а не в `machine-extras.cfg`: оно
индивидуально для машины, и его должен уметь записывать `SAVE_CONFIG`.
Klipper не сохраняет опцию, которая уже задана во включаемом файле
(`SAVE_CONFIG section 'stepper_z' option 'position_endstop' conflicts with
included value`), а `printer.cfg` — главный файл: при `SAVE_CONFIG` строка
плейсхолдера комментируется, а калиброванное значение уходит в autosave-блок
в конце файла.

Калибровок две:

1. `PROBE_EDDY_CURRENT_CALIBRATE CHIP=fly_eddy_probe` — таблица `calibrate`
   (частота по высоте); её сохраняет `SAVE_CONFIG`, и живёт она только в
   autosave стенда (`printer.cfg`), в git не попадает;
2. `Z_ENDSTOP_CALIBRATE` — `position_endstop` концевика, затем `SAVE_CONFIG`:
   значение комментарием заменяет плейсхолдер в `printer.cfg` и попадает в
   autosave. В git калиброванное значение не уходит.

`printer.cfg` — частично управляемый: деплой заменяет всё выше маркера
`SAVE_CONFIG` копией из профиля, а калиброванное значение живёт в блоке ниже и
сохраняется. Если файл пересоздан, Klipper поднимется на плейсхолдере `-0.520`,
и калибровку концевика нужно выполнить заново до первой печати.

Калибровать eddy нужно с `ACCEPT` на 0.3–0.5 мм выше соприкосновения сопла:
если катушка стоит низко над соплом (≈1 мм), точка контакта попадает в
плоский участок отклика, где шаг 40 мкм даёт ~300 Гц при шуме ~400 Гц — Klipper
пишет `Frequency too noisy ... Failed calibration - No usable data`. Тот же
щуп с `ACCEPT` на 0.5 мм выше даёт ~5.4 кГц на 40 мкм, диапазон частот
~277 кГц и шум ~1 мкм (стенд v24-350, 2026-11-18). Поэтому либо катушку
ставят в рекомендованные 2–3 мм над соплом, либо калибруют от приподнятого
положения, а нуль сводят со столом отдельно: `Z_ENDSTOP_CALIBRATE` задаёт
Z=0 по бумаге, после чего расхождение `PROBE` с нулём убирают
`Z_OFFSET_APPLY_PROBE`.

#### Смещение катушки: знак, проверка, влияние

`x_offset`/`y_offset` в Klipper — это **позиция щупа минус позиция сопла**
(`manual_probe` считает `bed_x = test_x + x_offset`, а `ProbePointsHelper`
двигает сопло в `point − offset`). На v24-350 центр катушки стоит за соплом
на 33 мм по +Y, поэтому в `machine-extras.cfg` профиля стоит `y_offset: 33`;
`x_offset: 0` — предположение о симметрии. Плейсхолдеры `0` в
`std.configs/sht36-v3.eddy-f.cfg` остаются: измеренный факт машины живёт в
профиле, как и override `i2c_address`.

Проверка знака и величины — одна команда (сопло встаёт на `Y = 175 − 33`):

```text
G28
G1 X175 Y142 Z10 F6000
PROBE
```

Ожидание: `Result: at 175.000,175.000 estimate contact at z=...`
(`bed_y = toolhead_y + y_offset = 142 + 33`). Если Klipper печатает
`109.000`, знак перевёрнут и дальше идти нельзя. Заодно подтверждается
`bed_x = 175`, то есть `x_offset: 0`.

Klipper применяет смещение только в `bed_mesh` (`BedMeshCalibrate` вызывает
`probe_helper.use_xy_offsets(True)`). `quad_gantry_level`, `z_tilt` и
`resonance_tester` двигают портал по своим `points` как по позициям сопла,
поэтому якоря QGL в `printers/v24-350/anchors.cfg` записаны как
«точка стола − offset»: желаемые точки под катушкой `(50,60)`, `(50,290)`,
`(300,290)`, `(300,60)` превращаются в
`points: 50,27 / 50,257 / 300,257 / 300,27`. Порядок точек 0..3 сохранён от
каталога, чтобы сопла Z-осей не перепутались. `gantry_corners` не меняются:
Klipper считает экстраполяцию по `bed_x/bed_y`, то есть уже в координатах
стола.

Смещение **не** меняет Z-калибровки: `position_endstop` концевика и остаток
`PROBE` от `y_offset` не зависят, меняется только XY-атрибуция точек. Ноль
стенда сведён: `PROBE` после `G28 Z` даёт остаток ≈ `+0.11` мм (2026-11-21).

Передняя граница — ход сопла, а не край стола: ближайшая точка стола под
катушкой `Y = 33`, потому что сопло не может уйти ниже `position_min_y = 0`.
По X смещения нет, границы симметричны.

#### `BED_MESH_CALIBRATE` по умолчанию = scan

`std.macros/homing.cfg` оборачивает `BED_MESH_CALIBRATE`
(`rename_existing: BED_MESH_CALIBRATE_BASE`) так же, как
`QUAD_GANTRY_LEVEL`. На eddy-машине голый вызов сначала делает контрольный
`PROBE` в `zero_reference_position` (макрос `_ZERO_REF_PROBE` сам компенсирует
`x_offset`/`y_offset`), затем scan-проход на высоте `bed_z + descend_z`.
Причина та же, что у QGL: scan идёт на абсолютном Z, а ошибка «датчик вне
диапазона» поднимается только после всех точек, поэтому высота должна быть
измеренной, а не статическими `2.5`. `descend_z` берётся из
`[probe_eddy_current <имя>]`, guard прерывает прогон, если поверхность уехала
больше чем на `MAX_ZERO_DEV` (0.5 мм) от нуля.

Правила обёртки:

- вызов с `METHOD=...` (например `METHOD=automatic`) идёт напрямую в Klipper
  одним проходом: метод и высоту тогда задаёт оператор;
- физический `[probe]` (машина `voron-t`) всегда идёт прямой веткой — у него
  нет scan-режима;
- явный `HORIZONTAL_MOVE_Z=` перекрывает расчётный: `{rawparams}` стоит
  последним, а Klipper оставляет последнее значение ключа;
- обёртка намеренно не погружается в `_PROBE_TEMP_GUARD` (сетку снимают
  горячей), дрейф щупа компенсирует `[temperature_probe fly_eddy_probe]`.

Высота scan для QGL вычисляется так же — `измеренный Z + descend_z` из
контрольного `PROBE`. Если `BED_MESH_CALIBRATE` вызван с `METHOD=scan` явно,
`HORIZONTAL_MOVE_Z=<descend_z>` (2.5) по-прежнему передают вручную: таблица
`calibrate` покрывает только свой диапазон, а штатные 5 мм у `bed_mesh` и
10 мм у QGL выходят за него — `probe_eddy_current sensor not in valid range`.
Понижать `horizontal_move_z` в секциях до 2.5 нельзя: в режиме `automatic`
(descend) пробирование начинается с этой высоты и сразу упрётся в
`descend_z`. `rapid_scan` не рекомендуется: он менее точен, а ошибка датчика в
`scan`/`rapid_scan` поднимается только после прохода всех точек — именно
поэтому перед точным проходом и стоит грубый descend.

Полный цикл калибровки нуля (guard в `_QGL_FINE` теперь печатает его целиком):
`Z_ENDSTOP_CALIBRATE` + `SAVE_CONFIG`, затем `PROBE` →
`SET_GCODE_OFFSET Z=<минус показание>` → `Z_OFFSET_APPLY_PROBE` →
`SAVE_CONFIG`. Шаг `SET_GCODE_OFFSET` обязателен: без активного gcode-offset
`Z_OFFSET_APPLY_PROBE` отвечает `Nothing to do: Z Offset is 0`.

Контроль согласованности двух Z=0: после `G28 Z` команда `PROBE` на столе
должна дать ≈ 0 (± 0.02 мм); расхождение означает, что одна из калибровок
неверна.

В коммитнутом профиле `v24-350` гибрид уже включён (`features=...,eddy_f`,
override — в его `machine-extras.cfg`), а `position_endstop` в его
`printer.cfg` — дефолт `-0.520` до калибровки на стенде. Требования те же,
что у обычного `eddy_f`: свежий Klipper с `descend_z` и шлейф EDDY-F,
подключаемый
только при снятом питании платы.

### Проверки валидатора

`check_config.py` эмулирует чтение конфигурации Klipper и дополнительно
проверяет ссылки на MCU по исходному тексту опций:

- **ERROR** — pin-префикс `NAME:` (`^NAME:PIN`, `NAME:PIN`), `mcu:` у
  `[board_pins]` или `sensor_mcu:` у `[temperature_sensor]` ссылается на MCU,
  для которого нет `[mcu NAME]` (виртуальные `*_virtual_endstop` исключены).
- **ERROR** — `[probe]` вместе с секцией `probe_eddy_current*`: Klipper
  регистрирует оба объекта как `probe` и падает на
  `Registering duplicate object 'probe'`. Ошибка ловится и при возврате
  `[probe]` в файл платы: парсер такие дубликаты молча сливает.
- **ERROR** — у `[stepper_z]` задан физический `endstop_pin` (не `probe:…`),
  а `position_endstop` нет: Klipper требует его для аппаратного Z-концевика.
  Обратная ошибка тоже ловится: `position_endstop` рядом с
  `probe:z_virtual_endstop` — Klipper такую опцию не читает и падает на
  `Option 'position_endstop' is not valid in section 'stepper_z'`.
- **ERROR** — точки, к которым Klipper смещение щупа не применяет
  (`quad_gantry_level points`, `z_tilt points`, `resonance_tester
  probe_points`), выносят катушку `point + (x_offset, y_offset)` за лимиты
  оси. Сообщение печатает готовые координаты катушки; `points` надо писать
  как «точка стола − offset».
- **ERROR** — `bed_mesh` проверяется по двум наборам границ:
  `mesh_min`/`mesh_max` — позиция катушки, она должна лежать на столе, а
  `mesh − offset` — позиция сопла, она должна остаться в
  `position_min/position_max`. Раньше проверялось только второе.
- **WARNING** — ненулевые `x_offset`/`y_offset` вместе с
  `quad_gantry_level`/`z_tilt`: напоминание, что якоря задаются как «точка
  стола − offset».
- **NOTICE** — сетка меньше 0.8 площади достижимой зоны: печатает расчётные
  `mesh_min`/`mesh_max`/`probe_count` по формуле
  `max(position_min + offset + 2, edge)` / `min(position_max + offset, bed −
  edge)` с маржой `edge = 12 мм` под катушкой.
- **WARNING** — `[mcu NAME]` объявлен, но на него нет ни одной ссылки: признак
  осиротевшей секции от платы, которой на машине нет. Неявный `mcu` и `host`
  предупреждение не вызывают.
- **ERROR** — активный `stealthchop_threshold >= 1000` у любой `[tmc*]`-секции:
  Klipper включает StealthChop, и регистры чоппера не работают. Сообщение
  содержит готовую команду `tmc_calc.py --update-module … --mode spreadcycle`.
- **WARNING** — у `[tmc*]`-секции ключа `stealthchop_threshold` нет: Klipper
  работает в SpreadCycle по умолчанию, но парковый инвариант требует явный `0`.
  Аудит обходит весь `std.configs/**` и `printers/*/local/**`, поэтому
  недосягаемый из `machine.conf` `boards/fly-sb2040.cfg` тоже проверяется.
- **ERROR** — `driver_*`-опция, которую модуль этого семейства не читает
  (`driver_THIGH` — типовой пример): Klipper падает на старте с
  `Option 'driver_THIGH' is not valid in section 'tmc5160 stepper_x'`.
  Легальный список берётся из `DRIVER_KEYS` в `tmc_calc.py`, второй копии нет;
  для порога полношагового перехода есть `high_velocity_threshold` в мм/с, из
  которого Klipper сам считает `THIGH`. Неизвестные семейства
  (`[tmc2109 …]`) пропускаются, а не угадываются.
- **ERROR** — `driver_VHIGHFS: 1` без положительного `high_velocity_threshold`:
  `THIGH` остаётся `0`, то есть «порог превышен на любой скорости», и каждый
  ход идёт в полный шаг (0.2 мм на полный шаг при 40 мм / 200 шагов) —
  измерительные поездки и сетка квантуются. Сообщение требует порог выше
  `[bed_mesh] speed`.
- **WARNING** — `driver_VHIGHCHM: 1` без положительного
  `high_velocity_threshold`: драйвер постоянно сидит в высокоскоростном
  режиме чоппера; upstream `docs/TMC_Drivers.md` называет такую смену режима
  при низкой скорости «poor and confusing».
- **NOTICE** — `high_velocity_threshold` задан, но ни `driver_VHIGHFS`, ни
  `driver_VHIGHCHM` не включены: регистр `THIGH` ни на что не влияет.
- **ERROR** — `--jinja-lint`: тело любого `[gcode_macro]` из `std.macros/` и
  `printers/*/macros.cfg` не разбирается Jinja с разделителями Klipper
  (`{% %}` для блоков, `{ }` для вывода), то есть Klipper не загрузит конфиг.
  Нужен `jinja2` — он есть в `~/klippy-env/bin/python`; системный `python3`
  без модуля выдаёт понятную ошибку вместо тихого пропуска.

### Раскладка репозитория

```text
vorons_configs/
├── printers/
│   └── voron-t/
│       ├── machine.conf        # оси и фичи машины (единственный источник выбора)
│       ├── profile.cfg         # ГЕНЕРИРУЕТСЯ из machine.conf, коммитится
│       ├── printer.cfg         # управляется до маркера SAVE_CONFIG, autosave внизу
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
├── docs/tmc/                   # калькуляторы Trinamic/ADI, CALCS.md, motors.json (НЕ деплоятся)
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
- **seed** — создаются только если файла ещё нет: `KlipperScreen.conf`,
  `crowsnest.conf`, `sonar.conf`, `telegram.conf`.
- **`printer.cfg` — частично управляемый.** При каждом деплое всё выше маркера
  `#*# <---------------------- SAVE_CONFIG ---------------------->` заменяется
  копией из `printers/<id>/printer.cfg`, а маркер и autosave-блок ниже
  сохраняются побайтно (`scripts/merge_printer_cfg.py`). Опция в голове файла,
  которую определяет и autosave, комментируется: иначе Klipper отдал бы
  приоритет голове и калибровка потерялась бы. При `-b` старая версия уходит в
  `DEST/.backup/<ts>/`.
- **`.deployed_profile`** — dot-файл состояния в `DEST`: id последнего
  фактически развёрнутого профиля. Его читает `scripts/moonraker_update.sh`
  после обновления репозитория. После записи файлов deploy идемпотентно
  приводит секцию `[update_manager vorons_configs]` в `moonraker.conf` к
  канонической (`scripts/lib/moonraker_conf.py`); под prune dot-файлы не
  попадают и в `--check` не участвуют. Рядом лежит `.deployed_commit` —
  commit, который хук уже задеплоил и после которого перезапустил Klipper
  (нужен таймеру, чтобы не повторять работу).
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

Мастер генерирует `machine.conf` из эталонного
`scripts/templates/machine.conf.template` (русские комментарии у каждого
ключа), создаёт `printer.cfg` с дефолтами, `anchors.cfg` с TODO,
`machine-extras.cfg`, `macros.cfg`, `moonraker.conf`, `local/`, рендерит
`profile.cfg` и валидирует профиль. Пара X/Y и Z-пара по умолчанию берутся по
правилу парка и archetype; переопределяются флагами `--xy-motor`, `--xy-driver`,
`--z-driver`, `--z-motor`, `--e-motor`. В интерактивном терминале мастер
спрашивает список фич (или принимает `--features`); `belay`/`btt_sfs` без
`extra_extruder` отклоняются. Дальше нужно заполнить `local/uuids.cfg` и
измеренные якоря. Пошаговый сценарий и таблица ключей — в
[`docs/PROFILES.md`](docs/PROFILES.md). Перед первой калибровкой проверить хост
CAN: `ip -details link show can0` должен показывать `qlen 1024`, а
`systemctl status ifup@can0` — не `status=1/FAILURE` (см. «Известные патчи
Klipper и настройка CAN-хоста»).

### Скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/deploy_configs.sh -p <профиль>` | деплой; `--render`, `--check`, `--matrix` (full/lite, по платам), `--axis K=V`, `-n`, `-b`, `-d`, `--no-prune` |
| `scripts/render_profile.py --machine-dir <профиль> [--write]` | рендер `profile.cfg` из `machine.conf` |
| `scripts/check_config.py` | офлайн-парсер: `--config-dir`, `--merged`, `--machine`, `--stale-check`, `--jinja-lint` (нужен `jinja2`) |
| `scripts/collect_local.sh -p <профиль>` | `std.config.local/*.cfg` → профиль + autosave-снимок |
| `scripts/new_machine.sh` | мастер заведения профиля (фичи, UUID-шаблон) |
| `scripts/build_mcu.sh -c <config> [--src DIR] [-o out] [--clean] [-j N] [--print-bin]` | сборка `klipper.bin`, `katapult.bin` или `klipper.elf` |
| `scripts/flash_mcu.sh [can\|bridge\|query\|serial\|dfu\|linux] ...` | прошивка контроллера |
| `scripts/update_firmware.sh [-p профиль] [--dry-run] [--auto]` | пересборка и прошивка всех MCU после обновления Klipper |
| `scripts/install_update_hook.sh [--profile профиль] [--dry-run]` | установка systemd path/timer хука (нужен sudo) |
| `scripts/moonraker_update.sh [-p профиль] [-d DEST] [-n] [-a]` | деплой после обновления репозитория: профиль, ensure секции, `--auto` — stamp коммита и перезапуск Klipper |
| `scripts/install_config_update_hook.sh [--dry-run] [--uninstall]` | systemd path/timer, который запускает `moonraker_update.sh --auto` (нужен sudo) |
| `scripts/lib/moonraker_conf.py ensure --config <файл>` | идемпотентная каноническая секция `[update_manager vorons_configs]`; `selftest` |
| `scripts/tmc_calc.py --driver tmc2209\|tmc5160 ...` | расчёт параметров TMC по даташиту мотора: `--write`, `--update-module`, `--wire-profile`, `--json`, `--selftest` |
| `scripts/tmc_tune.py --profile printers/<id> --run` | подбор `max_velocity`/`max_accel` через `TEST_SPEED`; `--z-test` — подбор `max_z_velocity`/`max_z_accel` через `TEST_SPEED_Z`: `--dry-plan`, `--apply`, `--heat`, `--z-offline-result`, `--selftest` |
| `scripts/bringup.sh -p <профиль>` | первичная настройка: `deploy → tmc → motion → z-motion → pid-e → pid-b → done`, resume через `--from`, проверка плана `--dry-run` |
| `scripts/lib/bringup_api.py` | клиент Moonraker (stdlib): `info`, `status`, `query`, `gcode`, `store`, `restart`, `wait-ready`, `wait-marker`, `verify-hold` |

### Расчёт TMC: `docs/tmc/` и `scripts/tmc_calc.py`

`docs/tmc/` в деплой не попадает (копируются только `std.configs/**`,
`std.macros/**` и файлы профиля) и содержит:

- `TMC2209_Calculations.xlsx`, `TMC5160_Calculations.xlsx` — вендорские
  калькуляторы Trinamic/ADI; адреса, дата и sha256 — `docs/tmc/SOURCES.md`;
- `CALCS.md` — карта «лист/ячейка → формула → функция скрипта»; правило
  проекта: новая формула сначала описывается здесь, потом попадает в скрипт;
- `motors.json` — параметры моторов парка, у каждой записи обязательна ссылка
  на даташит (`source`).

`scripts/tmc_calc.py` считает рекомендованный `run_current` и параметры
чоппера, а по умолчанию только печатает готовый stanza:

```bash
# мотор из базы: рекомендуемый ток и регистры
python3 scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24

# свой мотор (ток, L и R — из даташита), несколько секций
python3 scripts/tmc_calc.py --driver tmc2209 --i-rated 1.7 --l-mh 2.8 \
    --r-ohm 1.5 --vm 24 --section stepper_z --section stepper_z1

# StealthChop вместо SpreadCycle; PWM_OFS/GRAD — из PWM_AUTO после автотюнинга
python3 scripts/tmc_calc.py --driver tmc5160 --motor LDO-42STH48-2804AH-R \
    --vm 48 --mode stealthchop --pwm-ofs 30 --pwm-grad 14

# записать модуль и прописать пару xy_driver+xy_motor в профиль
python3 scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24 \
    --write manta-m5p/xy-tmc5160-17HM19-1684.cfg --wire-profile printers/voron-t

# пересчитать уже существующий модуль на месте (номинал, --force для записи)
python3 scripts/tmc_calc.py --update-module \
    std.configs/mechanics/tmc/3z-tmc2109-17hs4401s.cfg \
    --vm 24 --motor 17HS4401S --current-basis peak --i-factor 1.0 --force
```

Правила скрипта:

- печатаются только ключи `driver_*` из белого списка, сверенного с
  установленным Klipper (`driver_TPFD` есть только у TMC5160);
- регистры тока (`CS`/`IRUN`, `GLOBALSCALER`) в конфиг не попадают: Klipper
  считает их сам из `run_current`, в выводе они только для сверки;
- `run_current = min(номинал × --i-factor, предел IC)`; для X/Y и Z номинал
  даташита задаётся как `--current-basis peak` и переводится в RMS делением
  на √2 (0.707 × peak), у экструдеров базис — RMS по умолчанию. Мотор, у
  которого номинал выше предела IC (например, 1.68 A RMS на TMC2209 с шунтом
  0.110 Ом), отклоняется с кодом 2;
- `--write` пишет только внутрь `std.configs/mechanics/tmc/`, без `--force`
  существующий файл не перезаписывается;
- `--wire-profile` проверяет `xy_step` профиля (1.8° мотор в машину с
  `xy_step=0.9` не проведётся) и наличие пары в обеих семьях плат, пишет
  `xy_driver` и `xy_motor` двумя строками в `machine.conf` и
  перегенерирует `profile.cfg`; дальше нужен
  `./scripts/deploy_configs.sh -p <профиль> --check`;
- `--update-module FILE [--sections a,b]` пересчитывает **существующий** файл:
  `run_current`, `stealthchop_threshold` и (в SpreadCycle) `driver_TBL/TOFF/
  HSTRT/HEND`; пины, транспорт (`uart_pin`/`cs_pin`/`spi_*`), `sense_resistor`,
  ручные `driver_*` вне расчётного набора и порядок опций сохраняются.
  Комментарии-альтернативы (`#run_current: …`) не трогаются, сверху
  появляется блок расчёта с маркерами, который переписывается при повторном
  запуске. Без `--force` печатается diff, файл не меняется. Режим чоппера
  берётся из секции (`stealthchop_threshold >= 1000` → StealthChop), `--mode`
  его переопределяет. `--update-module` работает и с `std.configs/extruder/main.cfg`
  и `std.configs/extra-extruder.cfg`, поэтому для экструдера нужен
  `e_motor` в `machine.conf`;
- `motors.json` содержит не только моторы, но и таблицу `motor_by_module`
  (имя модуля → мотор) — обратная таблица для имён модулей; `bringup.sh`
  берёт моторы из `xy_motor`/`z_motor`/`e_motor`. Запись
  экструдера парка — `MOONS-CSE14HRA1L410A-01` (NEMA14, 1.0 A, 1.9 Ω,
  1.41 мГн, HGX 8T);
- файл `3z-tmc2109-17hs4401s.cfg` исторически назван `2109`, но содержит
  секции `[tmc2209 …]`; имя не переименовывается (на него ссылается
  `mechanics/trident.cfg`), правится только содержимое;
- `--selftest` сверяет формулы с сохранёнными xlsx (±1 LSB) и прогоняет doctest.

#### Входы чоппера и парковый SpreadCycle

- `TBL`/`TOFF` — входы расчёта (§3 `CALCS.md`), а не его результат. Они вынесены
  в `machine.conf` парами по группам осей: `xy_tbl/xy_toff`, `z_tbl/z_toff`,
  `e_tbl/e_toff` (дефолт `0`/`3`; TBL=0 на всех моторах парка).
  Диапазоны проверяет `render_profile.py` (TBL `0..3`, TOFF `1..15`), источник
  значения печатается в отчёте `tmc_calc.py` (`cli|module|profile`).
- Все драйверы парка работают в SpreadCycle с явным `stealthchop_threshold: 0`.
  Для X/Y и экструдеров так было и раньше (в Klipper отсутствие ключа = SpreadCycle),
  теперь это закреплено инвариантом: `check_config.py` даёт ERROR на активный
  порог ≥ 1000 и WARNING на отсутствующий ключ, аудит идёт по всему
  `std.configs/**` и `printers/*/local/**`, включая недосягаемый из
  `machine.conf` `boards/fly-sb2040.cfg`; `bringup_tmc.py` отказывает на
  stealthchop-секции вместо тихого выбрасывания регистров.
- Полношаговый переход по скорости задаётся **только** опцией
  `high_velocity_threshold` (мм/с): по ней `tmc.TMCVhighHelper` считает
  `THIGH = fCLK · rotation_distance / (full_steps_per_rotation · 256) / v`
  (для v24-350 `9375 / v`, то есть 700 мм/с → `THIGH=13`). Ключа
  `driver_THIGH` в Klipper нет — это ошибка старта, её ловит
  `check_config.py`. `driver_VHIGHFS`/`driver_VHIGHCHM` — легальные биты
  `CHOPCONF` (18 и 19), но без положительного порога они включают полный шаг
  (FS) или высокоскоростной чоппер (CHM) навсегда; порог обязан быть выше
  самой быстрой измерительной поездки (`[bed_mesh] speed`).
- Полношаговый переход проверен на стенде v24-350 (2026-11-22) и **не
  применён**. Механизм подтверждён: `thigh` с `VELOCITY=500` даёт `THIGH=19`,
  биты `vhighfs`/`vhighchm` видны в `CHOPCONF`, `fsactive=1` в 9 из 11
  сэмплов `DRV_STATUS` в движении и `0` во всех 11 сэмплах в покое. Но при
  64 микрошагах базовая линия уже проходит 750/8500, 900/9000 и 900/10000
  без потерь (3/3, `|Δ| ≤ 35` счётчиков МКУ, полный шаг — 64), а вариант
  «только CHM» так же чист (9/9, `|Δ| ≤ 31`); гейт требует провала baseline,
  которого нет. Прогон вариантов C/D был прерван отходом toolhead-MCU
  `extruder` (за 1 с 6288 `rx_error` и 6333 `tx_retries`, затем
  `Timeout on connect`; шина и USB-CAN мост остались живы). Причина найдена:
  разъём CAN/питания на SHT36 отошёл на высокоскоростных прогонах; после
  посадки разъёма серия C/D повторена: C 9/9 чисто (`|Δ| ≤ 10`), D 9/9,
  кроме одного прогона 750/8500 со сдвигом +515 счётчиков по одному мотору —
  то же редкое событие «~8 полных шагов», что и в baseline, без ошибок CAN в
  этом окне. Отдельно проверены скорости выше 1000 мм/с: 1000–1200 мм/с с
  ускорением 8500 проходят без потерь и у baseline, и у full step, а 1100/10000
  теряет ~8 полных шагов у обеих конфигураций, то есть выигрыша нет. При этом
  сам паттерн шагов не теряет: диагностика с парковкой на Z=30 даёт `0/0` по
  паттерну, а смещение появляется только после финального `G28` — сдвигается
  привязка гоминга (механика/ремни), а не траектория. Данные и
  вывод записаны в `printers/v24-350/machine-extras.cfg`. Откат ручных
  битов — только рестарт Klipper: `INIT_TMC` возвращает их из кэша полей.
- `klipper_tmc_autotune` (`andrewmcgr`, GPL-3.0) в парк **не берём**. Это
  рантайм-оверрайдёр: на `klippy:ready` и по `AUTOTUNE_TMC` он пересчитывает
  CHOPCONF, PWMCONF, COOLCONF, TPWMTHRS, TCOOLTHRS и THIGH поверх конфига,
  поэтому каталожные модули `tmc_calc.py` и железо расходятся молча. Для Z и
  экструдера режим `auto` включает StealthChop (сброс `CHM`), требует
  `interpolate: true` и CoolStep (`semin=2, semax=4`) — прямые конфликты с
  `stealthchop_threshold: 0`, `interpolate: false` и «без COOLCONF». Наконец,
  сам модуль держит `VHIGHFS = VHIGHCHM = False` и считает порог FS от
  `1.2 × vmaxpwm` StealthChop, что к SpreadCycle-парку неприменимо. Полезен
  только `motor_database.cfg` как второй источник констант: запись
  `ldo-42sth48-2804ah` = 0.7 Ом / 0.6 мГн / 2.8 А / 0.42 Н·м совпадает с
  `docs/tmc/motors.json`, поэтому мотор парка переименован в
  `LDO-42STH48-2804AH-R` без пересчёта токов. Код autotune в репозиторий не
  копируется (GPL-3.0), только факты и ссылка.
- Огибающая +50 % от применённых 750/8500 (1125 мм/с, 12750 мм/с²) измерена
  на v24-350 2026-11-23 на чистом baseline (A: `thigh=0`, оба бита 0, без
  VHIGH-опций). Клетка 1125/12750 прошла 3/3 (`|Δ| ≤ 7` счётчиков МКУ,
  полный шаг — 64), но 1000/12750 провалилась 2/3, 1125/8500 — 1/3,
  1125/10000 — 3/3 (`|Δ|` до 505); провалы не монотонны по ускорению.
  Диагностика `diag4` с парковкой Z=30 на провальных клетках дала
  `patterns 0/0` во всех прогонах и сдвиг `rehome` ±512 счётчиков (8 полных
  шагов): после прогона уезжает привязка гоминга, а не теряется шаг в
  паттерне. `LOST_STEPS` = 0, температура TMC 54.9–56.0 °C, toolhead-MCU
  остался `bus_state=active` без `rx_error`/`tx_error` (росли только
  накопительные `tx_retries`). Поэтому `[printer] 750/8500` не поднимаются:
  правило запаса 15 % берётся от монотонно пройденной клетки, а её выше
  1125/8500 нет.
- X/Y с **128 микрошагами** проверены той же серией +50 % (2026-11-23,
  baseline A, без VHIGH): 1000/12750, 1125/8500 и 1125/12750 — 3/3,
  1125/10000 — 1/3 (`dy` ≈ -507 счётчиков). `diag4` на 1125/10000 даёт
  `patterns 0/0` и сдвиг rehome до 1535 счётчиков (2.4 мм): предел — привязка
  гоминга, а не разрешение шага. 128 — это 640 шагов/мм, 1125 мм/с = 720 кГц
  на мотор; Manta M8P их принял без `Timer too close`. Применённый дефолт
  остаётся **64**: 1125/10000 не проходит, а у 64 уже есть длинная тепловая и
  качественная история. У драйвера Y в LDO-модулях `diag1_pin: DIAG_1` теперь
  включён по умолчанию (как `DIAG_0` у X); на `CHOPCONF` это не влияет.
- Лестница +15 % к 1500/15000 проверена на v24-350 (2026-11-23) на том же
  чистом baseline, по 3 повтора на клетку и по критерию 0.1 мм (32 счётчика
  при 64 микрошагах, 64 при 128). При 64 критерий держит только стартовая
  750/8500, при 128 — непрерывно до 992/11241; 1141/12927 проваливает обе
  серии, а выше снова чисто, то есть провалы не монотонны. `diag4` на всех
  провальных клетках даёт `patterns 0/0` и весь сдвиг в `rehome` (до 2544
  счётчиков = 4.0 мм при 128): снова уезжает привязка гоминга, а не теряется
  шаг. 1500 мм/с при 128 — это 960 кГц на мотор, Manta M8P выдержал без
  `Timer too close`/`Stepper move too late`. `LOST_STEPS` = 0, CAN без
  `rx_error`/`tx_error`. Применённые 750/8500 и 64 микрошага не меняются;
  правило запаса 15 % берётся от наивысшей монотонной клетки ≤ 0.1 мм.
- X/Y и Z пересчитаны от пикового тока даташита в RMS (`--current-basis peak`,
  `I_RMS = I_peak / √2 ≈ 0.707 · I_peak`): LDO 2.8 A peak → 1.9799 A RMS,
  17HM19 1.68 A peak → 1.1879 A RMS, Z 17HS4401S 1.7 A peak → 1.2021 A RMS,
  Z 17HS19-2004S1 2.0 A peak → 1.4142 A RMS (`driver_HSTRT: 0`,
  `driver_HEND: 0`). Экструдеры остаются на фактических
  0.55/0.60 A RMS: расчёт идёт под эти токи (`--run-current`), а не под номинал
  1.0 A мотора.

`--run-current A` задаёт `run_current` напрямую; `i_factor` выводится из него и
печатается как `i_factor_effective`. `--i-factor 0.8` остаётся стартовой точкой
ручных прогонов; в парке X/Y и Z пересчитываются на номинал
(`--i-factor 1.0 --current-basis peak`), экструдеры — на 0.55/0.60 A RMS.
Исторические 0.951/1.697/0.600 A — результат тепловых испытаний, в
`docs/tmc/CALCS.md` §8 они помечены как устаревшие. На LDO при 1.98 A расчёт
даёт `HystStart > 20` (TBL уже 0): это следствие 48/55 В и L = 0.6 мГн,
предупреждение информационное.

### Первичная настройка машины: `scripts/bringup.sh`

Один прогон на новую машину: **deploy → tmc → motion → z-motion → pid-e → pid-b → done**.
Скрипт оркестрирует существующие инструменты и не дублирует их логику.

```bash
cd ~/vorons_configs
./scripts/bringup.sh -p voron-t --dry-run     # план без команд и записи
./scripts/bringup.sh -p voron-t               # полный прогон, оператор у станка
./scripts/bringup.sh -p voron-t --from pid-e  # продолжить после обрыва
./scripts/bringup.sh -p voron-t --only tmc    # один этап
```

| Этап | Что делает |
|---|---|
| `deploy` | `deploy_configs.sh -p <id> -b`, затем `POST /machine/restart` (на Moonraker v0.10 — `/machine/services/restart`) и ожидание `ready` (60 с) |
| `tmc` | `check_config.py --merged` даёт живой список `[tmc*]`; для каждой секции берутся мотор (`xy_motor` / `z_motor` / `e_motor`) и рейл (`vm_xy` для X/Y, `vm_ze` для Z/E), `tmc_calc.py --update-module` переписывает ток и чоппер, затем deploy + restart |
| `motion` | `tmc_tune.py --run --apply --iterations 2`: лестница `TEST_SPEED`, вердикт по `GET_POSITION`, бисекция, запись пары в `machine-extras.cfg`; требует подтверждения оператора |
| `z-motion` | `tmc_tune.py --run --apply --z-test --iterations 2`: лестница `max_z_velocity`/`max_z_accel`, на каждого кандидата запись `std.config.local/z_speed_test.cfg`, рестарт, повторное применение TMC, `G28`, выравнивание и `TEST_SPEED_Z`; перекос Z-моторов прерывает серию; требует подтверждения оператора |
| `pid-e` | `PID_CALIBRATE HEATER=extruder TARGET=250`, разбор `pid_Kp/Ki/Kd` из `gcode_store`, патч `printers/<id>/local/pid.cfg`, deploy + restart, проверка удержания 30 с (±1.5 °C) |
| `pid-b` | то же для `heater_bed` при 120 °C |
| `done` | сводка `git diff --stat` и предлагаемое сообщение коммита |

Гейты S0 (без них прогон не стартует): чистый `git status` клона (нужен
откат), валидный `machine.conf` и свежий `profile.cfg`, зелёный
`deploy_configs.sh --check`, `std.config.local/uuids.cfg` без `REPLACE_WITH_`,
`anchors.cfg` без `TODO` для этапов `motion`/`z-motion`; Moonraker: Klipper
`ready`, печать не идёт, нагреватели < 45 °C.

Особенности:

- `SAVE_CONFIG` не используется: PID пишется в git, деплоится и применяется
  перезапуском Klipper;
- `z-motion` подбирает `max_z_velocity`/`max_z_accel` макросом `TEST_SPEED_Z`:
  каждый кандидат — запись `std.config.local/z_speed_test.cfg`, рестарт Klipper,
  повторное применение TMC (рестарт сбрасывает `SET_TMC_*`), `G28`,
  выравнивание (`QUAD_GANTRY_LEVEL` или `Z_TILT_ADJUST`) и прогон. Коридор
  держит сопло не ниже `--z-floor` (40 мм) и на 5 мм ниже верха оси; перекос
  Z-моторов больше полного шага прерывает серию с требованием `G28` +
  выравнивания. После теста обязательны `G28` и выравнивание: `position_endstop`
  стенда — плейсхолдер, поэтому `z_offset` до ручной калибровки недействителен;
- экструдеры остаются на фактических 0.55 A (`extruder`) и 0.60 A
  (`ext-extruder`) при `e_tbl=0`; расчётные `HSTRT/HEND` (7/4 и 7/5) дают более
  гранулярную регулировку тока, чем апстримные 7/6. Предупреждение `HystStart >
  20` для номинала 1.0 A больше не ожидается: ток не повышается, а `TBL=0`
  держит гистерезис в норме;
- состояние (`~/printer_data/.bringup/<id>.json`) хранит последний этап, HEAD
  и журнал прогонов; после обрыва продолжайте `--from`;
- после частичного прогона клон изменён: закоммитьте результат (или
  `git checkout .`) перед следующим запуском — этого требует гейт чистоты;
- откат: `git -C ~/vorons_configs checkout . &&
  ./scripts/deploy_configs.sh -p <id> -b` и перезапуск Klipper; коммит, push и
  тег делает владелец, `bringup.sh` их не выполняет;
- PID стола 350 при 120 °C близок к `max_temp: 145`; `verify_heater` штатно
  прервёт runaway, после чего этап завершится ошибкой с выключенными
  нагревателями.

Проверки без железа:

```bash
./scripts/bringup.sh -p voron-t --dry-run
./scripts/bringup.sh -p v24-350 --dry-run
python3 scripts/lib/bringup_api.py selftest
python3 scripts/lib/bringup_state.py selftest
python3 scripts/lib/bringup_pid.py selftest
python3 scripts/lib/bringup_tmc.py selftest
python3 scripts/tmc_tune.py --selftest
python3 scripts/tmc_tune.py --profile printers/v24-350 --z-test --dry-plan
python3 scripts/tmc_calc.py --selftest
```

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

### Автообновление конфигов через Moonraker

`[update_manager vorons_configs]` в `moonraker.conf` только тянет этот
репозиторий: Moonraker не исполняет `install_script` (эта устаревшая опция
лишь читается на `PKGLIST`), поэтому деплой запускает отдельный systemd-хук.
`scripts/install_config_update_hook.sh` ставит `klipper-configs-deploy.path`
(следит за `.git/HEAD`, `.git/FETCH_HEAD` и `.git/refs/heads` клона) и
`klipper-configs-deploy.timer` (повтор каждые 10 минут); оба запускают
`scripts/moonraker_update.sh --auto` от пользователя принтера без sudo.

Хук:

1. определяет профиль — по маркеру `~/printer_data/config/.deployed_profile`,
   который пишет `deploy_configs.sh` при фактическом деплое; если маркера нет,
   побайтно сравнивает живой `machine.conf` с рендером каждого профиля
   (`render_profile.py --dump-conf`, именно его пишет deploy) и при отсутствии
   или неоднозначности совпадений завершается ошибкой;
2. в режиме `--auto` пропускает работу, если `DEST/.deployed_commit` уже равен
   текущему `HEAD` (повторный запуск таймера ничего не делает);
3. деплоит профиль (`deploy_configs.sh -p <id> -b`); встроенный гейт не даёт
   писать во время печати;
4. идемпотентно приводит секцию `[update_manager vorons_configs]` в живом
   `moonraker.conf` к канонической (`scripts/lib/moonraker_conf.py`) и
   предупреждает, если её пришлось изменить: перезапуск Moonraker остаётся
   ручным, иначе хук убил бы сам себя;
5. перезапускает Klipper через API Moonraker (`managed_services` в секции не
   используется: Moonraker перезапустил бы Klipper до того, как деплой
   закончится) и записывает короткий commit в `DEST/.deployed_commit`;
6. печатает сводку (профиль, короткий commit, результат).

Любая ошибка деплоя или перезапуска завершает хук с ненулевым кодом, и таймер
повторяет попытку; до успешного перезапуска stamp не обновляется, поэтому
Klipper не останется со старым конфигом. Ручной запуск без `--auto` деплоит и
пишет stamp, но Klipper не перезапускает (хук печатает напоминание).

Bootstrap (один раз на машине):

```bash
sudo scripts/install_config_update_hook.sh       # path + timer, нужен sudo
./scripts/deploy_configs.sh -p <профиль> -b      # маркер + moonraker.conf
sudo systemctl restart moonraker                 # один раз: перечитать update-секцию
```

Дальше — «Update» в Mainsail или `POST /machine/update/full`: Moonraker делает
pull, path-юнит замечает новый коммит, хук деплоит конфиги и перезапускает
Klipper. Грязный клон (`git status` не пуст) Moonraker обновлять откажется, и
автодеплой не отработает: это штатное поведение `update_manager`, правки нужно
закоммитить или отбросить.

### Секреты

- Не коммитить реальный `bot_token`/`chat_id` в `telegram.conf`: в репозитории заглушка.
- Репозиторий приватный; `local/` (UUID, PID, input shaper) коммитится осознанно.
- `KlipperScreen.conf` содержит автогенерируемый блок `#~#`, поэтому он seed.

### Доступ к хостам парка

- Пароли хостов лежат только локально: `secrets/hosts.env` (каталог в
  `.gitignore`, файл `chmod 600`). В репозитории — шаблон
  `secrets/hosts.env.example` без значений. Значения пишутся в двойных
  кавычках: файл подключается через `set -a; . secrets/hosts.env`, и без
  кавычек пароль с `$`, обратной кавычкой, `#`, `!` или пробелом оболочка
  раскроет или обрежет.
- Стенд v24-350: `V24_350_HOST=192.168.52.30`, `V24_350_SSH_USER`,
  `V24_350_SSH_PASS`. Вход — по SSH-ключу (`ssh-copy-id` один раз, пароль
  нужен только для установки ключа и для `sudo`).
- Пароль не должен попадать в argv и в историю: передавайте его через
  переменную окружения (`sshpass -e` с `SSHPASS`) либо pty-обёрткой, которая
  сама читает `secrets/hosts.env`; `sshpass` в системе может отсутствовать, и
  тогда обёртка — единственный вариант.
- Проверка утечки после коммитов: `git status --short` не показывает
  `secrets/` (кроме `hosts.env.example`), а поиск по истории
  (`git log -p`) не находит пароль.

### Калибровка input shaper (Measuring Resonances)

Методика Klipper [Measuring Resonances](https://www.klipper3d.org/Measuring_Resonances.html)
на живом стенде. Результат пишется в `printers/<id>/local/input.shaper.cfg`
и коммитится: репозиторий остаётся source of truth, `SAVE_CONFIG` не используется.

Что нужно заранее:

- в `klippy-env` установлен `numpy` — без него `MEASURE_AXES_NOISE` и
  `TEST_RESONANCES` падают с `Failed to import numpy module`:
  `~/klippy-env/bin/pip install numpy`;
- акселерометр закреплён на toolhead, стол и сопло свободны, прошивка
  содержит trsync-патч (см. «Известные патчи Klipper»);
- графики строятся не на хосте, а на рабочей машине: `~/klipper/scripts/calibrate_shaper.py`
  и `graph_accelerometer.py` требуют `numpy`, `scipy` и `matplotlib`.

```bash
API="python3 ~/vorons_configs/scripts/lib/bringup_api.py"
$API gcode G28
$API --timeout 580 gcode QUAD_GANTRY_LEVEL        # портал должен быть ровным
$API --timeout 120 gcode MEASURE_AXES_NOISE      # ориентир lis2dw: < 10
$API --timeout 880 gcode 'TEST_RESONANCES AXIS=X'   # ~6 мин
$API --timeout 880 gcode 'TEST_RESONANCES AXIS=Y'
# CSV лежит на хосте в /tmp/resonances_<ось>_<дата>.csv
scp spectre@<host>:/tmp/resonances_x_*.csv .
python3 calibrate_shaper.py -o shaper_x.png resonances_x_*.csv
```

Порядок важен: `G28` в этом профиле сам прогоняет QGL, но повторный явный
`QUAD_GANTRY_LEVEL` перед замером обязателен. На стенде v24-350 перекос
портала почти на 2 мм размазывал пик Y (FWHM 7.8 → 9.4 Гц, вертикальное плечо
уходило на 60–65 Гц), а частота гуляла 33.5–37.3 Гц; после QGL до
0.0085 мм пик стал одиночным и острым.

Одну ось нельзя запускать, пока идёт предыдущий тест: команда синхронная,
между ними достаточно `wait-idle --timeout 900`. Пик ищется в `psd_x` для X и
в `psd_y` для Y; `calibrate_shaper.py` подбирает `shaper_freq_*` и
`shaper_type_*` с оценкой остаточных вибраций и сглаживания.

Ориентация датчика проверяется до первого замера: на неподвижном принтере
`ACCELEROMETER_QUERY` должен показывать весь вектор тяжести в Z
(`z≈+9475 mm/s²` для lis2dw при `axes_map: -y,z,-x`), ход +X — отклик только
в `x`, ход +Y — только в `y`. Иначе замер молча пишется не в те оси (так было
на v24-350 с прежним `axes_map: x,z,-y`: вертикаль висела на X).

### Известные патчи Klipper и настройка CAN-хоста

Конфиги репозитория этих правок не содержат — они применяются на самом хосте
принтера. Стенд v24-350 работает на Klipper `v0.13.0-828` (проверено
2026-11-23): фикс trsync `29d4ec2` уже в его истории, а `can0` поднят с
`qlen 1024`. Оба пункта ниже остаются обязательными для машин на более старых
сборках.

1. **trsync (upstream `29d4ec2`, 2026-11-11).** Без фикса при парковке и
   зондировании возможен `MCU 'mcu' shutdown: Timer too close`: знаковое
   сравнение `(int64_t)(expire - m->expire_clock) >= m->min_extend_ticks`
   может отправить MCU `trsync_set_timeout` с уже прошедшим clock.

   ```bash
   git -C ~/klipper cherry-pick --no-commit 29d4ec2d6d840ee839333306003a400da186d41d
   sudo systemctl restart klipper      # chelper пересобирается при старте
   ```

   Признаки применения: в свежем `klippy.log` есть
   `Building C code module c_helper.so` и строка
   `Modified files: klippy/chelper/trdispatch.c`. MCU перепрошивать не нужно.

   Важно: `cherry-pick --no-commit` оставляет правку в индексе, поэтому
   репозиторий Klipper считается изменённым (`git describe --dirty` даёт
   `-dirty`), и Moonraker отказывает в обновлении с
   `Update aborted, repo has been modified`. Порядок обновления Klipper:

   ```bash
   # 1. снять локальную правку; `checkout --` здесь НЕ работает — он вернёт
   #    версию из индекса, то есть тот же патч
   git -C ~/klipper restore --staged --worktree klippy/chelper/trdispatch.c
   # 2. обновить Klipper (Moonraker/Mainsail или git -C ~/klipper pull)
   # 3. проверить, что фикс пришёл с upstream
   grep -n "expire >= m->expire_clock" ~/klipper/klippy/chelper/trdispatch.c
   # 4. если строки нет (master ещё без фикса) — повторить cherry-pick
   ```

   Если правка была закоммичена локально, вместо шага 1 — `git revert`
   соответствующего коммита.

2. **Глубина TX-очереди `can0`.** `ifup@can0` должен поднимать
   `txqueuelen 1024`: при штатных 10 кадрах Klipper пишет
   `Got error -1 in can write: (105)No buffer space available`, кадры
   `trsync_set_timeout` теряются и MCU уходит в `Timer too close`. В образе
   CB2 нет `ifconfig` (net-tools не установлен), поэтому в
   `/etc/network/interfaces` нужен `ip`, иначе `ifup@can0` падает с кодом 1:

   ```
   iface can0 can static
       bitrate 1000000
       up ip link set dev can0 txqueuelen 1024
   ```

   Проверка: `ip -details link show can0` показывает `qlen 1024`,
   `systemctl status ifup@can0` — без `status=1/FAILURE`, в `klippy.log` нет
   новых `No buffer space available`.

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
  вниз), точка парковки и Z=0 — центр стола 175,175. `G28`,
  `QUAD_GANTRY_LEVEL` и `BED_MESH_CALIBRATE` на стенде прогоняются
  (2026-11-15: три цикла без shutdown), но якоря QGL и реальные лимиты
  по-прежнему не замерены, а зонд шумит — `Probe samples exceed tolerance`
  почти на каждой точке, поэтому QGL идёт 230–450 с, а сетка 10×10 около
  20 минут. `z_offset` в общем `probe.cfg` (`-0.400`) снят на
  voron-t и на стенде требует перекалибровки до первой печати.
  Вход probe у всей семьи M8P перенесён на `SENS_2` (M3-STOP, разъём с
  маркировкой «Z stop»): `PF2` у V2.0, `PF5` у V1.x; референсные M4-STOP/PF1
  (V2.0) и PC0 (V1.x) свободны. Сам `pin: !SENS_2` теперь объявлен в
  `std.configs/probe.cfg`, а не в файлах плат: файл платы включается всегда, и
  оставленный там `[probe]` регистрировал второй probe-объект в любом
  eddy-профиле. На стенде зонд должен быть переставлен на
  M3-STOP — если проводка осталась в M4-STOP, `QUERY_PROBE` не увидит
  срабатывание, а `G28 Z` уедет в стол.
- Гибрид на v24-350 (парковка Z по концевику, QGL и `bed_mesh` по eddy)
  включён в коммитнутом профиле и загружается на стенде (2026-11-18: `probe` —
  это `probe_eddy_current fly_eddy_probe`, `QUERY_ENDSTOPS` видит `stepper_z`,
  LDC1612 отвечает по адресу `43`, в логе нет `Registering duplicate object` и
  `Timer too close`). Таблица `calibrate` eddy снята на стенде (диапазон
  ~277 кГц, шум ~1 мкм при 1–3 мм) и сохранена в autosave;
  `position_endstop` концевика хранится в `printer.cfg` профиля (плейсхолдер
  выше маркера `SAVE_CONFIG`, калиброванное значение — в autosave). Нуль eddy сводится со столом
  через `PROBE` + `Z_OFFSET_APPLY_PROBE`; прогоны QGL/mesh и первый слой — за
  оператором.
  `check_config.py` ловит обе типовые ошибки такой сборки — `[probe]` вместе с
  `[probe_eddy_current]` и физический `endstop_pin` у `[stepper_z]` без
  `position_endstop`.
- Голый `QUAD_GANTRY_LEVEL` на eddy-машине теперь двухпроходный (грубый
  descend + контрольный `PROBE` + точный scan), поэтому стал дольше: это
  затрагивает `PRINT_START`, `TEST_SPEED` (`std.macros/test_speed.cfg`) и
  `scripts/tmc_tune.py` — они вызывают команду без параметров. Один проход
  по-прежнему вызывается любым параметром, например
  `QUAD_GANTRY_LEVEL RETRY_TOLERANCE=0.015`. На стенде v24-350 (2026-11-19)
  грубый descend сходится за ~18 с (разброс 0.035 мм), контрольный `PROBE`
  вместе с точным scan — за ~22 с (0.004 мм при допуске 0.015), явный
  одиночный проход — за ~14 с. Guard больше не мешает: нуль стенда сведён,
  `PROBE` после `G28 Z` даёт остаток ≈ `+0.11` мм (2026-11-21). Голый
  `BED_MESH_CALIBRATE` на eddy-машине теперь тоже двухшаговый (контрольный
  `PROBE` + scan на `bed_z + descend_z`), а расширенная сетка 15×14 на
  v24-350 расчётно идёт около 8 минут вместо ~2 на прежних 140×140 (реальное
  время замеряется на стенде).
- `anchors.cfg` для voron-t содержит унаследованные `max_z 105` и лимиты `153/156`;
  они помечены TODO до замера по физическим упорам. Правая сторона треугольника
  принята равной 245 мм по измерению левой.
- Маржа `bed_mesh` для размеров кроме 150 задаётся не каталожным `0.3·S`, а
  формулой достижимой зоны по измеренному смещению щупа (`P` — точка стола
  под катушкой, `edge` — маржа катушки от края стола, 2 мм — запас на член с
  ходом): `mesh_min = max(position_min + offset + 2, edge)`,
  `mesh_max = min(position_max + offset, bed − edge)`. На v24-350 при
  `y_offset: 33` и `edge = 12` это `mesh_min: 12, 35`, `mesh_max: 338, 338`,
  `probe_count: 15, 14` (~23.3 мм шаг, расчётно ~8 мин scan-прогона). Передняя граница
  упирается в ход сопла, задняя и боковые — в маржу под катушкой; зона
  `Y < 33` физически не пробируется, печать там опирается на bicubic-
  экстраполяцию. `edge` — стартовое допущение: систематический уклон
  последнего ряда в `BED_MESH_OUTPUT` лечат увеличением `edge`, точечные
  помехи (клипсы, магниты) — через `faulty_region_N_min/max`.
- Ветка `eddy` (`std.configs/sht36-v3.eddy.cfg`, встроенный чип SHT36 Max V3)
  по-прежнему выключена: макросы `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` не
  перенесены с машины-донора. Новая опция `eddy_f` самодостаточна и этих
  макросов не требует.
- Прошивка проверена офлайн (`--dry-run` и реальные сборки): CAN/serial/DFU
  требуют `~/katapult` и `python3-serial` и запускаются вручную из консоли.

## English

Repository of configuration files for my Voron printer fleet. The repository is the
source of truth; the live Klipper directory (`~/printer_data/config`) is populated by
deploying one printer profile.

### Fleet axes

A machine profile is defined once in `printers/<id>/machine.conf`. Deploy reads it,
renders `profile.cfg` and validates the result; there is no interactive choice on
every deploy. The full key reference, consistency rules and the profile creation
guide live in [`docs/PROFILES.md`](docs/PROFILES.md) (Russian).

| Key | Values | Purpose |
|---|---|---|
| `size` | `150`, `200`, `250`, `300`, `350` | bed size, mm |
| `model` | `trident`, `v24` | archetype: 3Z leadscrews + `z_tilt` / 4Z belts + `quad_gantry_level` |
| `kinematics` | `corexy` | kinematics type; must match `model` |
| `z_count` | `3`, `4` | number of Z motors; must match `model` |
| `leveling` | `z_tilt`, `quad_gantry_level` | bed levelling; must match `model` |
| `board` | `manta-m5p`, `manta-m8p` (V2.0), `manta-m8p-v1.0`, `manta-m8p-v1.1` | main board |
| `xy_step` | `0.9`, `1.8` | X/Y step angle: `0.9` only at 150 mm; checked against the motor |
| `xy_motor` | key of `docs/tmc/motors.json` | X/Y motor: `17HM19-1684` (0.9°) or `LDO-42STH48-2804AH-R` (1.8°) |
| `xy_driver` | `tmc5160`, `tmc2209` | X/Y driver IC; `xy-<driver>-<motor>.cfg` must exist in both board families |
| `z_motor` | key of `docs/tmc/motors.json` | Z motor (fleet: `17HS4401S`; v24 250+ — `17HS19-2004S1`) |
| `z_driver` | `tmc2109`, `tmc2209` | Z driver IC; `<z_count>z-<driver>-<motor>.cfg` |
| `e_motor` | key of `docs/tmc/motors.json` | extruder motor; its driver is fixed by the toolhead board |
| `toolhead` | module under `std.configs/boards/` | toolhead board |
| `head` | module under `std.configs/extruder/heads/` | extruder/hotend |
| `vm_xy` | `48` (default), `55` | X/Y driver rail; 55 V is legal only on `manta-m8p` (V2.0, HV input 24-60 V) |
| `vm_ze` | `24` | Z and both extruders; any other value is rejected |
| `xy_tbl`, `xy_toff` | TBL `0..3`, TOFF `1..15` (default `0`/`3`) | X/Y chopper inputs |
| `z_tbl`, `z_toff` | TBL `0..3`, TOFF `1..15` (default `0`/`3`) | Z chopper inputs |
| `e_tbl`, `e_toff` | TBL `0..3`, TOFF `1..15` (default `0`/`3`) | chopper inputs of both extruders |
| `features` | `fans`, `display`, `buttons`, `belay`, `btt_sfs`, `runout`, `extra_extruder`, `host`, `y_frame`, `eddy`, `eddy_f` | optional subsystems |
| `frame_w`, `frame_d` | mm | outer frame, used for anchor sanity checks |
| `z_base_measured`, `z_leg_measured` | mm | measured bed triangle sides (trident) |

Example `machine.conf`:

```ini
size=150
model=trident
kinematics=corexy
z_count=3
leveling=z_tilt
board=manta-m5p
xy_step=0.9
xy_motor=17HM19-1684
xy_driver=tmc5160
z_motor=17HS4401S
z_driver=tmc2109
e_motor=MOONS-CSE14HRA1L410A-01
toolhead=sht36-v3
head=HGX.8T
vm_xy=48
vm_ze=24
features=belay,runout,btt_sfs,extra_extruder,fans,display,buttons,host,y_frame
frame_w=310
frame_d=310
z_base_measured=227
z_leg_measured=245
```

Fleet rule: only 150x150 uses TMC5160 + 17HM19-1684 (0.9 degree);
every other size uses TMC5160 + LDO-42STH48-2804AH-R (1.8 degree, 42 Ncm,
2.8 A peak -> `run_current: 1.9799` RMS). TMC5160 runs in SpreadCycle
(`stealthchop_threshold: 0`), SPI at 1 MHz, with
`driver_TBL/TOFF/HSTRT/HEND/FD3/TPFD = 0/3/7/15/1/2`. Z: `17HS4401S`
(1.7 A peak -> 1.2021 A RMS) on trident and v24 below 250 mm,
`17HS19-2004S1` (2.0 A peak -> 1.4142 A RMS) on v24 from 250 mm. The
`xy_driver`+`xy_motor` pair is checked against the actual modules in
`std.configs/mechanics/tmc/manta-m5p/` **and** `.../manta-m8p/`; the Z pair is
checked through `<z_count>z-<driver>-<motor>.cfg`. New modules are generated by
`scripts/tmc_calc.py` (see below), and `--wire-profile` writes `xy_driver` and
`xy_motor` as two lines.

Driver power has two rails: `vm_xy` for X/Y and `vm_ze` for Z and both
extruders (always 24 V). `render_profile.py` and `check_config.py` validate the
`board`/`vm_xy` pair through one table, `BOARD_VM_XY_MAX`: 48 V on the M5P and
M8P V1.0/V1.1, 55 V only on the M8P V2.0 with the HV jumper fitted. Fleet
profiles: `voron-t` is 48/24, `v24-350` is 55/24.

The generated `profile.cfg` header shows the resolved hardware map:

```
# X/Y: tmc5160+17HM19-1684 @vm_xy=48 | Z×3: tmc2109+17HS4401S @vm_ze=24 | E: tmc2209(sht36-v3)+MOONS-CSE14HRA1L410A-01
```

TMC5160 X/Y configs are split by board: the M8P V2.0 uses the shared
**software SPI** bus on `PG6` (MOSI), `PG7` (MISO), `PG8` (SCLK) with a separate
CS pin per driver; the M5P uses hardware `spi2`. Hardware `spi1` on the M8P V2.0
reserves `PA7`, which is `TH3` (the driver thermistor) in this layout, so `spi1`
and `TH3` cannot be used together.

### M8P V2.0 Z drivers and the verified slot layout

The Z slot layout is a property of each machine. The shared
`mechanics/tmc/4z-tmc2209-17hs4401s.cfg` module defines the reference
(`Z0=MOTOR3`, `Z1=MOTOR5`, `Z2=MOTOR6`, `Z3=MOTOR7`); the module is pulled in by
the manifest from the profile's `z_driver`+`z_motor` pair, not by the mechanic.
A profile may override the `[stepper_z*]` and `[tmc2209 stepper_z*]` sections in
`machine-extras.cfg` (the include is last, so its values win over the catalog).

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
  `speed: 100.0`, `z_hop_speed: 30.0`. The `quad_gantry_level` anchors and the
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
not delayed. `BED_MESH_CALIBRATE` is wrapped separately (see
"`BED_MESH_CALIBRATE` defaults to scan" below), but deliberately **not**
through this guard: a mesh is taken at print temperature, and the wrapper only
activates on eddy machines. The module is included by `profile.cfg` for the v24
model; the wrappers rename the commands on `klippy:connect`, so `G28.1` still
goes through `[safe_z_home]` (30 mm lift, probe at the bed centre) and
`QUAD_GANTRY_LEVEL_BASE` through the `[quad_gantry_level]` module.

A bare `QUAD_GANTRY_LEVEL` call on an eddy machine runs two passes. First the
rough descend pass with `RETRY_TOLERANCE=0.25` and `RETRIES=2`: in that mode
probing stops `descend_z` above the bed, so a sagged rear gantry corner is not
pushed into it. Then `_ZERO_REF_PROBE` measures the absolute bed height with
`PROBE` at the `zero_reference_position` point (the axis centre when there is
no mesh); the nozzle goes to "bed point - offset", because that is a bed
coordinate and not a nozzle position. `_QGL_FINE` starts the precise
`METHOD=scan` pass with `HORIZONTAL_MOVE_Z = measured Z + descend_z`, so the
physical gap is always `descend_z` whatever the absolute zero is. If the check
probe differs from zero by more than `MAX_ZERO_DEV` (0.5 mm), the macro aborts
**before** the scan and prints the full zero cycle (`Z_ENDSTOP_CALIBRATE` +
`SAVE_CONFIG` → `PROBE` → `SET_GCODE_OFFSET Z=<minus the reading>` →
`Z_OFFSET_APPLY_PROBE` → `SAVE_CONFIG`); a deviation above 0.05 mm is reported
as a warning. The passes are separate
macros because a `gcode_macro` template is rendered in full before its G-code
runs and cannot use a `PROBE` result obtained in the same body. The fine pass
needs an eddy branch (`eddy_f`/`eddy`); a physical `[probe]` keeps the single
descend pass, and a call with any parameter (for example
`QUAD_GANTRY_LEVEL RETRY_TOLERANCE=0.015`) stays a single pass as before.

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
- `fans` requires `host`: `fans/host_fan.cfg` drives `host:gpio19`, and
  `[mcu host]` is only declared by the `host` feature file.
- `eddy` and `eddy_f` are eddy-current probes. They are mutually exclusive,
  require `toolhead=sht36-v3` and drop `std.configs/probe.cfg` (see
  "EDDY-F: external FLY-EDDY").
- The `local/uuids.cfg` created by the wizard always contains `[mcu]` and
  `[mcu extruder]`, and `[mcu ext-extruder]` only with `extra_extruder`.

### EDDY-F: external FLY-EDDY

The `eddy_f` option wires an external FLY-EDDY probe with the **EDDY-F (FPC)**
harness into the EDDY connector of the SHT36 V3 / Plus V3 toolboard. The module
is `std.configs/sht36-v3.eddy-f.cfg`: hardware I2C on `i2c1e`, LDC1612 at
address `42`, the temperature sensor on `extruder:gpio28` (`Generic 3950`). The
built-in SHT36 **Max** V3 chip lives at `43` and is the separate `eddy` feature.

Enable it in `printers/<id>/machine.conf`:

```ini
toolhead=sht36-v3
features=...,eddy_f
```

- `eddy` and `eddy_f` are mutually exclusive: both declare
  `[probe_eddy_current fly_eddy_probe]`, so the renderer and `new_machine.sh`
  reject that pair.
- Any eddy feature requires `toolhead=sht36-v3`: its pins live on the
  `extruder` MCU.
- The LDC1612 I2C address is strapped in hardware: `42` on the external
  FLY-EDDY-F of the module, `43` on the built-in SHT36 Max V3 chip. The
  address is therefore a machine fact and is overridden in the profile's
  `machine-extras.cfg` when the chip differs:

  ```ini
  [probe_eddy_current fly_eddy_probe]
  i2c_address: 43
  ```

  Check it with `LDC_CALIBRATE_DRIVE_CURRENT CHIP=fly_eddy_probe`: success
  prints `reg_drive_current: N`, a wrong address gives
  `MCU 'extruder' I2C request to addr 42 reports error START_READ_NACK` and a
  shutdown. The v24-350 bench chip answers at `43` (verified 2026-11-18), so
  its `machine-extras.cfg` carries the override; `i2c_speed` there stays
  `4000000`.
- With `eddy_f` (and with `eddy`) the renderer **does not include**
  `std.configs/probe.cfg`: Klipper cannot register `[probe]` and
  `[probe_eddy_current]` at the same time. Z homing stays on the mechanics
  `probe:z_virtual_endstop` and `[safe_z_home]` is unchanged (the hardware
  switch variant is the "Hybrid" section below).
- `x_offset`/`y_offset` in the module are `0` placeholders; the Klipper
  convention is **probe position minus nozzle position** (see "Hybrid" below).
  Measured values live in `printers/<profile>/machine-extras.cfg`, like the
  `i2c_address` override: they are facts of one machine. Mount the coil 2-3 mm
  above the nozzle; `descend_z: 2.5` is the nozzle-to-bed gap at which probing
  stops. The eddy probe has no `z_offset` of its own: in a current Klipper that
  is only the deprecated alias of `descend_z`, and both options together abort
  startup with `Option 'z_offset' is not valid`;
  `PROBE_EDDY_CURRENT_CALIBRATE` + `SAVE_CONFIG` store the `calibrate`
  frequency table.
- A current Klipper with `probe_eddy_current` (`descend_z`, `rapid_scan`) is
  required. Calibration is mandatory before the first print:
  `LDC_CALIBRATE_DRIVE_CURRENT` and `PROBE_EDDY_CURRENT_CALIBRATE`; the
  `_LDC_CALIBRATE_DRIVE_CURRENT`/`PROBE_EDDY_CURRENT_CALIBRATE_AUTO` macros from
  the Mellow documentation are added temporarily by the operator.
- The reference values come from the Mellow "EDDY usage" page (FLY-SHT36 V3,
  `mellow.klipper.cn`): `i2c_speed: 4000000`, `frequency: 40000000` (40 MHz
  crystal) and `descend_z: 2.5` with the coil 2-3 mm above the nozzle; the same
  page has the address table - an external FLY-EDDY on V3/Plus V3 is `42`, the
  built-in LDC1612 of SHT36 Max V3 is `43`.
- Connect the FPC harness only with the board powered off.

#### Hybrid: switch for Z, eddy for QGL/bed_mesh

In Klipper `QUAD_GANTRY_LEVEL` works only through the `probe` object
(`quad_gantry_level.py` calls `lookup_object('probe')`), so the gantry cannot be
levelled with a hardware switch. The hybrid splits the roles: `G28 Z` parks on
the M3-STOP switch (`SENS_2`), while `QUAD_GANTRY_LEVEL` and
`BED_MESH_CALIBRATE` probe with the eddy sensor.

The recipe keeps `endstop_pin` in the profile's `machine-extras.cfg`
(`[stepper_z]` already reopens there for the Z motor pins) and puts
`position_endstop` into that profile's `printer.cfg` (machine-local, managed up to the `SAVE_CONFIG` marker):

```ini
# machine-extras.cfg
[stepper_z]
endstop_pin: !SENS_2

# printer.cfg, profile default before calibration
[stepper_z]
position_endstop: -0.520
```

`position_endstop` is mandatory: Klipper accepts its absence only with
`probe:z_virtual_endstop` and otherwise refuses to load the section.
`descend_z: 2.5` in the eddy module stays the safety stop of probing (the
nominal nozzle-to-bed gap at which an attempt ends).

The value lives in `printer.cfg` and not in `machine-extras.cfg` because it is
per-machine and `SAVE_CONFIG` has to be able to persist it: Klipper refuses to
save an option that an included file already sets (`SAVE_CONFIG section
'stepper_z' option 'position_endstop' conflicts with included value`), while
`printer.cfg` is the main file, so a save comments the placeholder out and
appends the calibrated value to the autosave block.

There are two calibrations:

1. `PROBE_EDDY_CURRENT_CALIBRATE CHIP=fly_eddy_probe` — the `calibrate`
   frequency table; `SAVE_CONFIG` stores it in the bench autosave
   (`printer.cfg`), so it never reaches git;
2. `Z_ENDSTOP_CALIBRATE` — the switch `position_endstop`, then `SAVE_CONFIG`:
   the value comments out the placeholder in `printer.cfg` and lands in the
   autosave, so git never sees a calibrated value.

`printer.cfg` is partially managed: a deploy replaces everything above the
`SAVE_CONFIG` marker from the profile and keeps the calibrated block below it.
If the file is recreated, Klipper boots on the `-0.520` placeholder and the
endstop has to be calibrated again before the first print.

Calibrate the eddy with `ACCEPT` 0.3-0.5 mm above nozzle contact: when the coil
sits low over the nozzle (about 1 mm), the contact point lands in the flat part
of the response where a 40 um step gives ~300 Hz against ~400 Hz of noise, and
Klipper answers `Frequency too noisy ... Failed calibration - No usable data`.
The same sensor accepted 0.5 mm higher gives ~5.4 kHz per 40 um, a ~277 kHz
frequency span and ~1 um of noise (v24-350 bench, 2026-11-18). So either mount
the coil at the recommended 2-3 mm above the nozzle, or calibrate from a raised
position and set the zero separately: `Z_ENDSTOP_CALIBRATE` defines Z=0 on
paper, then the `PROBE` difference is removed with `Z_OFFSET_APPLY_PROBE`.

#### Probe offset: sign, one-command check, consequences

In Klipper `x_offset`/`y_offset` are the **probe position minus the nozzle
position** (`manual_probe` computes `bed_x = test_x + x_offset`, while
`ProbePointsHelper` moves the nozzle to `point − offset`). On v24-350 the coil
centre sits 33 mm behind the nozzle, so the profile's `machine-extras.cfg`
carries `y_offset: 33`; `x_offset: 0` is the symmetry assumption. The `0`
placeholders in `std.configs/sht36-v3.eddy-f.cfg` stay: the measured value is a
machine fact and lives in the profile, like the `i2c_address` override.

The sign and magnitude are checked with one command (the nozzle goes to
`Y = 175 − 33`):

```text
G28
G1 X175 Y142 Z10 F6000
PROBE
```

Expected: `Result: at 175.000,175.000 estimate contact at z=...`
(`bed_y = toolhead_y + y_offset = 142 + 33`). A `109.000` reply means the sign
is inverted and nothing further should be run. The same run confirms
`bed_x = 175`, i.e. `x_offset: 0`.

Klipper applies the offsets only in `bed_mesh` (`BedMeshCalibrate` calls
`probe_helper.use_xy_offsets(True)`). `quad_gantry_level`, `z_tilt` and
`resonance_tester` move the toolhead by their `points` as nozzle positions, so
the QGL anchors in `printers/v24-350/anchors.cfg` are written as
"bed point - offset": the desired coil points `(50,60)`, `(50,290)`,
`(300,290)`, `(300,60)` become
`points: 50,27 / 50,257 / 300,257 / 300,27`. The 0..3 order is kept from the
catalog so the Z axes do not swap. `gantry_corners` are unchanged: Klipper
extrapolates from `bed_x/bed_y`, i.e. already in bed coordinates.

The offset does **not** change Z calibrations: the switch `position_endstop`
and the `PROBE` residual are independent of `y_offset`; only the XY attribution
of the points moves. The bench zero is matched: `PROBE` after `G28 Z` reads a
residual of about `+0.11` mm (2026-11-21).

The front boundary is the nozzle travel, not the bed edge: the nearest bed
point the coil can reach is `Y = 33`, because the nozzle cannot go below
`position_min_y = 0`. There is no X offset, so the side boundaries are
symmetric.

#### `BED_MESH_CALIBRATE` defaults to scan

`std.macros/homing.cfg` wraps `BED_MESH_CALIBRATE`
(`rename_existing: BED_MESH_CALIBRATE_BASE`) the same way as
`QUAD_GANTRY_LEVEL`. On an eddy machine a bare call first probes the bed surface
once at `zero_reference_position` (`_ZERO_REF_PROBE` compensates
`x_offset`/`y_offset` itself), then scans at `bed_z + descend_z`. The reason
matches QGL: scan mode runs at an absolute Z and an eddy out-of-range error is
raised only after every point has been probed, so the height must be measured
rather than the static `2.5`. `descend_z` comes from
`[probe_eddy_current <name>]`, and the guard aborts the run when the surface is
further than `MAX_ZERO_DEV` (0.5 mm) from zero.

Wrapper rules:

- a call with `METHOD=...` (for example `METHOD=automatic`) goes straight to
  Klipper as a single pass: the operator then owns the method and the height;
- a physical `[probe]` (the `voron-t` machine) always takes the pass-through
  branch: it has no scan mode;
- an explicit `HORIZONTAL_MOVE_Z=` overrides the calculated value: `{rawparams}`
  comes last and Klipper keeps the last value of a repeated option;
- the wrapper is deliberately not put behind `_PROBE_TEMP_GUARD` (a mesh is
  taken hot); `[temperature_probe fly_eddy_probe]` compensates the drift.

The QGL scan height is derived the same way - `measured Z + descend_z` from the
check `PROBE`. If `BED_MESH_CALIBRATE` is called with an explicit `METHOD=scan`,
`HORIZONTAL_MOVE_Z=<descend_z>` (2.5) is still passed by hand: the `calibrate`
table covers only its own range, and the default 5 mm of `bed_mesh` and 10 mm of
QGL fall outside it - `probe_eddy_current sensor not in valid range`. Do not
lower `horizontal_move_z` in the sections to 2.5: in `automatic` (descend) mode
probing starts at that height and would hit `descend_z` immediately.
`rapid_scan` is not recommended: it is less accurate, and in
`scan`/`rapid_scan` a sensor error is raised only after all points have been
probed - which is exactly why the rough descend pass runs before the fine one.

The full zero calibration cycle (the `_QGL_FINE` guard now prints it in full):
`Z_ENDSTOP_CALIBRATE` + `SAVE_CONFIG`, then `PROBE` →
`SET_GCODE_OFFSET Z=<minus the reading>` → `Z_OFFSET_APPLY_PROBE` →
`SAVE_CONFIG`. The `SET_GCODE_OFFSET` step is mandatory: without an active
gcode offset `Z_OFFSET_APPLY_PROBE` answers `Nothing to do: Z Offset is 0`.

Consistency check of the two Z=0 references: after `G28 Z` the `PROBE` command
at the bed centre must read about 0 (+/- 0.02 mm); a difference means one of
the calibrations is wrong.

The committed `v24-350` profile already enables the hybrid
(`features=...,eddy_f`, the override lives in its `machine-extras.cfg`); until
it is calibrated on the bench `position_endstop: -0.520` is the profile default. The
requirements match plain `eddy_f`: a current Klipper with
`descend_z`, and the EDDY-F harness connected only with the board powered off.

### Validator checks

`check_config.py` emulates Klipper's config reader and additionally verifies MCU
references against the original option text:

- **ERROR** — a pin prefix `NAME:` (`^NAME:PIN`, `NAME:PIN`), `mcu:` in
  `[board_pins]` or `sensor_mcu:` in `[temperature_sensor]` that names an MCU
  without a `[mcu NAME]` section (virtual `*_virtual_endstop` pins are ignored).
- **ERROR** — `[probe]` next to a `probe_eddy_current*` section: Klipper
  registers both objects as `probe` and aborts with
  `Registering duplicate object 'probe'`. The check also catches a `[probe]`
  returning to a board file, which the config parser merges silently.
- **ERROR** — `[stepper_z]` has a physical `endstop_pin` (not `probe:...`) but
  no `position_endstop`: Klipper requires it for a hardware Z endstop. The
  opposite mistake is caught too: `position_endstop` next to
  `probe:z_virtual_endstop`, which Klipper never reads and rejects with
  `Option 'position_endstop' is not valid in section 'stepper_z'`.
- **ERROR** — a point to which Klipper does not apply the probe offset
  (`quad_gantry_level points`, `z_tilt points`, `resonance_tester
  probe_points`) puts the coil at `point + (x_offset, y_offset)` outside the
  axis limits. The message prints the ready coil coordinates; `points` must be
  written as "bed point - offset".
- **ERROR** — `bed_mesh` is checked against two boundary sets:
  `mesh_min`/`mesh_max` are the coil positions and must lie on the bed, while
  `mesh - offset` is the nozzle position and must stay inside
  `position_min/position_max`. Only the second set was checked before.
- **WARNING** — nonzero `x_offset`/`y_offset` together with
  `quad_gantry_level`/`z_tilt`: a reminder that the anchors are written as
  "bed point - offset".
- **NOTICE** — the mesh is smaller than 0.8 of the reachable area: prints the
  calculated `mesh_min`/`mesh_max`/`probe_count` using
  `max(position_min + offset + 2, edge)` /
  `min(position_max + offset, bed - edge)` with a coil `edge` of 12 mm.
- **WARNING** — `[mcu NAME]` is declared but nothing references it, which
  signals an orphaned section from a board the machine does not have. The
  implicit `mcu` and `host` never produce this warning.
- **ERROR** — an active `stealthchop_threshold >= 1000` in any `[tmc*]`
  section: Klipper switches to StealthChop and the chopper registers do nothing.
  The message contains a ready `tmc_calc.py --update-module … --mode spreadcycle`
  command.
- **WARNING** — a `[tmc*]` section has no `stealthchop_threshold`: Klipper uses
  SpreadCycle by default, but the fleet invariant wants an explicit `0`. The
  audit walks all of `std.configs/**` and `printers/*/local/**`, so
  `boards/fly-sb2040.cfg` (unreachable from `machine.conf`) is covered too.
- **ERROR** — a `driver_*` option the module of that family never reads
  (`driver_THIGH` is the common one): Klipper aborts startup with
  `Option 'driver_THIGH' is not valid in section 'tmc5160 stepper_x'`. The
  legal list comes from `DRIVER_KEYS` in `tmc_calc.py` with no second copy; the
  full-step threshold is the first-class `high_velocity_threshold` in mm/s,
  from which Klipper computes `THIGH`. Families without a table
  (`[tmc2109 …]`) are skipped, not guessed.
- **ERROR** — `driver_VHIGHFS: 1` without a positive
  `high_velocity_threshold`: `THIGH` stays `0`, meaning "threshold exceeded at
  any speed", so every move runs in full step (0.2 mm per full step on a
  40 mm / 200-step axis) and probing/mesh data gets quantized. The message asks
  for a threshold above `[bed_mesh] speed`.
- **WARNING** — `driver_VHIGHCHM: 1` without a positive
  `high_velocity_threshold`: the driver sits in the high-velocity chopper mode
  permanently; upstream `docs/TMC_Drivers.md` calls such a mode change at low
  speed "poor and confusing".
- **NOTICE** — `high_velocity_threshold` is set but neither `driver_VHIGHFS`
  nor `driver_VHIGHCHM` is enabled: `THIGH` has no effect.
- **ERROR** — `--jinja-lint`: a `[gcode_macro]` body in `std.macros/` or
  `printers/*/macros.cfg` does not parse as Jinja with Klipper's delimiters
  (`{% %}` blocks, `{ }` output), i.e. Klipper would refuse to load the config.
  Requires `jinja2` (`~/klippy-env/bin/python` has it); a system `python3`
  without the module reports a clear error instead of skipping silently.

### Repository layout

```text
vorons_configs/
├── printers/
│   └── voron-t/
│       ├── machine.conf        # machine axes and features (single source of choice)
│       ├── profile.cfg         # GENERATED from machine.conf, committed
│       ├── printer.cfg         # head-managed: includes + autosave at the end
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
├── docs/tmc/                   # Trinamic/ADI calculators, CALCS.md, motors.json (NOT deployed)
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
- **seed** — created only when missing: `KlipperScreen.conf`, `crowsnest.conf`,
  `sonar.conf`, `telegram.conf`.
- **`printer.cfg` is partially managed.** Every deploy replaces everything above
  the `#*# <---------------------- SAVE_CONFIG ---------------------->` marker
  with the copy from `printers/<id>/printer.cfg` and keeps the marker and the
  autosave block below it verbatim (`scripts/merge_printer_cfg.py`). A head option
  that the autosave also defines is commented out: Klipper gives the regular
  config priority, so an active head value would shadow the calibration. With `-b`
  the previous version moves to `DEST/.backup/<ts>/`.
- **`.deployed_profile`** — a state dotfile in `DEST` with the id of the last
  profile that was actually deployed. `scripts/moonraker_update.sh` reads it
  after the repository is updated. After writing the files, the deploy
  idempotently normalizes the `[update_manager vorons_configs]` entry in
  `moonraker.conf` (`scripts/lib/moonraker_conf.py`); prune never touches the
  dotfiles and `--check` does not involve them. Next to it,
  `.deployed_commit` records the commit the hook already deployed and restarted
  Klipper for (the timer uses it to skip repeated work).
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

The wizard generates `machine.conf` from the canonical
`scripts/templates/machine.conf.template` (Russian comments for every key),
creates a `printer.cfg` with defaults, a TODO `anchors.cfg`, `machine-extras.cfg`,
`macros.cfg`, `moonraker.conf`, `local/`, renders `profile.cfg` and validates the
profile. The X/Y and Z pairs default to the fleet/archetype rule and can be
overridden with `--xy-motor`, `--xy-driver`, `--z-driver`, `--z-motor`,
`--e-motor`. On an interactive terminal it asks for the feature list (or accepts
`--features`); `belay`/`btt_sfs` without `extra_extruder` are rejected. Next,
fill `local/uuids.cfg` and the measured anchors. The step-by-step guide and the
key table are in [`docs/PROFILES.md`](docs/PROFILES.md) (Russian). Before the
first calibration, check the CAN host: `ip -details link show can0` must report
`qlen 1024`, and `systemctl status ifup@can0` must not show `status=1/FAILURE`
(see "Known Klipper patches and CAN host setup").

### Scripts

| Script | Purpose |
|---|---|
| `scripts/deploy_configs.sh -p <profile>` | deploy; `--render`, `--check`, `--matrix` (full/lite, per board), `--axis K=V`, `-n`, `-b`, `-d`, `--no-prune` |
| `scripts/render_profile.py --machine-dir <profile> [--write]` | render `profile.cfg` from `machine.conf` |
| `scripts/check_config.py` | offline parser: `--config-dir`, `--merged`, `--machine`, `--stale-check`, `--jinja-lint` (needs `jinja2`) |
| `scripts/collect_local.sh -p <profile>` | `std.config.local/*.cfg` → profile + autosave snapshot |
| `scripts/new_machine.sh` | profile creation wizard (features, UUID template) |
| `scripts/build_mcu.sh -c <config> [--src DIR] [-o out] [--clean] [-j N] [--print-bin]` | build `klipper.bin`, `katapult.bin` or `klipper.elf` |
| `scripts/flash_mcu.sh [can\|bridge\|query\|serial\|dfu\|linux] ...` | flash one controller |
| `scripts/update_firmware.sh [-p profile] [--dry-run] [--auto]` | rebuild and flash all MCUs after a Klipper update |
| `scripts/install_update_hook.sh [--profile profile] [--dry-run]` | install the systemd path/timer hook (needs sudo) |
| `scripts/moonraker_update.sh [-p profile] [-d DEST] [-n] [-a]` | deploy after a repository update: profile, section ensure; `--auto` adds the commit stamp and the Klipper restart |
| `scripts/install_config_update_hook.sh [--dry-run] [--uninstall]` | systemd path/timer that runs `moonraker_update.sh --auto` (needs sudo) |
| `scripts/lib/moonraker_conf.py ensure --config <file>` | idempotent canonical `[update_manager vorons_configs]` entry; `selftest` |
| `scripts/tmc_calc.py --driver tmc2209\|tmc5160 ...` | TMC settings from a motor datasheet: `--write`, `--update-module`, `--wire-profile`, `--json`, `--selftest` |
| `scripts/tmc_tune.py --profile printers/<id> --run` | finds `max_velocity`/`max_accel` with `TEST_SPEED`; `--z-test` finds `max_z_velocity`/`max_z_accel` with `TEST_SPEED_Z`: `--dry-plan`, `--apply`, `--heat`, `--z-offline-result`, `--selftest` |
| `scripts/bringup.sh -p <profile>` | first-run setup: `deploy → tmc → motion → z-motion → pid-e → pid-b → done`, resume with `--from`, plan with `--dry-run` |
| `scripts/lib/bringup_api.py` | stdlib Moonraker client: `info`, `status`, `query`, `gcode`, `store`, `restart`, `wait-ready`, `wait-marker`, `verify-hold` |

### TMC settings: `docs/tmc/` and `scripts/tmc_calc.py`

`docs/tmc/` is never deployed (only `std.configs/**`, `std.macros/**` and the
profile files are copied) and holds:

- `TMC2209_Calculations.xlsx`, `TMC5160_Calculations.xlsx` — vendor Trinamic/ADI
  calculators; URLs, date and sha256 are in `docs/tmc/SOURCES.md`;
- `CALCS.md` — the "sheet/cell → formula → script function" map; project rule:
  a formula is documented there before it lands in the script;
- `motors.json` — fleet motor data, every entry requires a datasheet `source`.

`scripts/tmc_calc.py` picks `run_current` and the chopper settings and, by
default, only prints the resulting stanza:

```bash
# motor from the database: recommended current and registers
python3 scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24

# custom motor (current, L and R from the datasheet), several sections
python3 scripts/tmc_calc.py --driver tmc2209 --i-rated 1.7 --l-mh 2.8 \
    --r-ohm 1.5 --vm 24 --section stepper_z --section stepper_z1

# StealthChop instead of SpreadCycle; PWM_OFS/GRAD from PWM_AUTO after autotuning
python3 scripts/tmc_calc.py --driver tmc5160 --motor LDO-42STH48-2804AH-R \
    --vm 48 --mode stealthchop --pwm-ofs 30 --pwm-grad 14

# write the module and set the xy_driver+xy_motor pair in the profile
python3 scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 24 \
    --write manta-m5p/xy-tmc5160-17HM19-1684.cfg --wire-profile printers/voron-t

# recompute an existing module in place (nominal current, --force writes it)
python3 scripts/tmc_calc.py --update-module \
    std.configs/mechanics/tmc/3z-tmc2109-17hs4401s.cfg \
    --vm 24 --motor 17HS4401S --current-basis peak --i-factor 1.0 --force
```

Script rules:

- only `driver_*` keys from a whitelist checked against the installed Klipper are
  printed (`driver_TPFD` exists on TMC5160 only);
- current registers (`CS`/`IRUN`, `GLOBALSCALER`) never appear in the config:
  Klipper derives them from `run_current`, the output shows them for cross-check
  only;
- `run_current = min(rating × --i-factor, IC limit)`; for X/Y and Z the
  datasheet rating is passed as `--current-basis peak` and converted to RMS by
  dividing by sqrt(2) (0.707 x peak), while the extruders use the RMS default.
  A motor whose rating is above the IC limit (e.g. 1.68 A RMS on a TMC2209 with
  a 0.110 Ohm shunt) is refused with exit status 2;
- `--write` only writes inside `std.configs/mechanics/tmc/` and refuses to
  overwrite without `--force`;
- `--wire-profile` checks the profile `xy_step` (a 1.8 degree motor cannot be
  wired into an `xy_step=0.9` machine) and that the pair exists in both board
  families, writes `xy_driver` and `xy_motor` as two lines in `machine.conf`
  and re-renders `profile.cfg`; then run
  `./scripts/deploy_configs.sh -p <profile> --check`;
- `--update-module FILE [--sections a,b]` recomputes an **existing** file:
  `run_current`, `stealthchop_threshold` and (in SpreadCycle)
  `driver_TBL/TOFF/HSTRT/HEND`. Pins, transport (`uart_pin`/`cs_pin`/`spi_*`),
  `sense_resistor`, hand-written `driver_*` outside the computed set and the
  option order are preserved. Alternative comments (`#run_current: …`) are left
  alone and a marked calculation block is added on top and rewritten on the next
  run. Without `--force` a diff is printed and nothing is written. The chopper
  mode comes from the section (`stealthchop_threshold >= 1000` means
  StealthChop); `--mode` overrides it. It also works on
  `std.configs/extruder/main.cfg` and `std.configs/extra-extruder.cfg`, which is
  why the extruder needs `e_motor` in `machine.conf`;
- `motors.json` also holds a `motor_by_module` table (module name → motor), a
  reverse table for module names; `bringup.sh` reads `xy_motor`/`z_motor`/`e_motor`;
  it is
  what `bringup.sh` uses to resolve the Z and X/Y motors. The fleet extruder
  entry is `MOONS-CSE14HRA1L410A-01` (NEMA14, 1.0 A, 1.9 Ohm, 1.41 mH, HGX 8T);
- `3z-tmc2109-17hs4401s.cfg` is historically named `2109` but contains
  `[tmc2209 …]` sections; the name is not changed (`mechanics/trident.cfg`
  includes it), only its contents are edited;
- `--selftest` compares the formulas with the saved xlsx (±1 LSB) and runs the
  doctest plus the offline `--update-module` cases.

#### Chopper inputs and the SpreadCycle invariant

- `TBL`/`TOFF` are inputs of the calculation (§3 of `CALCS.md`), not its result.
  They live in `machine.conf` as one pair per axis group: `xy_tbl/xy_toff`,
  `z_tbl/z_toff`, `e_tbl/e_toff` (default `0`/`3`; TBL=0 on every fleet
  motor). `render_profile.py` checks the ranges (TBL `0..3`, TOFF
  `1..15`), and `tmc_calc.py` reports the value source (`cli|module|profile`).
- Every fleet driver runs SpreadCycle with an explicit
  `stealthchop_threshold: 0`. X/Y and the extruders already did (in Klipper a
  missing key means SpreadCycle); the invariant now enforces it:
  `check_config.py` raises ERROR for an active threshold ≥ 1000 and WARNING for
  a missing key, and the audit walks all of `std.configs/**` and
  `printers/*/local/**`, including `boards/fly-sb2040.cfg`, which no
  `machine.conf` can reach. `bringup_tmc.py` refuses a StealthChop section
  instead of silently dropping the chopper registers.
- The full-step switch on speed is configured **only** through
  `high_velocity_threshold` (mm/s): `tmc.TMCVhighHelper` computes
  `THIGH = fCLK · rotation_distance / (full_steps_per_rotation · 256) / v`
  (for v24-350 that is `9375 / v`, so 700 mm/s gives `THIGH=13`). Klipper has
  no `driver_THIGH` option - that is a startup error, caught by
  `check_config.py`. `driver_VHIGHFS`/`driver_VHIGHCHM` are legal `CHOPCONF`
  bits (18 and 19), but without a positive threshold they turn on full step
  (FS) or the high-velocity chopper (CHM) permanently; the threshold must stay
  above the fastest measuring move (`[bed_mesh] speed`).
- The full-step switch was tested on the v24-350 bench (2026-11-22) and is
  **not applied**. The mechanism is confirmed: `thigh` with `VELOCITY=500`
  gives `THIGH=19`, the `vhighfs`/`vhighchm` bits show up in `CHOPCONF`, and
  `fsactive=1` appeared in 9 of 11 `DRV_STATUS` samples taken during motion
  and in none of the 11 standstill samples. At microsteps 64, however, the
  baseline already passes 750/8500, 900/9000 and 900/10000 without loss (3/3,
  `|Δ| ≤ 35` MCU counts, one full step is 64) and the CHM-only variant is
  equally clean (9/9, `|Δ| ≤ 31`); the gate requires a baseline failure that
  does not exist. The C/D variants were cut short by the `extruder` toolhead
  MCU dropping out (6288 `rx_error` and 6333 `tx_retries` within one second,
  then `Timeout on connect`; the bus and the USB-CAN bridge stayed alive). The
  cause was found: the CAN/power connector on the SHT36 came loose during the
  high-speed runs, and the C/D series was repeated after it was re-seated:
  C 9/9 clean (`|Δ| ≤ 10`), D 9/9 apart from one 750/8500 run with a +515
  count shift on one motor - the same rare ~8-full-step event seen in the
  baseline, with no CAN errors in that window. Speeds above 1000 mm/s were
  checked separately: 1000-1200 mm/s at accel 8500 pass without loss in both
  the baseline and the full-step configuration, while 1100/10000 loses ~8 full
  steps in both, so there is no gain. The pattern itself keeps its steps: a
  diagnostic that parked at Z=30 on both sides reported `0/0` for the pattern,
  and the drift appeared only after the final `G28`, i.e. the homing reference
  shifts (gantry/belts), not the path. The
  data and the conclusion live in `printers/v24-350/machine-extras.cfg`.
  Hand-set bits can only be cleared by a Klipper restart: `INIT_TMC` writes
  the cached field values back.
- `klipper_tmc_autotune` (`andrewmcgr`, GPL-3.0) is **not adopted**. It is a
  runtime override: on `klippy:ready` and on `AUTOTUNE_TMC` it recalculates
  CHOPCONF, PWMCONF, COOLCONF, TPWMTHRS, TCOOLTHRS and THIGH over the config,
  so the `tmc_calc.py` catalog modules and the hardware silently diverge. For
  Z and the extruder the `auto` target enables StealthChop (clears `CHM`),
  requires `interpolate: true` and turns on CoolStep (`semin=2, semax=4`) -
  direct conflicts with `stealthchop_threshold: 0`, `interpolate: false` and
  the "no COOLCONF" invariant. Finally, the module itself keeps
  `VHIGHFS = VHIGHCHM = False` and derives the FS threshold from
  `1.2 × vmaxpwm` of StealthChop, which does not apply to the SpreadCycle
  fleet. Only `motor_database.cfg` is useful, as a second source of constants:
  `ldo-42sth48-2804ah` = 0.7 Ohm / 0.6 mH / 2.8 A / 0.42 Nm matches
  `docs/tmc/motors.json`, so the fleet motor is renamed to
  `LDO-42STH48-2804AH-R` with no current recalculation. No autotune code is
  copied into this repository (GPL-3.0), only facts and the reference.
- The +50 % envelope over the applied 750/8500 (1125 mm/s, 12750 mm/s^2) was
  measured on the v24-350 bench on 2026-11-23 on the pure baseline (A:
  `thigh=0`, both bits 0, no VHIGH options). The 1125/12750 cell passed 3/3
  (`|Δ| ≤ 7` MCU counts, one full step is 64), but 1000/12750 failed 2/3,
  1125/8500 failed 1/3 and 1125/10000 failed 3/3 (`|Δ|` up to 505); the
  failures are not monotonic in acceleration. A `diag4` run that parked at
  Z=30 on the failing cells reported `patterns 0/0` every time and a `rehome`
  shift of ±512 counts (8 full steps): the homing reference moves after the
  run, the pattern itself keeps its steps. `LOST_STEPS` stayed 0, the TMC
  temperature was 54.9-56.0 C, and the toolhead MCU stayed `bus_state=active`
  with no `rx_error`/`tx_error` (only the cumulative `tx_retries` grew). The
  `[printer] 750/8500` limits therefore stay: the 15 % margin rule is taken
  from a monotonically passed cell, and there is none above 1125/8500.
- X/Y with **128 microsteps** were run through the same +50 % series
  (2026-11-23, baseline A, no VHIGH): 1000/12750, 1125/8500 and 1125/12750
  passed 3/3, 1125/10000 passed 1/3 (`dy` ≈ -507 counts). `diag4` on
  1125/10000 gives `patterns 0/0` and a re-home shift of up to 1535 counts
  (2.4 mm): the limit is the homing reference, not the step resolution. 128
  microsteps is 640 steps/mm, so 1125 mm/s is 720 kHz per motor; the Manta
  M8P accepted it with no `Timer too close`. The applied default stays
  **64**: 1125/10000 does not pass, and 64 already has a long thermal and
  print-quality history. The Y driver now enables `diag1_pin: DIAG_1` by
  default in the LDO modules (matching `DIAG_0` on X); `CHOPCONF` is
  unaffected.
- A +15 % ladder up to 1500/15000 was measured on the v24-350 bench
  (2026-11-23) on the same pure baseline, 3 repeats per cell, against a
  0.1 mm criterion (32 counts at 64 microsteps, 64 at 128). At 64 only the
  starting 750/8500 holds the criterion; at 128 it holds contiguously up to
  992/11241; 1141/12927 fails both series while the cells above are clean
  again, so the failures are not monotonic. `diag4` on every failing cell
  gives `patterns 0/0` and moves the whole drift into `rehome` (up to 2544
  counts = 4.0 mm at 128): the homing reference moves again, the pattern
  keeps its steps. 1500 mm/s at 128 is 960 kHz per motor and the Manta M8P
  handled it with no `Timer too close`/`Stepper move too late`. `LOST_STEPS`
  stayed 0, CAN had no `rx_error`/`tx_error`. The applied 750/8500 and 64
  microsteps stay; the 15 % margin rule is taken from the highest monotonic
  cell <= 0.1 mm.
- X/Y and Z are recalculated from the datasheet peak into RMS
  (`--current-basis peak`, `I_RMS = I_peak / √2 ≈ 0.707 · I_peak`): LDO
  2.8 A peak → 1.9799 A RMS, 17HM19 1.68 A peak → 1.1879 A RMS, Z 17HS4401S
  1.7 A peak → 1.2021 A RMS, Z 17HS19-2004S1 2.0 A peak → 1.4142 A RMS
  (`driver_HSTRT: 0`, `driver_HEND: 0`). The
  extruders keep their actual 0.55/0.60 A RMS: the calculation uses those
  currents (`--run-current`), not the motor's 1.0 A rating.

`--run-current A` sets `run_current` directly; `i_factor` is derived from it and
printed as `i_factor_effective`. `--i-factor 0.8` remains a starting point for
manual runs; in the fleet X/Y and Z are recalculated at the rating
(`--i-factor 1.0 --current-basis peak`), and the extruders at 0.55/0.60 A RMS.
The historical 0.951/1.697/0.600 A values came from thermal testing and are
marked as outdated in §8 of `docs/tmc/CALCS.md`. On the LDO at 1.98 A the
calculation reports `HystStart > 20` (TBL is already 0): that follows from
48/55 V and L = 0.6 mH, and the warning is informational.

### Machine commissioning: `scripts/bringup.sh`

One run per new machine: **deploy → tmc → motion → z-motion → pid-e → pid-b → done**.
The script orchestrates the existing tools and does not duplicate their logic.

```bash
cd ~/vorons_configs
./scripts/bringup.sh -p voron-t --dry-run     # plan only, no commands
./scripts/bringup.sh -p voron-t               # full run, operator at the machine
./scripts/bringup.sh -p voron-t --from pid-e  # resume after an interruption
./scripts/bringup.sh -p voron-t --only tmc    # a single stage
```

| Stage | What it does |
|---|---|
| `deploy` | `deploy_configs.sh -p <id> -b`, then `POST /machine/restart` (on Moonraker v0.10 `/machine/services/restart`) and wait for `ready` (60 s) |
| `tmc` | `check_config.py --merged` gives the live `[tmc*]` list; each section gets its motor (`xy_motor` / `z_motor` / `e_motor`) and rail (`vm_xy` for X/Y, `vm_ze` for Z/E), `tmc_calc.py --update-module` rewrites current and chopper, then deploy + restart |
| `motion` | `tmc_tune.py --run --apply --iterations 2`: `TEST_SPEED` ladder, verdict from `GET_POSITION`, bisection, pair written to `machine-extras.cfg`; needs operator confirmation |
| `z-motion` | `tmc_tune.py --run --apply --z-test --iterations 2`: `max_z_velocity`/`max_z_accel` ladder; per candidate it writes `std.config.local/z_speed_test.cfg`, restarts, re-applies the TMC settings, homes, levels the gantry and runs `TEST_SPEED_Z`; a Z skew aborts the series; needs operator confirmation |
| `pid-e` | `PID_CALIBRATE HEATER=extruder TARGET=250`, parse `pid_Kp/Ki/Kd` from `gcode_store`, patch `printers/<id>/local/pid.cfg`, deploy + restart, verify 30 s of hold (±1.5 °C) |
| `pid-b` | same for `heater_bed` at 120 °C |
| `done` | `git diff --stat` summary and a suggested commit message |

S0 gates (a run does not start without them): clean `git status` of the clone
(the rollback target), valid `machine.conf` and a fresh `profile.cfg`, green
`deploy_configs.sh --check`, `std.config.local/uuids.cfg` without
`REPLACE_WITH_`, `anchors.cfg` without `TODO` for the `motion`/`z-motion` stages; Moonraker:
Klipper `ready`, no active print, heaters < 45 °C.

Notes:

- `SAVE_CONFIG` is not used: PID values are committed to git, deployed and
  applied by a Klipper restart;
- `z-motion` finds `max_z_velocity`/`max_z_accel` with `TEST_SPEED_Z`: every
  candidate writes `std.config.local/z_speed_test.cfg`, restarts Klipper,
  re-applies the TMC settings (a restart drops `SET_TMC_*`), homes (`G28`),
  levels the gantry (`QUAD_GANTRY_LEVEL` or `Z_TILT_ADJUST`) and runs the
  macro. The corridor keeps the nozzle at or above `--z-floor` (40 mm) and
  5 mm below the top of the axis; a spread between the Z motors larger than one
  full step aborts the series and requires `G28` + leveling. After the test,
  `G28` and leveling are mandatory: the bench `position_endstop` is a
  placeholder, so `z_offset` stays invalid until it is calibrated by hand;
- the extruders stay at their actual 0.55 A (`extruder`) and 0.60 A
  (`ext-extruder`) with `e_tbl=0`; the calculated `HSTRT/HEND` (7/4 and 7/5)
  give finer current regulation than the upstream 7/6. The `HystStart > 20`
  warning is no longer expected at a 1.0 A rating: the current is not raised and
  `TBL=0` keeps the hysteresis in range;
- the state file (`~/printer_data/.bringup/<id>.json`) keeps the last stage,
  the repository HEAD and a run log; resume with `--from`;
- a partial run leaves the clone modified: commit the result (or
  `git checkout .`) before the next run, as required by the cleanliness gate;
- rollback: `git -C ~/vorons_configs checkout . &&
  ./scripts/deploy_configs.sh -p <id> -b` and restart Klipper; committing,
  pushing and tagging are the owner's steps, `bringup.sh` never does them;
- the 350 bed at 120 °C is close to `max_temp: 145`; `verify_heater` aborts a
  runaway and the stage then fails with the heaters switched off.

Hardware-free checks:

```bash
./scripts/bringup.sh -p voron-t --dry-run
./scripts/bringup.sh -p v24-350 --dry-run
python3 scripts/lib/bringup_api.py selftest
python3 scripts/lib/bringup_state.py selftest
python3 scripts/lib/bringup_pid.py selftest
python3 scripts/lib/bringup_tmc.py selftest
python3 scripts/tmc_tune.py --selftest
python3 scripts/tmc_tune.py --profile printers/v24-350 --z-test --dry-plan
python3 scripts/tmc_calc.py --selftest
```

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

### Automatic config updates through Moonraker

`[update_manager vorons_configs]` in `moonraker.conf` only pulls this
repository: Moonraker never executes `install_script` (the legacy option is
read for `PKGLIST` only), so a separate systemd hook starts the deploy.
`scripts/install_config_update_hook.sh` installs
`klipper-configs-deploy.path` (watches the checkout's `.git/HEAD`,
`.git/FETCH_HEAD` and `.git/refs/heads`) and `klipper-configs-deploy.timer`
(retries every 10 minutes); both run `scripts/moonraker_update.sh --auto` as
the printer user without sudo.

The hook:

1. detects the profile from the `~/printer_data/config/.deployed_profile`
   marker written by `deploy_configs.sh` on a real deploy; without a marker it
   compares the live `machine.conf` byte by byte with each profile's render
   (`render_profile.py --dump-conf`, which is what deploy writes) and fails when
   there is no match or more than one;
2. in `--auto` mode it skips the work when `DEST/.deployed_commit` already
   equals the current `HEAD` (a timer retry becomes a no-op);
3. deploys the profile (`deploy_configs.sh -p <id> -b`); the built-in gate
   refuses to write while a print is running;
4. idempotently normalizes the `[update_manager vorons_configs]` entry in the
   live `moonraker.conf` (`scripts/lib/moonraker_conf.py`) and warns when it had
   to change it: restarting Moonraker stays manual, otherwise the hook would
   kill itself;
5. restarts Klipper through the Moonraker API (the entry does not use
   `managed_services`: Moonraker would restart Klipper before the deploy
   finishes) and writes the short commit to `DEST/.deployed_commit`;
6. prints a summary (profile, short commit, result).

Any deploy or restart failure exits non-zero and the timer retries; the stamp is
not updated until the restart succeeds, so Klipper never stays on the old
config after a successful run. A manual run without `--auto` deploys and stamps
but does not restart Klipper (the hook prints a reminder).

Bootstrap (once per machine):

```bash
sudo scripts/install_config_update_hook.sh       # path + timer units (needs sudo)
./scripts/deploy_configs.sh -p <profile> -b      # marker + moonraker.conf
sudo systemctl restart moonraker                 # once, to reread the update entry
```

After that use "Update" in Mainsail or `POST /machine/update/full`: Moonraker
pulls, the path unit sees the new commit, the hook deploys the configs and
restarts Klipper. Moonraker refuses to update a dirty clone (non-empty `git status`), so the automatic
deploy does not run: that is normal `update_manager` behavior, commit or discard
the changes first.

### Secrets

- Never commit a real `bot_token`/`chat_id` in `telegram.conf`; the repository keeps a
  placeholder.
- The repository is private; `local/` (UUIDs, PID, input shaper) is committed deliberately.
- `KlipperScreen.conf` contains a generated `#~#` block, which is why it is a seed file.

### Fleet host access

- Host passwords are stored locally only: `secrets/hosts.env` (the directory is
  gitignored, the file is `chmod 600`). The repository carries the
  `secrets/hosts.env.example` template without values. Values must be
  double-quoted: the file is loaded with `set -a; . secrets/hosts.env`, so an
  unquoted password containing `$`, a backtick, `#`, `!` or a space would be
  expanded or truncated by the shell.
- v24-350 bench: `V24_350_HOST=192.168.52.30`, `V24_350_SSH_USER`,
  `V24_350_SSH_PASS`. Login uses an SSH key (`ssh-copy-id` once); the password
  is only needed to install the key and for `sudo`.
- The password must never enter argv or shell history: pass it through the
  environment (`sshpass -e` with `SSHPASS`) or a pty wrapper that reads
  `secrets/hosts.env` itself. `sshpass` may be missing on the machine, in which
  case the wrapper is the only option.
- Leak check after commits: `git status --short` does not list `secrets/`
  (except `hosts.env.example`), and a history search (`git log -p`) does not
  find the password.

### Input shaper calibration (Measuring Resonances)

Klipper's [Measuring Resonances](https://www.klipper3d.org/Measuring_Resonances.html)
procedure on a live bench. The result goes into
`printers/<id>/local/input.shaper.cfg` and is committed: the repository stays
the source of truth and `SAVE_CONFIG` is not used.

Prerequisites:

- `numpy` is installed in `klippy-env`, otherwise `MEASURE_AXES_NOISE` and
  `TEST_RESONANCES` fail with `Failed to import numpy module`:
  `~/klippy-env/bin/pip install numpy`;
- the accelerometer is mounted on the toolhead, the bed and nozzle are clear,
  and the firmware carries the trsync patch (see "Known Klipper patches");
- graphs are rendered on the workstation, not on the host:
  `~/klipper/scripts/calibrate_shaper.py` and `graph_accelerometer.py` need
  `numpy`, `scipy` and `matplotlib`.

```bash
API="python3 ~/vorons_configs/scripts/lib/bringup_api.py"
$API gcode G28
$API --timeout 580 gcode QUAD_GANTRY_LEVEL        # the gantry must be level
$API --timeout 120 gcode MEASURE_AXES_NOISE      # lis2dw target: < 10
$API --timeout 880 gcode 'TEST_RESONANCES AXIS=X'   # ~6 min
$API --timeout 880 gcode 'TEST_RESONANCES AXIS=Y'
# the CSV lands on the host in /tmp/resonances_<axis>_<date>.csv
scp spectre@<host>:/tmp/resonances_x_*.csv .
python3 calibrate_shaper.py -o shaper_x.png resonances_x_*.csv
```

The order matters: `G28` already runs QGL in this profile, but an explicit
`QUAD_GANTRY_LEVEL` right before the measurement is mandatory. On the v24-350
bench a gantry skew of almost 2 mm smeared the Y peak (FWHM 7.8 → 9.4 Hz, the
vertical shoulder moved to 60–65 Hz) and the frequency wandered over
33.5–37.3 Hz; after QGL down to 0.0085 mm the peak became single and sharp.

Never start the second axis while the first test is running: the command is
synchronous, so `wait-idle --timeout 900` between them is enough. Look for the
peak in `psd_x` for X and in `psd_y` for Y; `calibrate_shaper.py` picks
`shaper_freq_*` and `shaper_type_*` with residual vibration and smoothing
estimates.

Check the sensor orientation before the first measurement: with the printer
stationary `ACCELEROMETER_QUERY` must report the whole gravity vector in Z
(`z≈+9475 mm/s²` for the lis2dw with `axes_map: -y,z,-x`), a +X move must
respond only in `x`, and a +Y move only in `y`. Otherwise the measurement is
silently written to the wrong axes (this happened on v24-350 with the old
`axes_map: x,z,-y`, which attached the vertical axis to X).

### Known Klipper patches and CAN host setup

These changes are not part of the config repository; they are applied on the
printer host itself. The v24-350 bench runs Klipper `v0.13.0-828` (verified on
2026-11-23): the trsync fix `29d4ec2` is already in its history and `can0` is
up with `qlen 1024`. Both items below stay mandatory for machines on older
builds.

1. **trsync (upstream `29d4ec2`, 2026-11-11).** Without the fix, homing and
   probing can end in `MCU 'mcu' shutdown: Timer too close`: the signed
   `(int64_t)(expire - m->expire_clock) >= m->min_extend_ticks` comparison can
   send the MCU a `trsync_set_timeout` whose clock has already passed.

   ```bash
   git -C ~/klipper cherry-pick --no-commit 29d4ec2d6d840ee839333306003a400da186d41d
   sudo systemctl restart klipper      # chelper rebuilds on start
   ```

   Signs that it is applied: the fresh `klippy.log` shows
   `Building C code module c_helper.so` and
   `Modified files: klippy/chelper/trdispatch.c`. No MCU reflash is needed.

   Important: `cherry-pick --no-commit` keeps the change in the index, so the
   Klipper repository counts as modified (`git describe --dirty` reports
   `-dirty`) and Moonraker refuses to update with
   `Update aborted, repo has been modified`. Update order:

   ```bash
   # 1. drop the local change; `checkout --` does NOT work here — it restores
   #    the index version, which is the patch itself
   git -C ~/klipper restore --staged --worktree klippy/chelper/trdispatch.c
   # 2. update Klipper (Moonraker/Mainsail or git -C ~/klipper pull)
   # 3. verify the fix arrived from upstream
   grep -n "expire >= m->expire_clock" ~/klipper/klippy/chelper/trdispatch.c
   # 4. if the line is missing (master still lacks the fix), re-apply it
   ```

   If the change was committed locally, use `git revert` instead of step 1.

2. **`can0` TX queue depth.** `ifup@can0` must raise `txqueuelen 1024`: with
   the default 10 frames Klipper logs
   `Got error -1 in can write: (105)No buffer space available`, loses
   `trsync_set_timeout` frames and the MCU goes to `Timer too close`. The CB2
   image has no `ifconfig` (net-tools is not installed), so
   `/etc/network/interfaces` must use `ip`, otherwise `ifup@can0` fails with
   exit code 1:

   ```
   iface can0 can static
       bitrate 1000000
       up ip link set dev can0 txqueuelen 1024
   ```

   Check: `ip -details link show can0` reports `qlen 1024`,
   `systemctl status ifup@can0` has no `status=1/FAILURE`, and `klippy.log`
   gains no new `No buffer space available` lines.

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
  parking point / Z=0 is the bed centre 175,175. `G28`,
  `QUAD_GANTRY_LEVEL` and `BED_MESH_CALIBRATE` do run on the bench (2026-11-15:
  three cycles without a shutdown), but the QGL anchors and real limits are
  still not measured, and the probe is noisy — `Probe samples exceed tolerance`
  on almost every point, so QGL takes 230–450 s and a 10x10 mesh about
  20 minutes. The `z_offset` in the shared `probe.cfg` (`-0.400`)
  comes from voron-t and needs recalibration on the bench before the first
  print. The probe input of the whole M8P family moved to `SENS_2` (M3-STOP,
  the connector labelled "Z stop"): `PF2` on V2.0, `PF5` on V1.x; the reference
  M4-STOP/PF1 (V2.0) and PC0 (V1.x) inputs stay free. The `pin: !SENS_2` line
  itself now lives in `std.configs/probe.cfg` instead of the board files: a
  board file is always included, so a `[probe]` left there registered a second
  probe object in every eddy profile. On the bench the probe must be rewired to
  M3-STOP — if it is still in M4-STOP, `QUERY_PROBE` will not see a trigger and
  `G28 Z` will drive into the bed.
- The v24-350 hybrid (park Z on the switch, QGL and `bed_mesh` on the eddy) is
  enabled in the committed profile and loads on the bench (2026-11-18: `probe`
  is `probe_eddy_current fly_eddy_probe`, `QUERY_ENDSTOPS` reports `stepper_z`,
  the LDC1612 answers at address `43`, and the log has no
  `Registering duplicate object` or `Timer too close`). The eddy `calibrate`
  table is measured on the bench (~277 kHz span, ~1 um of noise at 1-3 mm) and
  stored in the autosave; the switch `position_endstop` lives in the profile's
  `printer.cfg` (profile default above the marker, calibrated value in the autosave).
  The eddy zero is matched to the bed with
  `PROBE` + `Z_OFFSET_APPLY_PROBE`; the QGL/mesh runs and the first layer are
  still with the operator. `check_config.py` now
  catches the two typical mistakes of such a build: `[probe]` together with
  `[probe_eddy_current]`, and a physical `[stepper_z] endstop_pin` without
  `position_endstop`.
- A bare `QUAD_GANTRY_LEVEL` on an eddy machine is now two-pass (rough descend
  + check `PROBE` + fine scan), so it takes longer: this affects `PRINT_START`,
  `TEST_SPEED` (`std.macros/test_speed.cfg`) and `scripts/tmc_tune.py`, which
  call the command without parameters. A single pass is still available with
  any parameter, for example `QUAD_GANTRY_LEVEL RETRY_TOLERANCE=0.015`. On the
  v24-350 bench (2026-11-19) the rough descend converges in about 18 s (0.035 mm
  spread) and the check `PROBE` plus the fine scan take about 22 s (0.004 mm at
  a 0.015 tolerance); an explicit single pass takes about 14 s. The guard no
  longer blocks it: the bench zero is matched and `PROBE` after `G28 Z` leaves a
  residual of about `+0.11` mm (2026-11-21). A bare `BED_MESH_CALIBRATE` on an
  eddy machine is now two-step as well (check `PROBE` + scan at
  `bed_z + descend_z`), and the widened 15x14 mesh on v24-350 is estimated at
  about 8 minutes instead of ~2 for the former 140x140 (the real time is
  measured on the bench).
- voron-t `anchors.cfg` keeps inherited `max_z 105` and `153/156` limits, marked TODO
  until the physical stops are measured. The right triangle side is assumed 245 mm
  from the measured left side.
- The `bed_mesh` margin for sizes other than 150 is no longer the catalog
  `0.3·S`: it follows the reachable-zone formula with the measured probe offset
  (`P` is the bed point under the coil, `edge` the coil margin at the bed edge,
  and 2 mm a reserve on the travel term):
  `mesh_min = max(position_min + offset + 2, edge)`,
  `mesh_max = min(position_max + offset, bed - edge)`. On v24-350 with
  `y_offset: 33` and `edge = 12` this is `mesh_min: 12, 35`,
  `mesh_max: 338, 338`, `probe_count: 15, 14` (~23.3 mm per step, an estimated ~8 min scan
  run). The front boundary is the nozzle travel, the rear and sides the coil
  margin; `Y < 33` cannot be probed physically, so printing there relies on the
  bicubic extrapolation. `edge` is a starting assumption: a systematic slope in
  the last row of `BED_MESH_OUTPUT` is treated by increasing `edge`, and local
  obstacles (clips, magnets) by `faulty_region_N_min/max`.
- The `eddy` branch (`std.configs/sht36-v3.eddy.cfg`, the built-in SHT36 Max V3
  chip) is still disabled: the `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` files
  have not been copied from the donor machine yet. The new `eddy_f` option is
  self-contained and does not need those macros.
- Flashing is validated offline (`--dry-run` plus real builds): CAN/serial/DFU
  need `~/katapult` and `python3-serial` and are run manually from a console.
