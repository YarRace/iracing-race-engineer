# iRacing Race Engineer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пост-анализ заезда в iRacing (Cadillac GTP @ Watkins Glen): из телеметрии + условий + текущего `.sto` выдать разбор пилотирования, рекомендации по сетапу и готовый `.sto`-файл с объяснением.

**Architecture:** 5 независимых модулей на одном Windows-ПК: `collector` (читает живой SDK), `metrics` (детерминированный расчёт симптомов), `explainer` (Claude превращает симптомы в рекомендации), `setup` (чтение/запись `.sto`), `dashboard` (FastAPI + HTML на втором экране). Метрики и дашборд не зависят от Claude Code → задел под продукт.

**Tech Stack:** Python 3.11+, pyirsdk, FastAPI + uvicorn, pytest, Anthropic SDK (Claude), ванильный HTML/JS.

**⚠️ Платформа:** всё запускается на **Windows-ПК, где установлен iRacing** (SDK = Windows memory-mapped file). Задачи с пометкой `[НУЖЕН СИМ]` требуют запущенного iRacing.

**Спецификация:** `docs/superpowers/specs/2026-06-15-iracing-race-engineer-design.md`

**Порядок:** сначала спайки (Tasks 2–4) снимают единственные неизвестные (живые каналы SDK + формат `.sto`). Метрики (Tasks 10–15) — чистая оффлайн-разработка на записанной фикстуре стинта, без сима.

---

## Файловая структура

```
iracing-race-engineer/
├── requirements.txt
├── README.md
├── pytest.ini
├── config/
│   └── channels.py          # карта raw iRacing-каналов → нормализованные поля (заполняется по Task 2)
├── src/ire/
│   ├── __init__.py
│   ├── collector/
│   │   ├── irsdk_reader.py   # pyirsdk → нормализованный кадр телеметрии
│   │   ├── stint_recorder.py # детект границ стинта + запись лога (.jsonl)
│   │   └── live_state.py     # текущий снимок для дашборда
│   ├── setup/
│   │   ├── sto_reader.py     # .sto → dict полей (по Task 3)
│   │   └── sto_writer.py     # дельта → новый .sto (по Task 4)
│   ├── metrics/
│   │   ├── tire.py
│   │   ├── balance.py
│   │   ├── suspension.py
│   │   ├── inputs.py
│   │   ├── consistency.py
│   │   └── symptoms.py       # агрегатор → symptoms JSON
│   ├── explainer/
│   │   └── explainer.py      # интерфейс + Claude-реализация
│   ├── dashboard/
│   │   ├── server.py         # FastAPI
│   │   └── static/index.html
│   └── orchestrator.py       # склейка: collector → metrics → explainer → writer → dashboard
├── spikes/                   # результаты спайков (дампы каналов, заметки по формату .sto)
└── tests/
    ├── fixtures/             # sample_stint.jsonl, sample_setup.sto, sample_symptoms.json
    └── test_*.py
```

**Нормализованный кадр телеметрии** (контракт между `collector` и `metrics` — определяется в Task 5, потребляется метриками):
```python
{
  "t": float, "lap": int, "lap_dist_pct": float,   # время сессии, круг, доля круга 0..1
  "speed": float, "throttle": float, "brake": float, # м/с, 0..1, 0..1
  "steer": float, "lat_accel": float, "long_accel": float, "yaw_rate": float,  # рад, м/с², рад/с
  "gear": int, "fuel": float,
  "tires": {"LF": {"tl": float, "tm": float, "tr": float}, "RF": {...}, "LR": {...}, "RR": {...}},  # °C
  "shock_defl": {"LF": float, "RF": float, "LR": float, "RR": float},  # м
  "track_temp": float, "air_temp": float
}
```
Метрики работают ТОЛЬКО с этим контрактом → тестируются синтетическими кадрами без сима. Соответствие «raw iRacing → этот контракт» живёт в одном месте (`config/channels.py` + `irsdk_reader.py`) и подтверждается спайком Task 2.

---

## Task 1: Скаффолд проекта

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `src/ire/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Создать `requirements.txt`**
```
pyirsdk
fastapi
uvicorn[standard]
anthropic
pytest
```

- [ ] **Step 2: Создать `pytest.ini`**
```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 3: Создать пакет и smoke-тест**

`src/ire/__init__.py`:
```python
__version__ = "0.1.0"
```
`tests/test_smoke.py`:
```python
from ire import __version__

def test_version():
    assert __version__ == "0.1.0"
```

- [ ] **Step 4: Поставить зависимости и прогнать тест**

Run: `pip install -r requirements.txt && pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "chore: project scaffold"
```

---

## Task 2: `[НУЖЕН СИМ]` SPIKE — дамп живых каналов SDK

**Цель:** подтвердить, что pyirsdk работает, и зафиксировать РЕАЛЬНЫЕ имена каналов + структуру `WeekendInfo` для Cadillac GTP. Результат — основа `config/channels.py`.

**Files:**
- Create: `spikes/dump_channels.py`, `spikes/OUT_channels.txt` (артефакт)

