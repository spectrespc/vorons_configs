## Русский

Стандартные конфиги для моего парка принтеров Voron.

### Развёртывание конфигов

`deploy_configs.sh` копирует файлы `*.cfg`, `*.conf` и каталог `std.compil.configs/` в `~/printer_data/config`, сохраняя структуру каталогов. Каталог `.git` пропускается. При ошибке чтения источника выкладка прерывается, частичное копирование не выполняется.

```bash
./deploy_configs.sh -n                        # предпросмотр без изменений
./deploy_configs.sh                           # источник — каталог скрипта
./deploy_configs.sh -s /path/to/clone         # явный источник
./deploy_configs.sh -s SRC -d DEST            # явные источник и приёмник
./deploy_configs.sh -b                        # с резервной копией перезаписываемых файлов
```

С флагом `-b` перезаписываемые файлы сохраняются в `<DEST>/.backup/<timestamp>/` с той же структурой каталогов.

## English

Standard configs for my Voron printer fleet.

### Deploying configs

`deploy_configs.sh` copies `*.cfg` and `*.conf` files plus the `std.compil.configs/` directory into `~/printer_data/config`, preserving the directory structure. The `.git` directory is skipped. If the source cannot be read completely, the deployment aborts instead of copying a partial set.

```bash
./deploy_configs.sh -n                        # dry run, no changes
./deploy_configs.sh                           # source is the script's directory
./deploy_configs.sh -s /path/to/clone         # explicit source
./deploy_configs.sh -s SRC -d DEST            # explicit source and destination
./deploy_configs.sh -b                        # back up overwritten files
```

With `-b`, overwritten files are saved under `<DEST>/.backup/<timestamp>/` with the same directory structure.
