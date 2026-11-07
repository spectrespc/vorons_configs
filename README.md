# vorons_configs

Репозиторий конфигураций парка принтеров Voron. Источник истины — этот репозиторий,
а живой каталог Klipper (`~/printer_data/config`) наполняется деплоем выбранного профиля.

## Русский

### Раскладка репозитория

```text
vorons_configs/
├── printers/
│   └── voron-t/                  # профиль принтера
│       ├── printer.cfg           # манифест include, [printer] и базовые секции
│       ├── macros.cfg            # макросы конкретного принтера
│       ├── moonraker.conf        # Moonraker профиля
│       ├── KlipperScreen.conf    # seed
│       ├── crowsnest.conf        # seed
│       ├── sonar.conf            # seed
│       ├── telegram.conf         # seed
│       └── local/                # SAVE_CONFIG/тюнинг → std.config.local/
├── std.configs/                  # общие модули Klipper
│   ├── display/mini12864.cfg
│   ├── extruder/main.cfg
│   ├── extruder/heads/{HGX,BMG}.8T.cfg
│   ├── extruder/accel/lis2dw.cfg
│   └── sd_disable.cfg
├── std.macros/                   # общие макросы
├── std.compil.configs/           # конфиги сборки MCU (НЕ деплоятся)
├── scripts/                      # deploy/collect/check/build/flash
├── README.md  CHANGELOG.md  .gitignore
```

### Модель деплоя

Git-репозиторий живёт только в `~/vorons_configs`. Живой каталог `~/printer_data/config`
не является git-клоном: он наполняется скриптом `scripts/deploy_configs.sh -p <профиль>`.

- **managed** — перезаписываются при каждом деплое: `printers/<п>/{printer,macros}.cfg`,
  `moonraker.conf`, `local/*.cfg` → `std.config.local/`, весь `std.configs/` и `std.macros/`.
- **seed** — копируются только если файла ещё нет в приёмнике: `KlipperScreen.conf`,
  `crowsnest.conf`, `sonar.conf`, `telegram.conf`. Так сервисы не теряют свои настройки
  (автоблок KlipperScreen, реальный `bot_token` Telegram).
- `std.compil.configs/` в живой каталог не выкладывается: это исходники для сборки прошивок.

### Рабочий цикл

```bash
# 1. Правки/тюнинг на принтере; забрать локальные сохранения в репозиторий
~/vorons_configs/scripts/collect_local.sh -p voron-t
cd ~/vorons_configs && git add printers/voron-t/local && git commit -m "Tune voron-t" && git push

# 2. На принтере обновить клон и выложить профиль
cd ~/vorons_configs && git pull --ff-only
./scripts/deploy_configs.sh -p voron-t -b
sudo systemctl restart klipper moonraker
```

Перед перезапуском полезно проверить дерево офлайн:

```bash
./scripts/check_config.py --config-dir ~/printer_data/config
./scripts/check_config.py --merged ~/printer_data/config > /tmp/merged.cfg
```

### Скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/deploy_configs.sh -p <профиль>` | выкладка профиля (managed/seed), `-n`, `-b`, `-d` |
| `scripts/collect_local.sh -p <профиль>` | `std.config.local/*.cfg` → `printers/<п>/local/` |
| `scripts/check_config.py` | офлайн-парсер с семантикой Klipper; `--config-dir`, `--merged` |
| `scripts/build_mcu.sh -c <config> [-o out]` | сборка прошивки MCU |
| `scripts/flash_mcu.sh -u <uuid> -f <bin>` | прошивка CAN-MCU через Katapult |

### Профили и альтернативные модули

Имена профилей: `printers/<модель>-<индекс>/` (например, `voron-t`, `voron-2-1`).

В репозитории осознанно хранятся неиспользуемые модули-альтернативы парка:
`std.configs/pinout/{fly-sb2040,ebb36-v1.2}.cfg`,
`std.configs/gantry/TMC/xy-tmc5160-LDO-42SHT48-2804AC.cfg`,
`std.configs/extruder/heads/BMG.8T.cfg`, `std.configs/extruder/tc/104-gt2.cfg`,
`std.macros/{homing,actions_filament,filament_load_unload}.cfg`,
`std.configs/tc.ext/y.frame.cfg`, `std.configs/sht36-v3.eddy.cfg`.
Их не нужно удалять: они включаются в других профилях или при смене головы.
Секции `[mcu ...]` и CAN-UUID всегда живут в `printers/<п>/local/uuids.cfg`,
а не в общих pinout-модулях.

### Секреты

- Не коммитить реальный `bot_token`/`chat_id` в `telegram.conf`: в репозитории заглушка.
  Если секрет уже попал в историю — сменить токен у бота.
- Репозиторий приватный; `local/` (UUID, PID, input shaper) коммитится осознанно.
- `KlipperScreen.conf` содержит автогенерируемый блок `#~#`, поэтому он seed.

### Известные ограничения

- `std.configs/sd_disable.cfg` пока включает оба пина SD-слотов вместе (`PC0, PC1`).
  Раздельное управление — после подтверждения электрики слотов.