- [ ] **Step 1: Скрипт дампа**

`spikes/dump_channels.py`:
```python
import irsdk, time, json

ir = irsdk.IRSDK()
assert ir.startup(), "iRacing не запущен / SDK не доступен"
time.sleep(0.5)

# Все доступные телеметрийные каналы и их текущие значения
keys = sorted(ir._var_headers_dict.keys())
with open("spikes/OUT_channels.txt", "w", encoding="utf-8") as f:
    for k in keys:
        f.write(f"{k} = {ir[k]}\n")
    f.write("\n\n=== WeekendInfo ===\n")
    f.write(json.dumps(ir["WeekendInfo"], indent=2, ensure_ascii=False))
    f.write("\n\n=== DriverInfo (active car) ===\n")
    f.write(json.dumps(ir["DriverInfo"], indent=2, ensure_ascii=False))
print(f"Готово: {len(keys)} каналов → spikes/OUT_channels.txt")
ir.shutdown()
```

- [ ] **Step 2: Запустить в симе** (сесть на трассу за Cadillac GTP на Watkins, выехать)

Run: `python spikes/dump_channels.py`
Expected: файл `spikes/OUT_channels.txt` с 200+ каналами; внутри есть `Speed`, `Throttle`, `Brake`, `SteeringWheelAngle`, `LatAccel`, `YawRate`, `FuelLevel`, температуры шин (имена вида `LFtemp*`), прогибы амортизаторов (`*shockDefl`), а в `WeekendInfo` — `TrackName`, `TrackSurfaceTemp`/`TrackAirTemp`.

- [ ] **Step 3: Заполнить `config/channels.py` найденными именами**

`config/channels.py` (значения суффиксов взять из `OUT_channels.txt` — НЕ угадывать):
```python
# Карта: нормализованное поле -> точное имя канала iRacing (подтверждено дампом Task 2)
SCALAR = {
    "speed": "Speed", "throttle": "Throttle", "brake": "Brake",
    "steer": "SteeringWheelAngle", "lat_accel": "LatAccel",
    "long_accel": "LongAccel", "yaw_rate": "YawRate",
    "gear": "Gear", "fuel": "FuelLevel",
    "lap": "Lap", "lap_dist_pct": "LapDistPct", "t": "SessionTime",
}
# Температуры шин: 3 точки протектора на угол. ТОЧНЫЕ суффиксы — из OUT_channels.txt.
TIRE_TEMP = {
    "LF": ("<LF_left>", "<LF_mid>", "<LF_right>"),  # заменить на реальные имена из дампа
    "RF": ("<RF_left>", "<RF_mid>", "<RF_right>"),
    "LR": ("<LR_left>", "<LR_mid>", "<LR_right>"),
    "RR": ("<RR_left>", "<RR_mid>", "<RR_right>"),
}
SHOCK_DEFL = {"LF": "<LFshockDefl>", "RF": "<RFshockDefl>", "LR": "<LRshockDefl>", "RR": "<RRshockDefl>"}
WEEKEND_TRACK_TEMP = "TrackSurfaceTemp"  # подтвердить ключ по WeekendInfo
WEEKEND_AIR_TEMP = "TrackAirTemp"
```
> Плейсхолдеры `<...>` ОБЯЗАТЕЛЬНО заменить реальными именами из `OUT_channels.txt`. Это и есть смысл спайка — добыть факт, а не выдумать.

- [ ] **Step 4: Commit**
```bash
git add spikes/dump_channels.py config/channels.py
git commit -m "spike: dump live SDK channels, fill channel map"
```

---

## Task 3: `[НУЖЕН СИМ]` SPIKE — формат `.sto` Cadillac

**Цель:** определить, текстовый или бинарный `.sto`, и как закодированы поля. Без этого `sto_reader`/`sto_writer` писать нельзя.

**Files:**
- Create: `spikes/inspect_sto.py`, `spikes/NOTES_sto_format.md` (артефакт), `tests/fixtures/sample_setup.sto` (копия реального файла)

- [ ] **Step 1: Найти и скопировать реальный сетап**

Run (Windows):
```bash
dir "%USERPROFILE%\Documents\iRacing\setups\cadillacvr"
```
Скопировать любой существующий `.sto` Кадиллака в `tests/fixtures/sample_setup.sto`.

- [ ] **Step 2: Скрипт-инспектор**

`spikes/inspect_sto.py`:
```python
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/sample_setup.sto"
raw = open(p, "rb").read()
printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in raw)
print(f"размер={len(raw)} печатных_байт={printable} ({printable/len(raw):.0%})")
print("--- первые 512 байт как текст ---")
print(raw[:512].decode("latin-1"))
print("--- hex первых 64 байт ---")
print(raw[:64].hex(" "))
```

- [ ] **Step 3: Запустить, задокументировать формат**

Run: `python spikes/inspect_sto.py`
В `spikes/NOTES_sto_format.md` зафиксировать: текст/бинарь; есть ли заголовок; как выглядят пары «параметр = значение» (например `Front tire pressure: 138 kPa`); единицы. Это вход для Task 8/9.

