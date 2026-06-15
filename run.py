"""Задача 20: сквозной прогон на втором экране.

Поднимает дашборд (FastAPI на :8000) в фоне и крутит live-цикл сборщика:
пишет текущий кадр в STATE["live"]; по закрытии стинта (заезд в бокс) гоняет
metrics → explainer → manual-changes и кладёт результат в STATE["result"].

Требует: запущенный iRacing и переменную окружения ANTHROPIC_API_KEY (для explainer).
Run: python run.py  → открыть http://localhost:8000 на втором экране.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import irsdk
import uvicorn

from ire import orchestrator
from ire.collector.live_state import live_frame, is_on_track
from ire.collector.stint_recorder import StintDetector
from ire.dashboard.server import app, STATE


def _serve():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def main():
    threading.Thread(target=_serve, daemon=True).start()
    print("Дашборд: http://localhost:8000")

    ir = irsdk.IRSDK()
    assert ir.startup(), "iRacing не запущен / SDK недоступен"
    det = StintDetector()
    frames = []
    try:
        while True:
            ir.freeze_var_buffer_latest()
            state = det.update(on_track=is_on_track(ir))
            if state == "running":
                f = live_frame(ir)
                STATE["live"] = f
                frames.append(f)
            elif state == "closed" and frames:
                print(f"Стинт закрыт ({len(frames)} кадров) → анализ…")
                res = orchestrator.analyze_stint(
                    frames,
                    setup_path=ir["CarSetup"],            # живой CarSetup как dict
                    conditions={"track_temp": frames[0]["track_temp"]},
                )
                STATE["result"] = res
                print("Готово. Разбор на дашборде.")
                frames = []
                det = StintDetector()                    # готов к следующему стинту
            time.sleep(1 / 60)
    finally:
        ir.shutdown()


if __name__ == "__main__":
    main()
