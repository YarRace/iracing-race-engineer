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

print("Демо-дашборд: http://localhost:8000  (Ctrl+C — выход)")
uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
