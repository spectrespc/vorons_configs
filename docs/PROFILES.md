# Профили принтеров: эталон `machine.conf`

Документ описывает схему v2: как устроен профиль, какие ключи обязательны,
как они проверяются и как создать новый профиль от шаблона до первого деплоя.
Единственный источник выбора железа — `printers/<id>/machine.conf`; всё
остальное (`profile.cfg`, staging при деплое, проверки) выводится из него.

## Слои профиля

```
printers/<id>/
├── machine.conf        # ИСТОЧНИК: оси, драйверы, моторы, рейлы, фичи
├── profile.cfg         # ГЕНЕРИРУЕТСЯ из machine.conf, коммитится
├── printer.cfg         # seed: [include profile.cfg] + autosave SAVE_CONFIG
├── anchors.cfg         # измеренные точки стола/парковки (managed)
├── machine-extras.cfg  # машинные override'ы (managed)
├── macros.cfg          # макросы машины (managed)
├── moonraker.conf      # Moonraker (managed)
└── local/*.cfg         # UUID, PID, input shaper; деплоятся в std.config.local/
```

`render_profile.py` читает `machine.conf` и собирает `profile.cfg` —
детерминированный список `[include ...]` в фиксированном порядке:

1. `macros.cfg`, `std.configs/system.cfg`;
2. плата, плата toolhead, механика `mechanics/<model>.cfg`;
3. **модуль X/Y** `mechanics/tmc/<семейство>/xy-<xy_driver>-<xy_motor>.cfg`;
4. **модуль Z** `mechanics/tmc/<z_count>z-<z_driver>-<z_motor>.cfg`;
5. шаг моторов X/Y и геометрия `geometry/<model>-<size>.cfg`;
6. подсистемы (fans/display/buttons), `probe.cfg` (кроме eddy-фич), стол,
   экструдер;
7. фичи (belay, btt_sfs, runout, extra_extruder, host, y_frame, eddy, eddy_f);
8. `std.macros`, `anchors.cfg`, `machine-extras.cfg`, для v24 — `homing.cfg`.

Модули `mechanics/trident.cfg` и `mechanics/v24.cfg` больше не включают TMC
Z-модули: пара Z задаётся только ключами профиля. Klipper сливает одинаковые
секции (последнее значение выигрывает), поэтому приоритет слоёв такой:
каталог → `anchors.cfg` → `machine-extras.cfg` → `std.config.local/*.cfg`.

## Ключи схемы v2

Для коммитнутого профиля обязательны все ключи, кроме помеченных
«необязательный». Отсутствие обязательного ключа — ошибка с подсказкой на этот
документ.

| Ключ | Допустимые значения | Что проверяется |
| --- | --- | --- |
| `size` | `150`, `200`, `250`, `300`, `350` | `SIZES` в `render_profile.py`; наличие `geometry/<model>-<size>.cfg` |
| `model` | `trident`, `v24` | `MODELS`; выбирает механику и archetype |
| `kinematics` | `corexy` | должен совпадать с `MODEL_PROFILE[model]` |
| `z_count` | `3` (trident), `4` (v24) | должен совпадать с `model` |
| `leveling` | `z_tilt` (trident), `quad_gantry_level` (v24) | должен совпадать с `model` |
| `board` | `manta-m5p`, `manta-m8p`, `manta-m8p-v1.0`, `manta-m8p-v1.1` | `BOARDS`; ревизии M8P различаются только пинами/CAN |
| `xy_step` | `0.9` (только 150), `1.8` | равен `step_angle_deg` мотора `xy_motor` в `docs/tmc/motors.json` |
| `xy_motor` | ключ мотора из `docs/tmc/motors.json` | существует в базе; пара с `xy_driver` есть для обеих семейств плат |
| `xy_driver` | `tmc5160`, `tmc2209` | модуль `.../<семейство>/xy-<driver>-<motor>.cfg` существует для `manta-m5p` **и** `manta-m8p` |
| `z_motor` | ключ мотора из `docs/tmc/motors.json` | существует в базе |
| `z_driver` | `tmc2109` (trident), `tmc2209` (v24) | модуль `<z_count>z-<driver>-<motor>.cfg` существует |
| `e_motor` | ключ мотора из `docs/tmc/motors.json` | существует в базе; драйвер экструдера задан платой toolhead |
| `toolhead` | имя модуля платы, например `sht36-v3` | необязательный; plain-имя и наличие `boards/<toolhead>.cfg` |
| `head` | имя модуля хотэнда, например `HGX.8T` | необязательный; наличие `extruder/heads/<head>.cfg` |
| `vm_xy` | `48`, `55` | `BOARD_VM_XY_MAX`: 48 В на M5P и M8P V1.x, 55 В только на M8P V2.0 |
| `vm_ze` | `24` | всегда 24 В: Z и оба экструдера |
| `frame_w`, `frame_d` | мм | необязательные; положительные; `check_config.py` сверяет с размахом `z_positions` |
| `z_base_measured`, `z_leg_measured` | мм | необязательные (trident); сверяются с `z_positions` из `anchors.cfg` |
| `features` | `fans,display,buttons,belay,btt_sfs,runout,extra_extruder,host,y_frame,eddy,eddy_f` | необязательный; `belay`/`btt_sfs` требуют `extra_extruder`, `fans` требует `host`; `eddy` и `eddy_f` взаимоисключающие, требуют `toolhead=sht36-v3` и убирают `probe.cfg` |

