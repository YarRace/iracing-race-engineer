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
                                       fuel_capacity, damage_status, session_identity,
                                       tire_wear_by_corner, session_info)
from ire.collector.race_state import (race_extras, SectorTimer, sector_starts,
                                       build_relative)
from ire.collector.track_map import TrackMapBuilder, save_map, load_map
from ire.collector.standings import build_standings
from ire.collector.stint_recorder import StintDetector
from ire.metrics.consistency import consistency_metrics
from ire.storage import history
from ire.dashboard.server import app, STATE


def _serve():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def _connected(ir):
    """Подключён ли SDK к живой сессии iRacing (без падения процесса)."""
    if not (ir.is_initialized and ir.is_connected):
        ir.startup()                                     # пытаемся (пере)подключиться
    return ir.is_initialized and ir.is_connected


def _session_key(ir):
    """Идентификатор сессии — меняется при заходе в другую сессию/смене фазы."""
    wk = ir["WeekendInfo"] or {}
    return (ir["SessionNum"], wk.get("SubSessionID"), ir["SessionUniqueID"])


def _analyze_bg(frames, setup, conditions):
    """Разбор стинта В ФОНЕ — не блокирует live-цикл (LLM считается минуты)."""
    try:
        STATE["result"] = {"symptoms": build_symptoms(frames, conditions), "analyzing": True}
        res = orchestrator.analyze_stint(frames, setup_path=setup, conditions=conditions)
        STATE["result"] = res
        print("Готово. Разбор на дашборде.")
    except Exception as e:
        r = STATE.get("result") or {}
        r["analyzing"] = False
        r["explanation_error"] = str(e)
        STATE["result"] = r
        print("Разбор от модели недоступен (метрики есть):", e)