- [ ] **Step 4: Commit**
```bash
git add spikes/inspect_sto.py spikes/NOTES_sto_format.md tests/fixtures/sample_setup.sto
git commit -m "spike: determine .sto file format"
```

---

## Task 4: `[НУЖЕН СИМ]` SPIKE — round-trip записи `.sto`

**Цель:** разрешить ЕДИНСТВЕННЫЙ риск проекта — примет ли iRacing программно-изменённый `.sto`.

**Files:**
- Create: `spikes/roundtrip_sto.py`, дополнить `spikes/NOTES_sto_format.md`

- [ ] **Step 1: Скрипт round-trip** (логика правки — по NOTES из Task 3)
```python
# spikes/roundtrip_sto.py
# 1. читает sample_setup.sto, 2. меняет ОДНО поле (напр. давление в шине на +1),
# 3. пишет cadillacvr/SPIKE_TEST.sto. Реализация парс/правки — по NOTES_sto_format.md.
```

- [ ] **Step 2: Записать тестовый файл в папку сетапов**

Run: `python spikes/roundtrip_sto.py`

- [ ] **Step 3: Проверить в симе** — в гараже загрузить `SPIKE_TEST` и убедиться, что значение применилось.

- [ ] **Step 4: Записать ВЕРДИКТ в `NOTES_sto_format.md`**
  - ✅ грузит → `sto_writer` пишет файлы (Task 9 в полном режиме).
  - ❌ отверг → `sto_writer` работает в режиме «значения для ручного ввода», дашборд их показывает. Никогда не перезаписываем исходники.

- [ ] **Step 5: Commit**
```bash
git add spikes/roundtrip_sto.py spikes/NOTES_sto_format.md
git commit -m "spike: .sto write round-trip verdict"
```

---

## Task 5: `irsdk_reader` — нормализованный кадр

**Files:**
- Create: `src/ire/collector/irsdk_reader.py`, `tests/test_irsdk_reader.py`

- [ ] **Step 1: Тест на нормализацию (с фейковым источником, без сима)**

`tests/test_irsdk_reader.py`:
```python
from ire.collector.irsdk_reader import normalize_frame

def test_normalize_maps_raw_to_contract():
    raw = {
        "SessionTime": 12.5, "Lap": 3, "LapDistPct": 0.42,
        "Speed": 60.0, "Throttle": 0.9, "Brake": 0.0,
        "SteeringWheelAngle": 0.1, "LatAccel": 8.0, "LongAccel": -2.0,
        "YawRate": 0.3, "Gear": 4, "FuelLevel": 50.0,
        "TrackSurfaceTemp": 40.0, "TrackAirTemp": 25.0,
        # температуры/прогибы добавляются с реальными ключами из channels.TIRE_TEMP/SHOCK_DEFL
    }
    tires = {"LF": (80, 85, 90), "RF": (80, 85, 90), "LR": (82, 86, 91), "RR": (82, 86, 91)}
    shocks = {"LF": 0.01, "RF": 0.012, "LR": 0.02, "RR": 0.021}
    for c, (l, m, r) in tires.items():
        from config.channels import TIRE_TEMP
        raw[TIRE_TEMP[c][0]] = l; raw[TIRE_TEMP[c][1]] = m; raw[TIRE_TEMP[c][2]] = r
    for c, v in shocks.items():
        from config.channels import SHOCK_DEFL
        raw[SHOCK_DEFL[c]] = v

    f = normalize_frame(lambda k: raw[k])
    assert f["speed"] == 60.0
    assert f["lap"] == 3
    assert f["tires"]["LR"]["tm"] == 86
    assert f["shock_defl"]["RR"] == 0.021
    assert f["track_temp"] == 40.0
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `pytest tests/test_irsdk_reader.py -v`
Expected: FAIL (`normalize_frame` не определена)

- [ ] **Step 3: Реализация**

`src/ire/collector/irsdk_reader.py`:
```python
from config import channels

def normalize_frame(get):
    """get(channel_name) -> value. Источник: pyirsdk (ir.__getitem__) или dict в тестах."""
    f = {k: get(v) for k, v in channels.SCALAR.items()}
    f["tires"] = {
        c: {"tl": get(t[0]), "tm": get(t[1]), "tr": get(t[2])}
        for c, t in channels.TIRE_TEMP.items()
    }
    f["shock_defl"] = {c: get(v) for c, v in channels.SHOCK_DEFL.items()}
    f["track_temp"] = get(channels.WEEKEND_TRACK_TEMP)
    f["air_temp"] = get(channels.WEEKEND_AIR_TEMP)
    return f
