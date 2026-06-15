"""Демо дашборда БЕЗ сима: наполняет STATE данными реального заезда и поднимает сервер.

Удобно посмотреть/покрутить UI в браузере без iRacing.
Run: python spikes/demo_dashboard.py  → открыть http://localhost:8000
"""
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _ROOT)

import uvicorn
from ire.dashboard.server import app, STATE
from ire.setup.sto_reader import read_sto
from ire.setup.sto_writer import build_setup_sheet

# живой кадр — самый быстрый момент реального стинта (для наглядных приборов)
frames = [json.loads(l) for l in open(
    os.path.join(_ROOT, "tests/fixtures/sample_stint.jsonl"), encoding="utf-8")]
STATE["live"] = max(frames, key=lambda f: f["speed"])

# разбор — реальные симптомы + пример рекомендаций (как вернула бы LLM)
symptoms = json.load(open(
    os.path.join(_ROOT, "tests/fixtures/sample_symptoms.json"), encoding="utf-8"))
STATE["result"] = {
    "symptoms": symptoms,
    "explanation": {
        "driving": [
            "Устойчивый недоруль во всех фазах — добавляем переднего сцепления.",
            "Баланс тормозов в норме, можно слегка проверить и подстроить.",
        ],
        "setup_changes": [],
        "delta": {},
    },
    "manual_changes": [
        {"field": "TiresAero.LeftFront.StartingPressure", "from": "152 kPa", "to": "148 kPa",
         "why": "снизить давление передней шины для увеличения переднего сцепления"},
        {"field": "TiresAero.RightFront.StartingPressure", "from": "152 kPa", "to": "148 kPa",
         "why": "снизить давление передней шины для увеличения переднего сцепления"},
        {"field": "Chassis.Rear.ArbSize", "from": "Medium", "to": "Hard",
         "why": "ужесточить задний стабилизатор против недоруля"},
    ],
}

# полный сетап-лист (шпаргалка) на основе реального CarSetup + те же правки
_setup = read_sto(os.path.join(_ROOT, "tests/fixtures/sample_setup.json"))
STATE["result"]["setup_sheet"] = build_setup_sheet(_setup, {
    "TiresAero.LeftFront.StartingPressure": "148 kPa",
    "TiresAero.RightFront.StartingPressure": "148 kPa",
    "Chassis.Rear.ArbSize": "Hard",
})

# пример стратегии (как считал бы StrategyTracker на ходу)
STATE["strategy"] = {
    "fuel": 38.0, "tank": 89.0, "avg_burn": 3.05, "last_burn": 3.1,
    "avg_lap_time": 96.5, "laps_to_go": 14, "laps_on_fuel": 12.5,
    "fuel_to_add": 6.2, "pit_needed_for_fuel": True,
    "tire_min": 0.62, "tire_wear_per_lap": 0.05, "tire_laps_left": 6.4, "change_tires": False,
}

STATE["damage"] = {
    "repair_sec": 0.0, "opt_repair_sec": 0.0,
    "fast_repair_available": 1, "fast_repair_used": 0, "incidents": 2, "damaged": False,
}

print("Демо-дашборд: http://localhost:8000  (Ctrl+C — выход)")
uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
