# Источники данных `docs/tmc/`

## Вендорские расчётные таблицы

Оба файла — официальные калькуляторы Trinamic (с 2020 г. Trinamic входит в
Analog Devices). Прямые адреса `analog.com` из этой сети недоступны (соединение
не устанавливается), а `trinamic.com` отвечает `301` на тот же адрес
`analog.com`. Поэтому файлы получены из Wayback Machine — это те же байты,
которые отдавал `analog.com`; в таблице указан и исходный, и фактический адрес.

| Файл | Размер | SHA-256 |
|---|---|---|
| `docs/tmc/TMC5160_Calculations.xlsx` | 97 092 Б | `66ee14d79c1e042e3b2027c22575d7fadc8d9b7bee338395dffea108dac0f62c` |
| `docs/tmc/TMC2209_Calculations.xlsx` | 44 949 Б | `97b642b30d493dc21feac777a48582bcd28191a81cc13952be22ac4f9a5e406f` |

| Файл | Исходный адрес (вендор) | Фактически скачан | Дата |
|---|---|---|---|
| `TMC5160_Calculations.xlsx` | `https://www.trinamic.com/fileadmin/assets/Products/ICs_Documents/TMC5160_Calculations.xlsx` (301 → `https://www.analog.com/media/en/engineering-tools/design-tools/TMC5160_Calculations.xlsx`) | `https://web.archive.org/web/20240216044714id_/https://www.analog.com/media/en/engineering-tools/design-tools/tmc5160_calculations.xlsx` | 2026-11-15 |
| `TMC2209_Calculations.xlsx` | `https://www.analog.com/media/en/engineering-tools/design-tools/TMC2209_Calculations.xlsx` | `https://web.archive.org/web/20240120062414id_/https://www.analog.com/media/en/engineering-tools/design-tools/TMC2209_Calculations.xlsx` | 2026-11-15 |

Проверка целостности:

```bash
sha256sum docs/tmc/*.xlsx
```

Обе книги открываются как ZIP (`xl/workbook.xml` + листы); использованные листы:

- `TMC5160_Calculations.xlsx`: `Chopper Parameters`, `Rsense`, `Power Dissipation`;
- `TMC2209_Calculations.xlsx`: `Chopper Parameters`, `Rsense`, `Power Dissipation`.

Листы `Velocity Calculation`, `Datagram CRC calculation`, `Encoder Constant`,
`Microstep Table` к задаче не относятся и не переносились.

## Даташиты моторов (для `docs/tmc/motors.json`)

| Мотор | Параметры | Источник |
|---|---|---|
| LDO-42STH48-2804AC | 2.8 A/фаза, 0.7 Ω, 0.6 мГн, 1.8° | <https://ldomotion.com/products/ldo42sth482804ac> |
| 17HM19-1684 | 1.68 A/фаза, 1.65 Ω, 4.10 мГн, 0.9° | <https://files.omc-stepperonline.com/17HM19-1684S_Full_Datasheet.pdf> |
| 17HS4401S | 1.7 A/фаза, 1.5 Ω, 2.8 мГн, 1.8° | <https://www.handsontec.com/dataspecs/17HS4401S.pdf> |
| 17HS19-2004S1 | 2.0 A/фаза, 1.4 Ω, 3.0 мГн, 1.8°, 59 Н·см | <https://www.omc-stepperonline.com/download/17HS19-2004S1.pdf> |
| MOONS-CSE14HRA1L410A-01 | 1.0 A/фаза, 1.9 Ω ±10 %, 1.41 мГн ±20 %, 10 Н·см, 1.8° | <https://biqu.equipment/products/moons-cse14hra1l410a-01-36-stepper-motor> |

Значения в `motors.json` взяты из этих документов; поле `source` у каждой
записи обязательно и проверяется скриптом при загрузке базы. Для X/Y и Z это
**пиковый** ток фазы: рельсы считаются с `--current-basis peak`, и `run_current`
Klipper (RMS) равен `I_peak / √2 ≈ 0.707 · I_peak`. Запись
`MOONS-CSE14HRA1L410A-01` — мотор экструдера HGX 8T (NEMA14, 36 мм, шестерня
8T). Её `rated_current_a` (1.0 A, RMS), `inductance_mh` и `resistance_ohm` нужны
только для **расчёта чоппер-регистров** (`driver_HSTRT/HEND`) при фактических токах
секций: `extruder` 0.55 A и `extruder_stepper ext-extruder` 0.60 A. Ток
экструдеров до номинала не повышается — `--run-current` задаёт его явно, а
`rated_current_a` используется лишь для вывода `i_factor_effective`. Таблица `motor_by_module` в том же
файле сопоставляет имя TMC-модуля мотору и проверяется при загрузке.

## Формулы Klipper (для сверки регистров тока)

`scripts/tmc_calc.py` не изобретает регистры тока: формулы CS/IRUN взяты из
установленного Klipper (`~/klipper/klippy/extras/tmc2130.py`,
`TMC5160CurrentHelper` в `tmc5160.py`). Версия Klipper — та, что стоит на
машине; при обновлении Klipper формулы следует перепроверить.