```
> Примечание: `track_temp`/`air_temp` в живом SDK лежат в `WeekendInfo` (YAML), не в скалярных каналах. В живом `irsdk_reader` для них использовать `ir["WeekendInfo"]["TrackSurfaceTemp"]`; в тесте — плоский dict. Обернуть доступ в `get` так, чтобы оба пути работали (адаптер в live-цикле Task 6).

- [ ] **Step 4: Запустить — должен пройти**

Run: `pytest tests/test_irsdk_reader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat: irsdk_reader normalized frame"
```

---

## Task 6: `[НУЖЕН СИМ для записи фикстуры]` `stint_recorder` — детект стинта + лог

**Files:**
- Create: `src/ire/collector/stint_recorder.py`, `tests/test_stint_recorder.py`

- [ ] **Step 1: Тест детектора границ стинта**
```python
# tests/test_stint_recorder.py
from ire.collector.stint_recorder import StintDetector

def test_stint_closes_when_entering_pits():
    d = StintDetector()
    assert d.update(on_track=True) == "running"
    assert d.update(on_track=True) == "running"
    assert d.update(on_track=False) == "closed"   # заехал в бокс → стинт закрыт
    assert d.update(on_track=False) == "idle"
```

- [ ] **Step 2: Запустить — FAIL**

Run: `pytest tests/test_stint_recorder.py -v` → FAIL

- [ ] **Step 3: Реализация**
```python
# src/ire/collector/stint_recorder.py
import json

class StintDetector:
    def __init__(self):
        self._prev_on_track = False
    def update(self, on_track: bool) -> str:
        was = self._prev_on_track
        self._prev_on_track = on_track
        if on_track:
            return "running"
        return "closed" if was else "idle"

class StintWriter:
    def __init__(self, path): self._f = open(path, "w", encoding="utf-8")
    def write(self, frame: dict): self._f.write(json.dumps(frame) + "\n")
    def close(self): self._f.close()
```

- [ ] **Step 4: Запустить — PASS**

Run: `pytest tests/test_stint_recorder.py -v` → PASS

- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "feat: stint detection + jsonl writer"
```

---

## Task 7: `[НУЖЕН СИМ]` Записать реальную фикстуру стинта

**Цель:** один реальный заезд на Watkins → лог `tests/fixtures/sample_stint.jsonl`. На нём оффлайн разрабатываются ВСЕ метрики.

- [ ] **Step 1:** Собрать минимальный live-цикл: `ir.startup()` → каждые ~16 мс `normalize_frame` → `StintWriter.write` → на `StintDetector=="closed"` закрыть файл.
- [ ] **Step 2:** Проехать 5–10 чистых кругов за Cadillac GTP на Watkins, заехать в бокс.
- [ ] **Step 3:** Убедиться, что `sample_stint.jsonl` содержит сотни кадров с непустыми температурами шин и прогибами.
- [ ] **Step 4: Commit**
```bash
git add tests/fixtures/sample_stint.jsonl
git commit -m "test: real Watkins stint fixture"
```

---

## Task 8: `sto_reader` — парсинг `.sto`

**Files:**
- Create: `src/ire/setup/sto_reader.py`, `tests/test_sto_reader.py`
- Использует: `tests/fixtures/sample_setup.sto` (Task 3) и `spikes/NOTES_sto_format.md`

- [ ] **Step 1: Тест на реальном файле** (ожидаемые поля/значения взять из NOTES — НЕ выдумывать)
```python
# tests/test_sto_reader.py
from ire.setup.sto_reader import read_sto

def test_reads_known_fields_from_fixture():
    s = read_sto("tests/fixtures/sample_setup.sto")
    # имена полей и хотя бы одно значение сверить с тем, что показал inspect_sto.py
    assert "fields" in s and len(s["fields"]) > 0
    assert any("pressure" in k.lower() for k in s["fields"])
```

- [ ] **Step 2: FAIL** — Run: `pytest tests/test_sto_reader.py -v`

- [ ] **Step 3: Реализация по NOTES_sto_format.md.** Возвращает `{"fields": {<имя>: <значение>}, "raw": <исходные данные для записи>}`. Если формат текстовый — парсить строки `имя: значение единицы`; если бинарный — по задокументированной структуре.

- [ ] **Step 4: PASS** — Run: `pytest tests/test_sto_reader.py -v`

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: .sto reader"`

---

## Task 9: `sto_writer` — применение дельты

**Files:**
- Create: `src/ire/setup/sto_writer.py`, `tests/test_sto_writer.py`
- Режим (файл vs «ручной ввод») — по вердикту Task 4.

- [ ] **Step 1: Тест round-trip чтение→правка→чтение**
```python
# tests/test_sto_writer.py
import os
from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import write_sto

def test_delta_applied_and_originals_untouched(tmp_path):
    base = "tests/fixtures/sample_setup.sto"
    before = read_sto(base)
    key = next(k for k in before["fields"] if "pressure" in k.lower())
    out = tmp_path / "AI_v1.sto"
    write_sto(base, {key: before["fields"][key] + 1}, str(out))
    after = read_sto(str(out))
    assert after["fields"][key] == before["fields"][key] + 1
    assert os.path.exists(base)  # исходник цел
```

- [ ] **Step 2: FAIL** — `pytest tests/test_sto_writer.py -v`

- [ ] **Step 3: Реализация.** `write_sto(base_path, delta: dict, out_path)`: читает base, применяет дельту, пишет НОВЫЙ файл `out_path`. Никогда не перезаписывает `base_path`. Если Task 4 = «отверг» — вместо записи в папку сетапов возвращает дельту как текст для дашборда.