def main():
    # Сервер дашборда поднимается СРАЗУ и работает независимо от состояния сима,
    # поэтому http://localhost:8000 открывается ещё до выезда на трассу.
    threading.Thread(target=_serve, daemon=True).start()
    print("Дашборд: http://localhost:8000  (ждёт подключения iRacing…)")
    STATE["live"] = {"status": "ожидание iRacing…"}

    ir = irsdk.IRSDK()
    hist = history.connect()                      # база истории (круги/стинты) — Фаза 1
    print(f"История: {history.default_path()}")
    det = StintDetector()
    tracker = None
    sector_timer = None
    tmb = None            # построитель карты трассы
    ident = {}            # трасса/машина/сессия — для привязки сохранённых кругов
    frames = []
    lap_log = []          # история времён кругов (для блока «Лог кругов»)
    last_logged_lap = None
    last_sess = None      # ключ сессии — для авто-сброса при смене
    frame_n = 0           # счётчик кадров для троттлинга standings
    try:
        while True:
            if not _connected(ir):
                STATE["live"] = {"status": "ожидание iRacing… (запусти сим и сядь в машину)"}
                time.sleep(1)
                continue
            ir.freeze_var_buffer_latest()
            # авто-сброс при заходе в ДРУГУЮ сессию (новая гонка/практика/смена пилота)
            sess = _session_key(ir)
            if sess != last_sess:
                if last_sess is not None:
                    print("Новая сессия — сбрасываю данные дашборда.")
                tracker = None
                sector_timer = None
                tmb = None
                frames = []
                lap_log = []
                last_logged_lap = None
                det = StintDetector()
                STATE["result"] = {}
                STATE["strategy"] = {}
                STATE["race"] = {}
                STATE["trackmap"] = {}
                last_sess = sess
            if tracker is None:                              # инициализация на первом подключении
                tracker = StrategyTracker(tank_capacity=fuel_capacity(ir))
                sector_timer = SectorTimer(sector_starts(ir))  # [] если трасса без секторов
                ident = session_identity(ir)                 # трасса/машина для истории
                tmb = TrackMapBuilder()
                if ident.get("track"):
                    print(f"Трасса: {ident['track_display']} / машина: {ident['car']}")
                    cached = load_map(ident["track"])         # карта уже построена ранее?
                    if cached:
                        tmb.load(cached)
                        STATE["trackmap"] = {"points": cached}
                        print("Карта трассы загружена из кэша.")
                # прогрев LLM в фоне, пока едешь — первый разбор будет быстрым
                threading.Thread(target=warm_up, daemon=True).start()
                print("Прогрев модели в фоне…")
            # стратегия считается всегда, пока в сессии (топливо/износ по кругам)
            try:
                tracker.update(**strategy_inputs(ir))
                STATE["strategy"] = tracker.snapshot()
                STATE["damage"] = damage_status(ir)
                STATE["wear"] = tire_wear_by_corner(ir)      # износ по углам
                # live-кадр ПОСТОЯННО (не только когда сам за рулём) — чтобы в эндурансе
                # гаражный вид был живым, пока машину ведёт напарник
                STATE["live"] = live_frame(ir)
                race = race_extras(ir)
                sector_timer.update(ir["LapDistPct"], ir["SessionTime"])
                # карта трассы: копим форму по кругу, только пока на трассе
                if is_on_track(ir):
                    tmb.update(ir["LapDistPct"], ir["Speed"], ir["YawRate"], ir["SessionTime"])
                if tmb.new:                                  # круг завершён — карта готова
                    STATE["trackmap"] = tmb.snapshot()
                    if ident.get("track"):
                        save_map(ident["track"], tmb.map)
                        print("Карта трассы построена и сохранена.")
                    tmb.new = False
                # лог кругов: при смене номера круга фиксируем время + сектора
                if race["lap"] != last_logged_lap:
                    if last_logged_lap is not None and race["last_lap_time"] and race["last_lap_time"] > 0:
                        lap_time = round(race["last_lap_time"], 2)
                        sectors = sector_timer.lap_sectors()
                        lap_log.append({"lap": last_logged_lap, "time": lap_time, "sectors": sectors})
                        if ident.get("track"):               # сохраняем круг в историю (Фаза 1)
                            try:
                                history.save_lap(hist, ident, last_logged_lap, lap_time, sectors)
                            except Exception as e:
                                if not getattr(main, "_hist_warned", False):
                                    print("История: не удалось сохранить круг:", e)
                                    main._hist_warned = True
                    sector_timer.reset()
                    last_logged_lap = race["lap"]
                race["lap_log"] = lap_log[-20:]              # последние 20 кругов
                STATE["race"] = race
                frame_n += 1
                if frame_n % 15 == 0:                        # таблица + relative ~4 раза/сек
                    STATE["standings"] = build_standings(ir)
                    STATE["relative"] = build_relative(ir)   # Relative / радар / трек-ринг
                if frame_n % 120 == 0:                       # инфо о сессии + рекорд ~1/2сек
                    info = session_info(ir)
                    info["record"] = (history.best_lap(hist, ident["track"], ident["car"])
                                      if ident.get("track") else None)
                    STATE["session"] = info
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
                # разбор уходит В ФОН — живой цикл не зависает на время инференса LLM
                print(f"Стинт закрыт ({len(frames)} кадров) → разбор в фоне…")
                # сводка стинта в историю (Фаза 1) — считается детерминированно, без LLM
                if ident.get("track"):
                    try:
                        cm = consistency_metrics(frames)
                        history.save_stint(hist, ident, {
                            "laps": cm["lap_count"], "best_lap": cm["best_lap"],
                            "mean_lap": cm["mean"], "spread": cm["spread"],
                            "incidents": (STATE.get("damage") or {}).get("incidents"),
                        })
                    except Exception as e:
                        print("История: не удалось сохранить стинт:", e)
                conditions = {"track_temp": frames[0]["track_temp"]}
                threading.Thread(
                    target=_analyze_bg,
                    args=(list(frames), ir["CarSetup"], conditions),
                    daemon=True,
                ).start()
                frames = []
                det = StintDetector()                    # готов к следующему стинту
            time.sleep(1 / 60)
    finally:
        ir.shutdown()


if __name__ == "__main__":
    main()
