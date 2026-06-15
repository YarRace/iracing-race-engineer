# SPIKE: формат `.sto` и источник сетапа (Задачи 3 + 4)

Дата инспекции: 2026-06-15

## ИТОГОВЫЙ ВЕРДИКТ (читать первым)

1. **Современный iRacing `.sto` — закрытый бинарный формат v3** (заголовок `03 00 00 00`),
   тело сжато/зашифровано. Это НЕ текстовый/гибридный формат, как предполагал план.
   Парсить и тем более записывать `.sto`-файлы программно — ненадёжно.
2. **Источник сетапа — живой SDK `ir["CarSetup"]`** (session-info YAML). Отдаёт ВЕСЬ
   текущий сетап машины в открытом структурированном виде. Это надёжный путь чтения.
3. **Запись `.sto` невозможна → режим «ручной ввод».** Дельта от Claude выдаётся как
   список изменений `from → to` для ручного ввода в гараже iRacing. Дашборд показывает
   их. Исходные файлы НИКОГДА не трогаем. Это ровно fallback-вердикт Задачи 4 (❌).

## Почему `.sto`-файлы не подходят

Папка сетапов: `C:\Users\Ярослав\Documents\iRacing\setups\cadillacvseriesrgtp`
(имя из CarPath Задачи 2; старого `cadillacvr` из плана НЕ существует; `cadillacctsvr` пуста).

Инспекция (`spikes/inspect_sto.py`) по всем файлам:
- Покупные P1Doks-сетапы (32 шт.): ~48% печатных, заголовок `03 00 00 00 "VH" ...`,
  UTF-16LE watermark `www.p1doks.com` в хвосте, тело не распаковывается zlib/deflate.
- Файл, пересохранённый через **Save As из загруженного P1Doks** (`native_baseline.sto`,
  попытка 1): остался зашифрованным P1Doks (watermark переносится при Save As).
- Файл, пересохранённый из **заводского сетапа iRacing** (попытка 2): watermark P1Doks
  ушёл, размер 10564, заголовок всё равно `03 00 00 00`, тело — нечитаемые байты,
  текстовых секций (`[TiresAero]`, `coldPressure`, `RideHeight`) НЕТ.

Вывод: даже «чистый» iRacing-`.sto` бинарный (формат v3, сжатый). Распространённое
мнение «`.sto` текстовые» устарело — относилось к старым версиям iRacing.

Заголовок v3 (little-endian, 16 байт): `03 00 00 00 | <comp_size> | 40 0c 00 00 (=3136) | <?>`,
где `comp_size` = размер файла − 16 (подтверждено на двух файлах). Дальше сжатый поток.

## Источник сетапа: SDK `ir["CarSetup"]`  ✅

Дамп: `spikes/OUT_carsetup.json`. Фикстура для тестов: `tests/fixtures/sample_setup.json`.

Структура (Cadillac GTP) — 3 секции, вложенные подсекции, значения — строки с единицами:
```json
{
  "TiresAero": {
    "LeftFront": {"StartingPressure": "152 kPa", "LastHotPressure": "152 kPa", ...},
    "RightFront": {"StartingPressure": "152 kPa", ...},
    "LeftRearTire": {...}, "RightRearTire": {...},
    "AeroSettings": {"RearWingAngle": "17 deg"},
    "AeroCalculator": {"DownforceBalance": "52.33%", ...}
  },
  "Chassis": {
    "Front": {"ArbSize": "Soft", "ArbBlades": 3, "ToeIn": "-1.3 mm", ...},
    "LeftFront": {"RideHeight": "30.0 mm", "Camber": "-2.9 deg", "LsCompDamping": "5 clicks", ...},
    "LeftRear": {"SpringRate": "120 N/mm", "Camber": "-1.8 deg", "ToeIn": "+0.1 mm", ...},
    "RightFront": {...}, "RightRear": {...},
    "Rear": {"ThirdSpring": "580 N/mm", "ArbSize": "Medium", "CrossWeight": "50.0%", ...}
  },
  "BrakesDriveUnit": {
    "BrakeSpec": {"BrakePressureBias": "51.25%", "PadCompound": "Medium", ...},
    "Fuel": {"FuelLevel": "89.0 L", ...},
    "TcAndThrottle": {"TractionControlGain": "5 (TC B)", "ThrottleShape": 12, ...},
    "GearRatios": {...}, "DiffSpec": {"Preload": "70 Nm", ...}
  }
}
```

### Формат значений
- Почти все значения — **строки `"<число> <единица>"`**: `"152 kPa"`, `"-2.9 deg"`,
  `"30.0 mm"`, `"120 N/mm"`, `"70 Nm"`, `"89.0 L"`, `"52.33%"`.
- Некоторые — голые числа (`"ArbBlades": 3`, `"ThrottleShape": 12`, `"LD": 3.659`).
- Часть полей — несколько чисел в одной строке (`"ShockDefl": "15.0 mm 100.0 mm"` —
  текущий/макс ход) или перечисление (`"LastTempsOMI": "40C, 40C, 40C"`).
- Некоторые значения категориальные/со скобкой: `"ArbSize": "Soft"`,
  `"PowerSteeringAssist": "8 (EPAS)"`, `"TractionControlGain": "5 (TC B)"`.

## Вывод для Задач 8/9

- **Task 8 `sto_reader` → читает CarSetup.** Функция `read_sto(source)` принимает либо
  путь к JSON-дампу CarSetup (тесты/оффлайн), либо живой `ir["CarSetup"]`. Возвращает
  `{"fields": {<плоское_имя>: <значение>}, "raw": <исходная_вложенная_структура>}`.
  Плоское имя — конкатенация пути, напр. `"TiresAero.LeftFront.StartingPressure"`,
  чтобы значения были адресуемы для дельты. Парсинг числа+единицы — отдельный хелпер.
- **Task 9 `sto_writer` → режим ручного ввода.** `apply_delta(setup, delta)` НЕ пишет
  файлов. Возвращает структуру изменений `[{field, from, to, unit}]` для дашборда.
  Никогда не перезаписывает исходные `.sto`.
- Контракт `read_sto → {"fields","raw"}` сохранён (как в плане), меняется лишь источник.