- [ ] **Step 4: PASS** — `pytest tests/test_sto_writer.py -v`

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: .sto writer (new-file-only)"`

---

## Task 10: Метрика — шины (`metrics/tire.py`)

**Files:** Create `src/ire/metrics/tire.py`, `tests/test_tire.py`

- [ ] **Step 1: Тест**
```python
# tests/test_tire.py
from ire.metrics.tire import tire_metrics

def _frame(temps):
    return {"tires": {c: {"tl": t[0], "tm": t[1], "tr": t[2]} for c, t in temps.items()}}

def test_inner_hotter_means_too_much_camber():
    # LF: внутренняя кромка (tl) горячее внешней → избыток развала спереди
    frames = [_frame({"LF": (110, 95, 80), "RF": (80, 95, 110),
                      "LR": (90, 90, 90), "RR": (90, 90, 90)})]
    m = tire_metrics(frames)
    assert m["LF"]["spread"] == 30           # 110 - 80
    assert m["LF"]["bias"] == "inner_hot"
    assert m["front_rear_balance"] > 0       # перед горячее зада
```

- [ ] **Step 2: FAIL** — `pytest tests/test_tire.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/metrics/tire.py
def _avg(xs): return sum(xs) / len(xs)

def tire_metrics(frames):
    out = {}
    corner_means = {}
    for c in ("LF", "RF", "LR", "RR"):
        tl = _avg([f["tires"][c]["tl"] for f in frames])
        tm = _avg([f["tires"][c]["tm"] for f in frames])
        tr = _avg([f["tires"][c]["tr"] for f in frames])
        spread = round(max(tl, tm, tr) - min(tl, tm, tr), 1)
        bias = "even"
        if tl - tr > 8: bias = "inner_hot" if c[0] == "L" else "outer_hot"
        elif tr - tl > 8: bias = "outer_hot" if c[0] == "L" else "inner_hot"
        out[c] = {"tl": round(tl, 1), "tm": round(tm, 1), "tr": round(tr, 1),
                  "spread": spread, "bias": bias}
        corner_means[c] = _avg([tl, tm, tr])
    front = _avg([corner_means["LF"], corner_means["RF"]])
    rear = _avg([corner_means["LR"], corner_means["RR"]])
    out["front_rear_balance"] = round(front - rear, 1)
    return out
```

- [ ] **Step 4: PASS** — `pytest tests/test_tire.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: tire metrics"`

---

## Task 11: Метрика — баланс (`metrics/balance.py`)

**Files:** Create `src/ire/metrics/balance.py`, `tests/test_balance.py`

Признак недо-/избытка: при повороте сравниваем фактический yaw rate с «нейтральным» (по скорости и углу руля). Меньше нужного → недостаточная (push), больше → избыточная (loose).

- [ ] **Step 1: Тест**
```python
# tests/test_balance.py
from ire.metrics.balance import balance_metrics

def _f(speed, steer, yaw, phase_throttle, brake=0.0):
    return {"speed": speed, "steer": steer, "yaw_rate": yaw,
            "throttle": phase_throttle, "brake": brake, "lat_accel": 8.0}

def test_low_yaw_for_steering_is_understeer():
    # большой угол руля, но машина почти не поворачивает → недостаток
    frames = [_f(50, 0.5, 0.05, 0.0, brake=0.5) for _ in range(50)]
    m = balance_metrics(frames)
    assert m["entry"]["tendency"] == "understeer"
```

- [ ] **Step 2: FAIL** — `pytest tests/test_balance.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/metrics/balance.py
import math

def _phase(f):
    if f["brake"] > 0.2: return "entry"
    if f["throttle"] > 0.2: return "exit"
    return "mid"

def _tendency(samples):
    # ожидаемый yaw ~ steer*speed*k (упрощённо, k подбирается калибровкой); сравниваем со средним фактическим
    if not samples: return "n/a"
    exp = sum(abs(s["steer"]) * s["speed"] for s in samples) / len(samples)
    act = sum(abs(s["yaw_rate"]) for s in samples) / len(samples)
    if exp == 0: return "neutral"
    ratio = act / (exp * 0.04)  # 0.04 — стартовый калибровочный коэффициент, уточняется на фикстуре
    if ratio < 0.85: return "understeer"
    if ratio > 1.15: return "oversteer"
    return "neutral"

def balance_metrics(frames):
    turning = [f for f in frames if abs(f["steer"]) > 0.1]
    out = {}
    for ph in ("entry", "mid", "exit"):
        s = [f for f in turning if _phase(f) == ph]
        out[ph] = {"tendency": _tendency(s), "samples": len(s)}
    return out
```

- [ ] **Step 4: PASS** — `pytest tests/test_balance.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: balance metrics"`

---

## Task 12: Метрика — подвеска (`metrics/suspension.py`)

**Files:** Create `src/ire/metrics/suspension.py`, `tests/test_suspension.py`

