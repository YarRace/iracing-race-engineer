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

STATE["race"] = {
    "position": 4, "class_position": 2,
    "cur_lap_time": 38.2, "last_lap_time": 95.81, "best_lap_time": 94.32, "delta_best": 0.4,
    "rpm": 8100, "shift_pct": 0.7, "shift_rpm": 8550, "blink_rpm": 8725, "abs_active": False,
    "flags": [{"key": "green", "label": "зелёный"}],
    "warnings": [],
    "wind_vel": 2.4, "wind_dir": 1.2, "humidity": 0.45, "skies": 1, "track_wetness": 1,
    "energy_pct": 0.82, "deploy_pct": 0.35,
    "gap_ahead": 1.8, "gap_behind": 0.9, "lap": 12, "on_pit": False,
    "standing_ahead": 5.4, "standing_behind": 3.1,
    "predicted": 94.9,
    "lap_log": [{"lap": 9, "time": 96.1, "sectors": [28.5, 34.2, 33.4]},
                {"lap": 10, "time": 95.4, "sectors": [28.1, 34.0, 33.3]},
                {"lap": 11, "time": 94.32, "sectors": [27.8, 33.6, 32.9]},
                {"lap": 12, "time": 95.81, "sectors": [28.3, 34.1, 33.4]}],
}

print("Демо-дашборд: http://localhost:8000  (Ctrl+C — выход)")
uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
