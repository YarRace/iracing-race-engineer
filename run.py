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
from ire.metrics.symptoms import build_symptoms
from ire.collector.live_state import live_frame, is_on_track
from ire.collector.stint_recorder import StintDetector
from ire.dashboard.server import app, STATE


def _serve():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def _connected(ir):
    """Подключён ли SDK к живой сессии iRacing (без падения процесса)."""
    if not (ir.is_initialized and ir.is_connected):
        ir.startup()                                     # пытаемся (пере)подключиться
    return ir.is_initialized and ir.is_connected


def main():
    # Сервер дашборда поднимается СРАЗУ и работает независимо от состояния сима,
    # поэтому http://localhost:8000 открывается ещё до выезда на трассу.
    threading.Thread(target=_serve, daemon=True).start()
    print("Дашборд: http://localhost:8000  (ждёт подключения iRacing…)")
    STATE["live"] = {"status": "ожидание iRacing…"}

    ir = irsdk.IRSDK()
    det = StintDetector()
    frames = []
    try:
        while True:
            if not _connected(ir):
                STATE["live"] = {"status": "ожидание iRacing… (запусти сим и сядь в машину)"}
                time.sleep(1)
                continue
            ir.freeze_var_buffer_latest()
            state = det.update(on_track=is_on_track(ir))
            if state == "running":
                f = live_frame(ir)
                STATE["live"] = f
                frames.append(f)
            elif state == "closed" and frames:
                print(f"Стинт закрыт ({len(frames)} кадров) → анализ…")
                conditions = {"track_temp": frames[0]["track_temp"]}
                # симптомы (метрики) считаем всегда — они не зависят от Claude
                STATE["result"] = {"symptoms": build_symptoms(frames, conditions)}
                print("Метрики посчитаны. Запрашиваю разбор у Claude…")
                try:                                      # explainer опционален (нужен ключ)
                    res = orchestrator.analyze_stint(
                        frames,
                        setup_path=ir["CarSetup"],        # живой CarSetup как dict
                        conditions=conditions,
                    )
                    STATE["result"] = res
                    print("Готово. Разбор на дашборде.")
                except Exception as e:                    # анализ не должен ронять цикл
                    STATE["result"]["explanation_error"] = str(e)
                    print("Разбор от Claude недоступен (метрики на дашборде есть):", e)
                frames = []
                det = StintDetector()                    # готов к следующему стинту
            time.sleep(1 / 60)
    finally:
        ir.shutdown()


if __name__ == "__main__":
    main()