- [ ] **Step 1: Тест**
```python
# tests/test_suspension.py
from ire.metrics.suspension import suspension_metrics

def test_detects_bottoming_when_defl_near_max():
    frames = [{"shock_defl": {"LF": 0.001, "RF": 0.001, "LR": 0.001, "RR": 0.001}} for _ in range(10)]
    m = suspension_metrics(frames, min_defl=0.002)
    assert m["LF"]["bottoming_pct"] == 100.0
```

- [ ] **Step 2: FAIL** — `pytest tests/test_suspension.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/metrics/suspension.py
def suspension_metrics(frames, min_defl=0.002):
    out = {}
    for c in ("LF", "RF", "LR", "RR"):
        vals = [f["shock_defl"][c] for f in frames]
        bottom = sum(v <= min_defl for v in vals)
        out[c] = {"min": round(min(vals), 4), "max": round(max(vals), 4),
                  "range": round(max(vals) - min(vals), 4),
                  "bottoming_pct": round(100.0 * bottom / len(vals), 1)}
    return out
```

- [ ] **Step 4: PASS** — `pytest tests/test_suspension.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: suspension metrics"`

---

## Task 13: Метрика — инпуты (`metrics/inputs.py`)

**Files:** Create `src/ire/metrics/inputs.py`, `tests/test_inputs.py`

- [ ] **Step 1: Тест**
```python
# tests/test_inputs.py
from ire.metrics.inputs import input_metrics

def test_trail_braking_detected_when_brake_and_steer_overlap():
    frames = [{"brake": 0.4, "throttle": 0.0, "steer": 0.3} for _ in range(8)] + \
             [{"brake": 0.0, "throttle": 0.8, "steer": 0.1} for _ in range(2)]
    m = input_metrics(frames)
    assert m["trail_brake_pct"] == 80.0
    assert 0.0 <= m["throttle_smoothness"] <= 1.0
```

- [ ] **Step 2: FAIL** — `pytest tests/test_inputs.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/metrics/inputs.py
def input_metrics(frames):
    n = len(frames)
    trail = sum(f["brake"] > 0.1 and abs(f["steer"]) > 0.15 for f in frames)
    # плавность газа: 1 - средний модуль приращения (0..1, выше = плавнее)
    deltas = [abs(frames[i]["throttle"] - frames[i-1]["throttle"]) for i in range(1, n)]
    smooth = 1.0 - (sum(deltas) / len(deltas) if deltas else 0.0)
    return {"trail_brake_pct": round(100.0 * trail / n, 1),
            "throttle_smoothness": round(max(0.0, min(1.0, smooth)), 3)}
```

- [ ] **Step 4: PASS** — `pytest tests/test_inputs.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: input metrics"`

---

## Task 14: Метрика — стабильность (`metrics/consistency.py`)

**Files:** Create `src/ire/metrics/consistency.py`, `tests/test_consistency.py`

- [ ] **Step 1: Тест**
```python
# tests/test_consistency.py
from ire.metrics.consistency import consistency_metrics

def test_lap_time_variance_from_lap_changes():
    # 3 круга: времена восстанавливаются по смене поля lap и t (время сессии)
    frames = []
    for lap, dur in [(1, 90.0), (2, 90.5), (3, 92.0)]:
        frames.append({"lap": lap, "t": sum_so_far if (sum_so_far := 0) else 0})
    m = consistency_metrics([
        {"lap": 1, "t": 0.0}, {"lap": 2, "t": 90.0}, {"lap": 3, "t": 180.5}, {"lap": 4, "t": 272.5}
    ])
    assert m["lap_count"] == 3
    assert m["best_lap"] == 90.0
    assert m["spread"] == round(92.0 - 90.0, 2)
```

- [ ] **Step 2: FAIL** — `pytest tests/test_consistency.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/metrics/consistency.py
def consistency_metrics(frames):
    # время круга = разница session-time между сменами номера круга
    marks = []
    last_lap, last_t = None, None
    for f in frames:
        if f["lap"] != last_lap:
            if last_t is not None:
                marks.append(f["t"] - last_t)
            last_lap, last_t = f["lap"], f["t"]
    laps = [round(x, 2) for x in marks]
    if not laps:
        return {"lap_count": 0, "best_lap": None, "spread": None, "mean": None}
    return {"lap_count": len(laps), "best_lap": min(laps),
            "spread": round(max(laps) - min(laps), 2),
            "mean": round(sum(laps) / len(laps), 2)}
```

- [ ] **Step 4: PASS** — `pytest tests/test_consistency.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: consistency metrics"`

---

## Task 15: Агрегатор симптомов (`metrics/symptoms.py`)

**Files:** Create `src/ire/metrics/symptoms.py`, `tests/test_symptoms.py`

- [ ] **Step 1: Тест на реальной фикстуре**
```python
# tests/test_symptoms.py
import json
from ire.metrics.symptoms import build_symptoms

def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]

def test_symptoms_from_real_stint():
    frames = _load("tests/fixtures/sample_stint.jsonl")
    s = build_symptoms(frames, conditions={"track_temp": frames[0]["track_temp"]})
    for key in ("tire", "balance", "suspension", "inputs", "consistency", "conditions"):
        assert key in s
    json.dump(s, open("tests/fixtures/sample_symptoms.json", "w"), indent=2)
```

