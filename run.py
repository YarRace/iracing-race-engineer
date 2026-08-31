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

# ДО импорта остального: на старом Python падение выглядит как SyntaxError
# в случайном файле, и человек решает, что сломана программа, а не версия.
from ire import preflight                                        # noqa: E402
preflight.check(extra=[("irsdk", "pyirsdk")])

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
from ire.collector.track_map import (TrackMapBuilder, save_map, load_map,
                                     from_garage61 as track_map_from_g61)
from ire.collector import track_svg
from ire.collector.standings import build_standings, strength_of_field, cars_in_class
from ire.collector.stint_recorder import StintDetector
from ire.metrics.consistency import consistency_metrics
from ire.storage import history, laps as lap_store
from ire.dashboard.server import app, STATE


def _serve():
    # Порт из окружения: 8000 занят, когда инженер уже запущен, и второй
    # экземпляр раньше просто падал на bind, продолжая крутить цикл сима
    # без дашборда — со стороны это выглядело как «запустился и молчит».
    port = int(os.environ.get("IRE_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def _connected(ir):
    """Подключён ли SDK к живой сессии iRacing (без падения процесса)."""
    if not (ir.is_initialized and ir.is_connected):
        ir.startup()                                     # пытаемся (пере)подключиться
    return ir.is_initialized and ir.is_connected


def _session_key(ir):
    """Идентификатор сессии — меняется при заходе в другую сессию/смене фазы."""
    wk = ir["WeekendInfo"] or {}
    return (ir["SessionNum"], wk.get("SubSessionID"), ir["SessionUniqueID"])


_lap_writers = []     # живые потоки записи — их дожидаемся на выходе


def _save_lap_bg(ident, lap_num, frames):
    """Кладёт завершённый круг на диск в фоне.

    В фоне, потому что живой цикл крутится 60 раз в секунду: сжатие и запись
    даже на 30 КБ дают заметную паузу, а пауза в цикле — это рывок телеметрии
    в оверлее ровно в момент пересечения линии.
    """
    def work(fr):
        try:
            t = lap_store.lap_time(fr)
            if t is None:
                return
            path = lap_store.save_lap(lap_store.default_root(), ident, lap_num, t, fr)
            if path:
                print(f"Lap {lap_num} saved ({t:.3f}s) -> {path.name}")
        except Exception as e:
            print("Lap storage: failed to save lap:", e)

    th = threading.Thread(target=work, args=(list(frames),), daemon=True)
    th.start()
    _lap_writers[:] = [t for t in _lap_writers if t.is_alive()] + [th]


def _flush_lap_writers(timeout=5.0):
    """Дать записи кругов договорить перед выходом.

    Потоки демонические: без этого выход из программы убивает их на месте,
    и круг, пересечённый за секунду до закрытия, пропадает. Ждём не больше
    timeout — зависшая запись не должна держать программу.
    """
    for th in [t for t in _lap_writers if t.is_alive()]:
        th.join(timeout)


def _analyze_bg(frames, setup, conditions, identity=None):
    """Разбор стинта В ФОНЕ — не блокирует live-цикл (LLM считается минуты)."""
    try:
        STATE["result"] = {"symptoms": build_symptoms(frames, conditions), "analyzing": True}
        res = orchestrator.analyze_stint(frames, setup_path=setup, conditions=conditions,
                                         identity=identity)
        STATE["result"] = res
        print("Done. Analysis is on the dashboard.")
    except Exception as e:
        r = STATE.get("result") or {}
        r["analyzing"] = False
        r["explanation_error"] = str(e)
        STATE["result"] = r
        print("Model analysis unavailable (metrics are there):", e)


def main():
    # Сервер дашборда поднимается СРАЗУ и работает независимо от состояния сима,
    # поэтому http://localhost:8000 открывается ещё до выезда на трассу.
    threading.Thread(target=_serve, daemon=True).start()
    print("Dashboard: http://localhost:8000  (waiting for iRacing…)")
    STATE["live"] = {"status": "waiting for iRacing…"}

    ir = irsdk.IRSDK()
    hist = history.connect()                      # база истории (круги/стинты) — Фаза 1
    print(f"History: {history.default_path()}")
    det = StintDetector()
    tracker = None
    sector_timer = None
    tmb = None            # построитель карты трассы
    ident = {}            # трасса/машина/сессия — для привязки сохранённых кругов
    frames = []
    lap_frames = []       # кадры ТЕКУЩЕГО круга — пишутся на диск по его завершении
    cur_lap = None        # номер круга, который сейчас пишем
    lap_log = []          # история времён кругов (для блока «Лог кругов»)
    last_logged_lap = None
    last_sess = None      # ключ сессии — для авто-сброса при смене
    frame_n = 0           # счётчик кадров
    record = None         # кэш рекорда трассы (запрос к БД — дорогой, обновляем реже)
    official_map = False  # есть официальная геометрия трассы (тогда не строим из телеметрии)
    sof_frozen = None     # SoF снимаем ОДИН раз на входе в сессию (см. ниже)
    try:
        while True:
            if not _connected(ir):
                STATE["live"] = {"status": "waiting for iRacing… (start the sim and get in the car)"}
                time.sleep(1)
                continue
            ir.freeze_var_buffer_latest()
            # авто-сброс при заходе в ДРУГУЮ сессию (новая гонка/практика/смена пилота)
            sess = _session_key(ir)
            if sess != last_sess:
                if last_sess is not None:
                    print("New session — resetting dashboard data.")
                tracker = None
                sector_timer = None
                tmb = None
                frames = []
                lap_frames = []
                cur_lap = None
                lap_log = []
                last_logged_lap = None
                det = StintDetector()
                STATE["result"] = {}
                STATE["strategy"] = {}
                STATE["race"] = {}
                STATE["trackmap"] = {}
                record = None                                # рекорд перечитаем для новой трассы
                official_map = False
                sof_frozen = None                            # новая сессия — новый состав, новый SoF
                last_sess = sess
            if tracker is None:                              # инициализация на первом подключении
                tracker = StrategyTracker(tank_capacity=fuel_capacity(ir))
                sector_timer = SectorTimer(sector_starts(ir))  # [] если трасса без секторов
                ident = session_identity(ir)                 # трасса/машина для истории
                tmb = TrackMapBuilder()
                official_map = False
                if ident.get("track"):
                    print(f"Track: {ident['track_display']} / car: {ident['car']}")
                    tid = (ir["WeekendInfo"] or {}).get("TrackID")
                    # официальное имя трассы едет вместе с картой — им подписываем её в UI
                    tinfo = {"track": ident.get("track_display") or ident.get("track"),
                             "config": ident.get("config")}
                    off = track_svg.fetch(tid)                # ОФИЦИАЛЬНАЯ геометрия (полная/точная)
                    if off:
                        STATE["trackmap"] = {"points": off, "source": "official", **tinfo}
                        official_map = True
                        print(f"Track map: OFFICIAL iRacing (track_id {tid}, {len(off)} points).")
                    else:
                        reason = track_svg.LAST_ERROR or "?"  # почему официальная не скачалась
                        # Координаты Garage 61 — вторая попытка перед своей
                        # картой: своя копит ошибку по кругу и к финишу не
                        # сходится сама с собой, а Lat/Lon дают форму такой,
                        # какая трасса есть. Тянем в фоне: сеть не должна
                        # задерживать выезд на трассу.
                        def _try_garage61(tr=ident["track"], ca=ident.get("car"),
                                          ti=dict(tinfo)):
                            pts = track_map_from_g61(tr, ca)
                            if pts and STATE.get("trackmap", {}).get("source") != "official":
                                STATE["trackmap"] = {"points": pts,
                                                     "source": "Garage 61 (real coordinates)", **ti}
                                save_map(tr + " g61", pts)
                                print(f"Track map: Garage 61 coordinates ({len(pts)} points).")
                        threading.Thread(target=_try_garage61, daemon=True).start()

                        cached = load_map(ident["track"] + " g61") or load_map(ident["track"])
                        if cached:
                            tmb.load(cached)
                            STATE["trackmap"] = {"points": cached, "source": f"own (cached) · no official: {reason}", **tinfo}
                        print(f"Track map: NO official one (track_id={tid}, {reason}) → Garage 61 / telemetry.")
                # прогрев LLM в фоне, пока едешь — первый разбор будет быстрым
                threading.Thread(target=warm_up, daemon=True).start()
                print("Warming up the model in the background…")
            # стратегия считается всегда, пока в сессии (топливо/износ по кругам)
            try:
                tracker.update(**strategy_inputs(ir))
                STATE["strategy"] = tracker.snapshot()
                STATE["damage"] = damage_status(ir)
                STATE["wear"] = tire_wear_by_corner(ir)      # износ по углам
                # live-кадр ПОСТОЯННО (не только когда сам за рулём) — чтобы в эндурансе
                # гаражный вид был живым, пока машину ведёт напарник
                STATE["live"] = live_frame(ir)
                STATE["live"]["on_track"] = is_on_track(ir)   # для «прятать оверлеи вне трассы»
                race = race_extras(ir)
                sector_timer.update(ir["LapDistPct"], ir["SessionTime"])
                # карта трассы из телеметрии — ТОЛЬКО если нет официальной (полной/точной)
                if not official_map:
                    if is_on_track(ir):
                        tmb.update(ir["LapDistPct"], ir["Speed"], ir["YawRate"], ir["SessionTime"])
                    if tmb.new:                              # круг завершён — карта готова
                        snap = tmb.snapshot() or {}
                        snap["source"] = "own (telemetry)"
                        snap["track"] = ident.get("track_display") or ident.get("track")
                        snap["config"] = ident.get("config")
                        STATE["trackmap"] = snap
                        if ident.get("track"):
                            save_map(ident["track"], tmb.map)
                            print("Track map built and saved.")
                    tmb.new = False
                # лог кругов: при смене номера круга фиксируем время + сектора
                if race["lap"] != last_logged_lap:
                    if last_logged_lap is not None and race["last_lap_time"] and race["last_lap_time"] > 0:
                        lap_time = round(race["last_lap_time"], 2)
                        sectors = sector_timer.lap_sectors()
                        # температура трассы кладётся вместе с кругом: она
                        # объясняет, почему круг медленнее соседнего, а задним
                        # числом её уже не восстановить
                        lap_log.append({"lap": last_logged_lap, "time": lap_time,
                                        "sectors": sectors,
                                        "track_temp": f.get("track_temp"),
                                        "fuel": f.get("fuel")})
                        if ident.get("track"):               # сохраняем круг в историю (Фаза 1)
                            try:
                                history.save_lap(hist, ident, last_logged_lap, lap_time, sectors)
                            except Exception as e:
                                if not getattr(main, "_hist_warned", False):
                                    print("History: failed to save lap:", e)
                                    main._hist_warned = True
                    sector_timer.reset()
                    last_logged_lap = race["lap"]
                race["lap_log"] = lap_log[-20:]              # последние 20 кругов
                STATE["race"] = race
                frame_n += 1
                # рекорд из БД — дорого, поэтому КЭШ: берём один раз и обновляем ~1/2сек
                # (рекорд меняется максимум раз в круг, чаще спрашивать БД смысла нет)
                if ident.get("track") and (record is None or frame_n % 120 == 0):
                    record = history.best_lap(hist, ident["track"], ident["car"])
                # ВСЕ каналы для оверлея/дашборда — часто и РАВНОМЕРНО (~20/сек, выше частоты
                # опроса оверлея), чтобы живым был КАЖДЫЙ виджет, а не «пара частичек».
                # 20/сек (а не 60) — баланс: плавно, но CPU не отбираем у iRacing
                if frame_n % 3 == 0:
                    st = build_standings(ir)
                    STATE["standings"] = st
                    STATE["relative"] = build_relative(ir)   # Relative / радар / трек-мапа / стинт
                    info = session_info(ir)
                    info["record"] = record
                    # SoF снимаем ОДИН раз, на входе в сессию — как показывает сам iRacing.
                    # Пересчёт каждый кадр заставлял цифру прыгать от захода/выхода пилотов.
                    if sof_frozen is None:
                        irs = [r["irating"] for r in st if r.get("irating")]
                        if len(irs) >= 2:
                            sof_frozen = strength_of_field(irs)
                            print(f"Session SoF: {sof_frozen} ({len(irs)} drivers).")
                    info["sof"] = sof_frozen
                    info["cars_class"] = cars_in_class(st)   # live: сошедшие вычитаются
                    info["cars_total"] = len(st)
                    info["car_class"] = next((r.get("car_class") for r in st if r.get("is_player")), None)
                    STATE["session"] = info
            except Exception as e:
                if not getattr(main, "_strat_warned", False):
                    print("Strategy/race: channel read error:", e)
                    main._strat_warned = True
            state = det.update(on_track=is_on_track(ir))
            if state == "running":
                f = live_frame(ir)
                f["on_track"] = True                         # едем сами → точно на трассе
                STATE["live"] = f
                frames.append(f)
                # Телеметрию пишем ПОКРУГОВО, а не в конце стинта: 24-часовая
                # гонка иначе копила бы миллионы кадров в памяти и теряла всё
                # при вылете сима.
                if f.get("lap") != cur_lap:
                    if cur_lap is not None and lap_frames and ident.get("track"):
                        _save_lap_bg(ident, cur_lap, lap_frames)
                    cur_lap = f.get("lap")
                    lap_frames = []
                lap_frames.append(f)
            elif state == "closed" and frames:
                # разбор уходит В ФОН — живой цикл не зависает на время инференса LLM
                print(f"Stint closed ({len(frames)} frames) → analysis in background…")
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
                        print("History: failed to save stint:", e)
                conditions = {"track_temp": frames[0]["track_temp"]}
                threading.Thread(
                    target=_analyze_bg,
                    args=(list(frames), ir["CarSetup"], conditions, dict(ident)),
                    daemon=True,
                ).start()
                frames = []
                lap_frames = []                          # круг оборван заездом в боксы
                cur_lap = None
                det = StintDetector()                    # готов к следующему стинту
            time.sleep(1 / 60)
    finally:
        _flush_lap_writers()
        ir.shutdown()


if __name__ == "__main__":
    main()