### Правила согласованности

- **Модель — селектор механики.** `model=trident` требует
  `kinematics=corexy`, `z_count=3`, `leveling=z_tilt`;
  `model=v24` — `corexy`, `z_count=4`, `quad_gantry_level`. Свободных
  комбинаций нет: ошибка указывает, какой ключ не совпал.
- **Правило парка для X/Y.** `size=150` → `xy_step=0.9` → мотор
  `17HM19-1684`; остальные размеры → `1.8` → `LDO-42STH48-2804AC`.
  Драйвер парка — `tmc5160`. Значения можно задать явно, но `xy_step` обязан
  совпадать с паспортным шагом мотора, иначе геометрия (`rotation_distance`/
  микрошаг) будет неверной.
- **Пара драйвер/мотор проверяется по файлам.** Для X/Y модуль должен
  существовать в обеих семьях (`manta-m5p`, `manta-m8p`), чтобы одна и та же
  пара была пригодна для всего парка. Для Z модуль один:
  `std.configs/mechanics/tmc/<z_count>z-<driver>-<motor>.cfg`.
  Отсутствующий модуль — ошибка с готовой командой `tmc_calc.py --write`.
- **Рейлы питания.** X/Y питаются от `vm_xy`, Z и оба экструдера — от `vm_ze`
  (всегда 24 В). `vm_xy=55` допустим только на M8P V2.0 с установленной
  HV-перемычкой; таблица `BOARD_VM_XY_MAX` общая для рендера и
  `check_config.py`, поэтому проверки не расходятся.
- **Драйвер экструдера не выбирается ключом.** Он задан платой toolhead
  (`sht36-v3` — TMC2209); `e_motor` задаёт только мотор. Так профиль не может
  разъехаться с железом toolhead. Драйвер виден в resolved-карте заголовка
  `profile.cfg`.
- **eddy-щупы взаимоисключающие.** `eddy` (встроенный LDC1612 SHT36 Max V3,
  адрес `43`) и `eddy_f` (внешний FLY-EDDY с шлейфом EDDY-F, адрес `42`) обе
  объявляют `[probe_eddy_current fly_eddy_probe]`, поэтому включить можно
  только одну. Любая из них требует `toolhead=sht36-v3` (пины на MCU
  `extruder`) и выключает `std.configs/probe.cfg` — иначе Klipper падает на
  дублирующей регистрации `[probe]`/`[probe_eddy_current]`. Z-хоуминг остаётся
  на `probe:z_virtual_endstop` из механики.
- **Гибрид: Z по концевику, QGL/bed_mesh по eddy.** `QUAD_GANTRY_LEVEL`
  в Klipper работает только через объект `probe`, поэтому выровнять портал
  концевиком нельзя. Если у машины с `eddy`/`eddy_f` Z паркуется аппаратным
  концевиком, профиль задаёт его в `machine-extras.cfg` (managed-слой,
  `[stepper_z]` там уже переопределён):

  ```ini
  [stepper_z]
  endstop_pin: !SENS_2
  position_endstop: 0.400 # калибруется Z_ENDSTOP_CALIBRATE
  ```

  `position_endstop` обязателен: Klipper принимает его отсутствие только при
  `probe:z_virtual_endstop`. При этом eddy-фича остаётся включённой: `G28 Z`
  идёт по концевику, `QUAD_GANTRY_LEVEL` и `BED_MESH_CALIBRATE` — по щупу.
  `check_config.py` требует `position_endstop` для любого не-`probe:`
  `endstop_pin` и запрещает `[probe]` вместе с `[probe_eddy_current]`.
- **`extruder_motor` и составной `xy_driver` — устаревшие.** Схема v1 писала
  `xy_driver=tmc5160-17HM19-1684` и `extruder_motor=...`. Теперь это ошибки с
  явной подсказкой: разбейте на `xy_driver` + `xy_motor` и переименуйте
  `extruder_motor` в `e_motor`.

## Создание профиля

### 1. Мастер

```bash
cd ~/vorons_configs
./scripts/new_machine.sh -p my-voron --size 250 --model trident \
    --board manta-m5p --vm-xy 48 \
    --features fans,display,buttons,runout,host,y_frame
```

Мастер генерирует `machine.conf` из
`scripts/templates/machine.conf.template` (русские комментарии у каждого
ключа), создаёт seed-файлы и `local/uuids.cfg`, затем рендерит `profile.cfg`
и валидирует профиль через `check_config.py --machine`.

Полезные флаги: `--xy-motor`, `--xy-driver`, `--z-driver`, `--z-motor`,
`--e-motor`, `--toolhead`, `--head`, `--frame-w`, `--frame-d`. По умолчанию
X/Y-пара и Z-пара берутся по правилу парка и archetype.