- [ ] **Step 2: FAIL** — `pytest tests/test_symptoms.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/metrics/symptoms.py
from ire.metrics.tire import tire_metrics
from ire.metrics.balance import balance_metrics
from ire.metrics.suspension import suspension_metrics
from ire.metrics.inputs import input_metrics
from ire.metrics.consistency import consistency_metrics

def build_symptoms(frames, conditions):
    return {
        "tire": tire_metrics(frames),
        "balance": balance_metrics(frames),
        "suspension": suspension_metrics(frames),
        "inputs": input_metrics(frames),
        "consistency": consistency_metrics(frames),
        "conditions": conditions,
        "frame_count": len(frames),
    }
```

- [ ] **Step 4: PASS** (создаёт `sample_symptoms.json` для Task 16) — `pytest tests/test_symptoms.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: symptoms aggregator"`

---

## Task 16: `explainer` — Claude → рекомендации + дельта

**Files:** Create `src/ire/explainer/explainer.py`, `tests/test_explainer.py`
Использует `tests/fixtures/sample_symptoms.json` (Task 15) и текущий `.sto` (Task 8).

- [ ] **Step 1: Тест на форму ответа (Claude мокается)**
```python
# tests/test_explainer.py
import json
from ire.explainer.explainer import build_prompt, parse_response

def test_prompt_contains_symptoms_and_setup():
    sym = json.load(open("tests/fixtures/sample_symptoms.json"))
    p = build_prompt(sym, setup_fields={"Front tire pressure": 138}, car="Cadillac GTP", track="Watkins Glen")
    assert "Cadillac GTP" in p and "Watkins Glen" in p and "balance" in p

def test_parse_extracts_driving_setup_delta():
    fake = json.dumps({
        "driving": ["Тормози позже в Т1"],
        "setup_changes": [{"field": "Front tire pressure", "from": 138, "to": 140, "why": "перегрев центра"}],
        "delta": {"Front tire pressure": 140},
    })
    r = parse_response(fake)
    assert r["driving"] and r["setup_changes"][0]["field"] == "Front tire pressure"
    assert r["delta"]["Front tire pressure"] == 140
```

- [ ] **Step 2: FAIL** — `pytest tests/test_explainer.py -v`

- [ ] **Step 3: Реализация** (интерфейс стабилен; реализация Claude — сменная)
```python
# src/ire/explainer/explainer.py
import json, os

SYSTEM = (
    "Ты — гоночный инженер по сетапам iRacing. На вход: посчитанные симптомы заезда "
    "и текущие значения сетапа. Меняй ТОЛЬКО переданные поля, в их разумных пределах. "
    "Верни строго JSON: {driving:[...], setup_changes:[{field,from,to,why}], delta:{field:value}}."
)

def build_prompt(symptoms, setup_fields, car, track):
    return (f"Машина: {car}. Трасса: {track}.\n"
            f"Текущий сетап (только эти поля можно менять):\n{json.dumps(setup_fields, ensure_ascii=False, indent=2)}\n"
            f"Симптомы заезда:\n{json.dumps(symptoms, ensure_ascii=False, indent=2)}\n"
            "Дай разбор пилотирования и правки сетапа.")

def parse_response(text):
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])

def explain(symptoms, setup_fields, car="Cadillac GTP", track="Watkins Glen"):
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-8", max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(symptoms, setup_fields, car, track)}],
    )
    return parse_response(msg.content[0].text)
```

- [ ] **Step 4: PASS** — `pytest tests/test_explainer.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: Claude explainer"`

---

## Task 17: Дашборд — сервер (`dashboard/server.py`)

**Files:** Create `src/ire/dashboard/server.py`, `tests/test_server.py`

- [ ] **Step 1: Тест эндпоинтов (FastAPI TestClient)**
```python
# tests/test_server.py
from fastapi.testclient import TestClient
from ire.dashboard.server import app, STATE

def test_live_and_result_endpoints():
    c = TestClient(app)
    STATE["live"] = {"speed": 60.0}
    STATE["result"] = {"driving": ["x"]}
    assert c.get("/api/live").json()["speed"] == 60.0
    assert c.get("/api/result").json()["driving"] == ["x"]
```

- [ ] **Step 2: FAIL** — `pytest tests/test_server.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/dashboard/server.py
from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

app = FastAPI()
STATE = {"live": {}, "result": {}}

@app.get("/api/live")
def live(): return STATE["live"]

@app.get("/api/result")
def result(): return STATE["result"]

@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))
```

- [ ] **Step 4: PASS** — `pytest tests/test_server.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: dashboard server"`

---

## Task 18: Дашборд — UI (`dashboard/static/index.html`)

**Files:** Create `src/ire/dashboard/static/index.html`