- Ветка Eddy (`std.configs/sht36-v3.eddy.cfg`) выключена; макросы
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` ещё не перенесены с машины-донора.

## English

Repository of configuration files for my Voron printer fleet. The repository is the
source of truth; the live Klipper directory (`~/printer_data/config`) is populated by
deploying one printer profile.

### Repository layout

```text
vorons_configs/
├── printers/
│   └── voron-t/                  # printer profile
│       ├── printer.cfg           # include manifest, [printer] and base sections
│       ├── macros.cfg            # printer-specific macros
│       ├── moonraker.conf        # profile Moonraker config
│       ├── KlipperScreen.conf    # seed
│       ├── crowsnest.conf        # seed
│       ├── sonar.conf            # seed
│       ├── telegram.conf         # seed
│       └── local/                # SAVE_CONFIG/tuning -> std.config.local/
├── std.configs/                  # shared Klipper modules
│   ├── display/mini12864.cfg
│   ├── extruder/main.cfg
│   ├── extruder/heads/{HGX,BMG}.8T.cfg
│   ├── extruder/accel/lis2dw.cfg
│   └── sd_disable.cfg
├── std.macros/                   # shared macros
├── std.compil.configs/           # MCU build configs (NOT deployed)
├── scripts/                      # deploy/collect/check/build/flash
├── README.md  CHANGELOG.md  .gitignore
```

### Deployment model

The git repository lives only in `~/vorons_configs`. The live directory
`~/printer_data/config` is not a git clone; it is populated by
`scripts/deploy_configs.sh -p <profile>`.

- **managed** — overwritten on every deploy: `printers/<p>/{printer,macros}.cfg`,
  `moonraker.conf`, `local/*.cfg` → `std.config.local/`, all of `std.configs/` and `std.macros/`.
- **seed** — copied only when missing in the destination: `KlipperScreen.conf`,
  `crowsnest.conf`, `sonar.conf`, `telegram.conf`. This preserves service-generated state
  (the KlipperScreen auto block, a real Telegram `bot_token`).
- `std.compil.configs/` is never deployed: it holds MCU firmware build configs.

### Workflow

```bash
# 1. Edit/tune on the printer, then collect local overrides into the repository
~/vorons_configs/scripts/collect_local.sh -p voron-t
cd ~/vorons_configs && git add printers/voron-t/local && git commit -m "Tune voron-t" && git push

# 2. On the printer, update the clone and deploy the profile
cd ~/vorons_configs && git pull --ff-only
./scripts/deploy_configs.sh -p voron-t -b
sudo systemctl restart klipper moonraker
```

Validate the tree offline before restarting:

```bash
./scripts/check_config.py --config-dir ~/printer_data/config
./scripts/check_config.py --merged ~/printer_data/config > /tmp/merged.cfg
```

### Scripts

| Script | Purpose |
|---|---|
| `scripts/deploy_configs.sh -p <profile>` | deploy a profile (managed/seed), `-n`, `-b`, `-d` |
| `scripts/collect_local.sh -p <profile>` | `std.config.local/*.cfg` → `printers/<p>/local/` |
| `scripts/check_config.py` | offline parser with Klipper semantics; `--config-dir`, `--merged` |
| `scripts/build_mcu.sh -c <config> [-o out]` | build MCU firmware |
| `scripts/flash_mcu.sh -u <uuid> -f <bin>` | flash a CAN MCU through Katapult |

### Profiles and alternative modules

Profile names: `printers/<model>-<index>/` (for example `voron-t`, `voron-2-1`).

The repository intentionally keeps unused fleet-alternative modules:
`std.configs/pinout/{fly-sb2040,ebb36-v1.2}.cfg`,
`std.configs/gantry/TMC/xy-tmc5160-LDO-42SHT48-2804AC.cfg`,
`std.configs/extruder/heads/BMG.8T.cfg`, `std.configs/extruder/tc/104-gt2.cfg`,
`std.macros/{homing,actions_filament,filament_load_unload}.cfg`,
`std.configs/tc.ext/y.frame.cfg`, `std.configs/sht36-v3.eddy.cfg`.
Do not delete them: other profiles or toolhead swaps use them.
`[mcu ...]` sections and CAN UUIDs always live in `printers/<p>/local/uuids.cfg`,
never in shared pinout modules.

### Secrets

- Never commit a real `bot_token`/`chat_id` in `telegram.conf`; the repository keeps a
  placeholder. If a secret ever reaches history, rotate the bot token.
- The repository is private; `local/` (UUIDs, PID, input shaper) is committed deliberately.
- `KlipperScreen.conf` contains a generated `#~#` block, which is why it is a seed file.

### Known limitations

- `std.configs/sd_disable.cfg` currently drives both SD-slot pins together (`PC0, PC1`).
  Separate control requires confirming the slot wiring.
- The Eddy branch (`std.configs/sht36-v3.eddy.cfg`) is disabled; the
  `std.macros/{eddy,G28,TEMP_NOZZLE}.cfg` files have not been copied from the donor
  machine yet.