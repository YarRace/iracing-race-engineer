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
from ire.explainer.explainer import warm_up
from ire.metrics.symptoms import build_symptoms
from ire.metrics.strategy import StrategyTracker
from ire.collector.live_state import (live_frame, is_on_track, strategy_inputs,
                                       fuel_capacity, damage_status)
from ire.collector.race_state import race_extras, SectorTimer, sector_starts
from ire.voice.engineer import VoiceEngineer, announce
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
    tracker = None
    sector_timer = None
    frames = []
    lap_log = []          # история времён кругов (для блока «Лог кругов»)
    last_logged_lap = None
    voice = VoiceEngineer()
    best_seen = None      # для озвучки личного рекорда
    try:
        while True:
            if not _connected(ir):
                STATE["live"] = {"status": "ожидание iRacing… (запусти сим и сядь в машину)"}
                time.sleep(1)
                continue
            ir.freeze_var_buffer_latest()
            if tracker is None:                              # инициализация на первом подключении
                tracker = StrategyTracker(tank_capacity=fuel_capacity(ir))
                sector_timer = SectorTimer(sector_starts(ir))  # [] если трасса без секторов
                # прогрев LLM в фоне, пока едешь — первый разбор будет быстрым
                threading.Thread(target=warm_up, daemon=True).start()
                print("Прогрев модели в фоне…")
            # стратегия считается всегда, пока в сессии (топливо/износ по кругам)
            try:
                tracker.update(**strategy_inputs(ir))
                STATE["strategy"] = tracker.snapshot()
                STATE["damage"] = damage_status(ir)
                race = race_extras(ir)
                sector_timer.update(ir["LapDistPct"], ir["SessionTime"])
                # лог кругов: при смене номера круга фиксируем время + сектора
                if race["lap"] != last_logged_lap:
                    if last_logged_lap is not None and race["last_lap_time"] and race["last_lap_time"] > 0:
                        lap_log.append({"lap": last_logged_lap, "time": round(race["last_lap_time"], 2),
                                        "sectors": sector_timer.lap_sectors()})
                    sector_timer.reset()
                    last_logged_lap = race["lap"]
                race["lap_log"] = lap_log[-20:]              # последние 20 кругов
                STATE["race"] = race
                # голосовой инженер: флаги, предупреждения, мало топлива
                announce(voice, race, STATE["strategy"])
                # личный рекорд круга
                blt = race.get("best_lap_time")
                if blt and blt > 0:
                    if best_seen is not None and blt < best_seen - 0.01:
                        voice.say("Личный рекорд", key="best")
                    best_seen = blt if best_seen is None else min(best_seen, blt)
            except Exception as e:
                if not getattr(main, "_strat_warned", False):
                    print("Стратегия/гонка: ошибка чтения каналов:", e)
                    main._strat_warned = True
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
                    voice.say("Разбор заезда готов")
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