- [ ] **Step 1: Сверстать страницу** — две зоны: «Живьё» (опрос `/api/live` каждые 250 мс: скорость, передача, топливо, темп. шин по 4 углам, темп. трассы) и «Разбор» (опрос `/api/result`: список `driving`, таблица `setup_changes` с from→to→why, имя нового `.sto`). Тёмная тема, крупный шрифт для второго экрана.
```html
<!doctype html><meta charset="utf-8"><title>Race Engineer</title>
<style>body{background:#111;color:#eee;font:18px system-ui;margin:0;padding:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:#1c1c1c;border-radius:12px;padding:16px}
table{width:100%;border-collapse:collapse}td,th{padding:6px;border-bottom:1px solid #333;text-align:left}</style>
<div class="grid">
  <div class="card"><h2>Живьё</h2><div id="live"></div></div>
  <div class="card"><h2>Разбор заезда</h2><div id="result"></div></div>
</div>
<script>
async function tick(){
  const l = await (await fetch('/api/live')).json();
  document.getElementById('live').textContent = JSON.stringify(l, null, 1);
  const r = await (await fetch('/api/result')).json();
  document.getElementById('result').textContent = JSON.stringify(r, null, 1);
}
setInterval(tick, 250); tick();
</script>
```

- [ ] **Step 2: Проверить руками** — `uvicorn ire.dashboard.server:app` → открыть `http://localhost:8000` на втором экране, увидеть обе зоны.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "feat: dashboard UI"`

---

## Task 19: Оркестратор (`orchestrator.py`)

**Files:** Create `src/ire/orchestrator.py`, `tests/test_orchestrator.py`

Склейка: пишет live в `STATE`, по закрытию стинта гоняет цепочку metrics→explainer→writer, кладёт результат в `STATE["result"]`.

- [ ] **Step 1: Тест цепочки разбора на фикстуре (Claude мокается)**
```python
# tests/test_orchestrator.py
import json
from ire import orchestrator as orch

def test_analyze_stint_produces_result(monkeypatch):
    frames = [json.loads(l) for l in open("tests/fixtures/sample_stint.jsonl", encoding="utf-8")]
    monkeypatch.setattr(orch, "explain",
        lambda sym, setup, **kw: {"driving": ["ok"], "setup_changes": [], "delta": {}})
    res = orch.analyze_stint(frames, setup_path="tests/fixtures/sample_setup.sto",
                             out_dir=".", conditions={"track_temp": 40})
    assert "symptoms" in res and res["explanation"]["driving"] == ["ok"]
```

- [ ] **Step 2: FAIL** — `pytest tests/test_orchestrator.py -v`

- [ ] **Step 3: Реализация**
```python
# src/ire/orchestrator.py
import os
from ire.metrics.symptoms import build_symptoms
from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import write_sto
from ire.explainer.explainer import explain

def analyze_stint(frames, setup_path, out_dir, conditions):
    symptoms = build_symptoms(frames, conditions)
    setup = read_sto(setup_path)
    explanation = explain(symptoms, setup["fields"])
    new_path = None
    if explanation.get("delta"):
        new_path = os.path.join(out_dir, "cadillacvr_watkinsglen_ai.sto")
        write_sto(setup_path, explanation["delta"], new_path)
    return {"symptoms": symptoms, "explanation": explanation, "new_setup": new_path}
```

- [ ] **Step 4: PASS** — `pytest tests/test_orchestrator.py -v`
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: orchestrator"`

---

## Task 20: `[НУЖЕН СИМ]` Сквозной прогон

- [ ] **Step 1:** Собрать `run.py`: запустить uvicorn-сервер в потоке + live-цикл сборщика (Task 7) пишет `STATE["live"]`; на закрытии стинта вызвать `orchestrator.analyze_stint`, положить в `STATE["result"]`.
- [ ] **Step 2:** В симе: проехать стинт на Watkins → заехать в бокс → на втором экране увидеть разбор и (если Task 4 ✅) новый `.sto` в папке сетапов.
- [ ] **Step 3:** Проверить в гараже, что новый сетап грузится.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat: end-to-end run"`

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки:** collector→Tasks 2,5,6,7; dashboard→17,18; metrics→10–15; explainer→16; setup r/w→3,4,8,9; обработка ошибок→в модулях (короткий стинт→balance/consistency через `samples`/`lap_count`; SDK off→Task 20 live-цикл; .sto reject→Task 4/9 fallback); тестирование→фикстура Task 7 + юнит-тесты; спайк .sto→Task 4. ✅
- **Плейсхолдеры:** единственные намеренные `<...>` — в `config/channels.py` (Task 2): это РЕАЛЬНЫЕ имена каналов, которые добываются спайком, а не выдумываются (требование CLAUDE.md «не фантазировать»). Аналогично поля `.sto` берутся из NOTES (Task 3), а не из головы. ✅
- **Согласованность типов:** нормализованный кадр (см. «Файловая структура») един для Tasks 5–15; `read_sto`→`{"fields","raw"}` потребляется одинаково в 9/16/19; `explain()`/`parse_response` форма `{driving,setup_changes,delta}` едина в 16/19. ✅