### 2. UUID плат

Замените `REPLACE_WITH_*` в `printers/<id>/local/uuids.cfg` реальными UUID
(их печатает Katapult: `python3 ~/katapult/scripts/flashtool.py -i can0 -q`;
`flash_mcu.sh` спрашивает UUID при прошивке).

### 3. Замеры anchors

Заполните `printers/<id>/anchors.cfg`: точки стола, `safe_z_home`,
`zero_reference_position`, реальные лимиты. Добавьте строку
`# замер YYYY-MM-DD`, иначе `check_config.py` выдаст предупреждение.
До замера действуют значения `geometry/<model>-<size>.cfg`.

### 4. Рендер и проверки

```bash
./scripts/deploy_configs.sh -p my-voron --render
./scripts/deploy_configs.sh -p my-voron --check
python3 scripts/check_config.py --stale-check
```

`--render` обязателен после любого изменения `machine.conf`: деплой
отказывается работать с устаревшим `profile.cfg`. `--check` собирает staging
и прогоняет полный `check_config.py`.

### 5. Деплой

```bash
./scripts/deploy_configs.sh -p my-voron -b
```

Деплой сам откажет, если `profile.cfg` устарел или Moonraker сообщает
`printing`/`paused`.

### 6. Ввод в строй

```bash
./scripts/bringup.sh --profile my-voron
```

Конвейер: `deploy → tmc → motion → pid-e → pid-b`. Этап `tmc` берёт моторы из
`xy_motor`/`z_motor`/`e_motor` и рейлы `vm_xy`/`vm_ze`, пересчитывает токи и
чоппер через `tmc_calc.py --update-module`.

## Как добавить новую пару драйвер/мотор

1. Добавьте мотор в `docs/tmc/motors.json` (обязательны `rated_current_a`,
   `inductance_mh`, `resistance_ohm`, `source`; желательно
   `step_angle_deg`).
2. Сгенерируйте и запишите модуль для обеих семейств X/Y:

   ```bash
   ./scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 48 \
       --write manta-m5p/xy-tmc5160-17HM19-1684.cfg
   ./scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 48 \
       --write manta-m8p/xy-tmc5160-17HM19-1684.cfg
   ```

   Для Z достаточно одного модуля:
   `--write 3z-tmc2109-17hs4401s.cfg`.
3. Проверьте пару на профиле и перерендерите:

   ```bash
   ./scripts/tmc_calc.py --driver tmc5160 --motor 17HM19-1684 --vm 48 \
       --write manta-m5p/xy-tmc5160-17HM19-1684.cfg \
       --wire-profile printers/voron-t
   ```

   `--wire-profile` проверит шаг мотора против `xy_step`, запишет
   `xy_driver` и `xy_motor` двумя строками, перегенерирует `profile.cfg` и
   откажется писать, если пары нет в обеих семьях или модуль не создан.

## Готовые примеры

### trident-150 (`printers/voron-t`)

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
frame_w=310
frame_d=310
features=belay,runout,btt_sfs,extra_extruder,fans,display,buttons,host,y_frame
```

Заголовок `profile.cfg` показывает resolved-карту:

```
# X/Y: tmc5160+17HM19-1684 @vm_xy=48 | Z×3: tmc2109+17HS4401S @vm_ze=24 | E: tmc2209(sht36-v3)+MOONS-CSE14HRA1L410A-01
```

### v24-350 (`printers/v24-350`)

```ini
size=350
model=v24
kinematics=corexy
z_count=4
leveling=quad_gantry_level
board=manta-m8p
xy_step=1.8
xy_motor=LDO-42STH48-2804AC
xy_driver=tmc5160
z_motor=17HS4401S
z_driver=tmc2209
e_motor=MOONS-CSE14HRA1L410A-01
toolhead=sht36-v3
head=HGX.8T
vm_xy=55
vm_ze=24
frame_w=510
frame_d=510
features=belay,runout,btt_sfs,extra_extruder,fans,display,buttons,host,y_frame
```

55 В здесь допустимы только потому, что плата — M8P V2.0 с HV-входом; для
`manta-m8p-v1.0`/`v1.1` рендер потребует `vm_xy=48`.

## Миграция со схемы v1

1. Разбейте `xy_driver=tmc5160-<мотор>` на `xy_driver=tmc5160` и
   `xy_motor=<мотор>`.
2. Переименуйте `extruder_motor` в `e_motor`.
3. Добавьте `kinematics`, `z_count`, `leveling` по таблице модели.
4. Добавьте `z_motor`/`z_driver` (trident: `17HS4401S`/`tmc2109`,
   v24: `17HS4401S`/`tmc2209`).
5. Убедитесь, что `board`, `xy_step`, `vm_xy`, `vm_ze` заданы явно.
6. Перерендерите и проверьте:

   ```bash
   ./scripts/deploy_configs.sh -p <id> --render
   ./scripts/deploy_configs.sh -p <id> --check
   ```

Набор секций merged-конфига не меняется: Z-модуль переехал из
`mechanics/<model>.cfg` в манифест, значения секций те же.