import os

import pytest
from fastapi.testclient import TestClient
from ire.dashboard.server import app, STATE
from ire.storage import history

def test_live_and_result_endpoints():
    c = TestClient(app)
    STATE["live"] = {"speed": 60.0}
    STATE["result"] = {"driving": ["x"]}
    assert c.get("/api/live").json()["speed"] == 60.0
    assert c.get("/api/result").json()["driving"] == ["x"]

def test_records_endpoint(tmp_path):
    # эндпоинт читает базу через history.connect(); направляем её в temp-файл
    os.environ["IRE_DB_PATH"] = str(tmp_path / "h.db")
    try:
        conn = history.connect()
        history.save_lap(conn, {"track": "t", "track_display": "T", "config": None,
                                "car": "c", "car_path": "cp", "session_type": "Race"}, 1, 90.0)
        conn.close()
        data = TestClient(app).get("/api/records").json()
        assert data and data[0]["best_lap"] == 90.0 and data[0]["car"] == "c"
    finally:
        del os.environ["IRE_DB_PATH"]


def _seed(tmp_path, laps=3):
    """Готовит временную базу с кругами и стинтом. Возвращает identity."""
    os.environ["IRE_DB_PATH"] = str(tmp_path / "h.db")
    ident = {"track": "monza full", "track_display": "Monza", "config": None,
             "car": "Porsche 963 GTP", "car_path": "porsche963", "session_type": "Race"}
    conn = history.connect()
    for i in range(laps):
        history.save_lap(conn, ident, i + 1, 94.0 - i * 0.1)
    history.save_stint(conn, ident, {"laps": laps, "best_lap": 93.8, "mean_lap": 93.9,
                                     "spread": 0.2, "incidents": 0})
    conn.close()
    return ident


def test_history_endpoint_returns_laps_over_time(tmp_path):
    ident = _seed(tmp_path)
    try:
        r = TestClient(app).get("/api/history",
                                params={"track": ident["track"], "car": ident["car"]})
        data = r.json()
        assert r.status_code == 200 and len(data) == 3
        # порядок по времени: график прогресса рисуется слева направо
        assert [round(x["lap_time"], 1) for x in data] == [94.0, 93.9, 93.8]
        assert "ts" in data[0]
    finally:
        del os.environ["IRE_DB_PATH"]


def test_history_without_params_is_empty_not_error(tmp_path):
    _seed(tmp_path)
    try:
        r = TestClient(app).get("/api/history")
        # без трассы и машины показывать нечего, но и падать нельзя — карточка
        # дашборда дёргает эндпоинт до того, как появится сессия
        assert r.status_code == 200 and r.json() == []
    finally:
        del os.environ["IRE_DB_PATH"]


def test_stints_endpoint(tmp_path):
    _seed(tmp_path)
    try:
        data = TestClient(app).get("/api/stints").json()
        assert len(data) == 1 and data[0]["laps"] == 3
    finally:
        del os.environ["IRE_DB_PATH"]


def test_limit_is_clamped(tmp_path):
    _seed(tmp_path, laps=5)
    try:
        c = TestClient(app)
        # чужой запрос с limit=999999 не должен тащить всю базу в память
        assert len(c.get("/api/history", params={"track": "monza full",
                                                 "car": "Porsche 963 GTP",
                                                 "limit": 2}).json()) == 2
        assert c.get("/api/stints", params={"limit": 0}).json() == []
    finally:
        del os.environ["IRE_DB_PATH"]


def test_tokens_css_is_served():
    r = TestClient(app).get("/tokens.css")
    # index.html подключает этот файл; если он не отдаётся, дашборд теряет
    # всю палитру и становится чёрно-белым
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    assert "--accent" in r.text and "--best" in r.text


def test_site_pages_render():
    c = TestClient(app)
    for path, must in (("/about", "A race engineer"),
                       ("/catalog", "Widgets and cards"),
                       ("/news", "What changed")):
        r = c.get(path)
        assert r.status_code == 200, path
        assert must in r.text, path
        # все страницы берут палитру из того же файла, что и дашборд
        assert "/tokens.css" in r.text, path


def test_catalog_numbers_come_from_code():
    """Цифры на сайте должны совпадать с реальным реестром виджетов, иначе
    каталог начнёт врать, как врал docstring про 31 виджет вместо 42."""
    import html as _html

    from ire.dashboard import site
    if not site.load_catalog()["widgets"]:
        pytest.skip("каталог не собран: python tools/build_catalog.py")

    from overlay.widgets import WIDGETS
    text = TestClient(app).get("/catalog").text
    assert str(len(WIDGETS)) in text, "число виджетов на странице разошлось с реестром"
    for cls in WIDGETS[:5]:
        # названия на странице экранированы: «Position & gaps» -> «Position &amp; gaps»
        assert _html.escape(cls.TITLE) in text


def test_news_rss_is_valid_xml():
    import xml.etree.ElementTree as ET
    r = TestClient(app).get("/news/rss.xml")
    assert r.status_code == 200 and "rss" in r.headers["content-type"]
    root = ET.fromstring(r.text)          # падает, если XML сломан
    assert root.tag == "rss"
    assert root.find("./channel/title") is not None


def test_plural_on_site():
    """«1 widgets» сразу выдаёт, что текст собрала машина и никто не читал."""
    from ire.dashboard.site import plural
    assert plural(1, "widget", "widgets") == "widget"
    assert plural(0, "widget", "widgets") == "widgets"       # ноль — множественное
    assert plural(44, "widget", "widgets") == "widgets"
    assert plural(-1, "tab", "tabs") == "tab"


def test_site_has_no_cyrillic_left():
    """Решение от 17.07.2026: сайт целиком английский, без переключателя.

    Русский текст в вёрстке — не косметика: сайт метит в продажу, а оба
    конкурента англоязычные. Тест ловит новую строку, написанную по привычке.
    """
    import re
    c = TestClient(app)
    for path in ("/about", "/catalog", "/news"):
        found = re.findall(r"[А-Яа-яЁё][А-Яа-яЁё ,.-]{3,}", c.get(path).text)
        assert not found, (path, found[:5])


# ── виджеты оверлея: износ по зонам и пит-лимитер ───────────────────────────

from overlay.widgets import GREEN, PURPLE, RED   # цвета для проверок


def _widget(title):
    import sys
    sys.path.insert(0, ".")
    from overlay.widgets import WIDGETS
    return next(w for w in WIDGETS if getattr(w, "TITLE", "") == title)


class _Store:
    def __init__(self, **d):
        self._d = d

    def get(self, k):
        return self._d.get(k, {})


def test_pit_helper_warns_about_forgotten_limiter():
    """Забытый лимитер стоит дороже превышения: проезд мимо бокса и штраф."""
    W = _widget("Pit helper")
    w = W.__new__(W)
    w.store = _Store(race={"on_pit": True, "warnings": []},
                     live={"speed": 15.0}, strategy={})
    rows = dict((r[0], r[1]) for r in w.rows())
    assert rows["Limiter"] == "OFF"
    assert "limiter" in rows["!"]


def test_pit_helper_quiet_when_limiter_on():
    W = _widget("Pit helper")
    w = W.__new__(W)
    w.store = _Store(race={"on_pit": True, "warnings": [{"key": "pit_limiter"}]},
                     live={"speed": 16.0}, strategy={})
    rows = dict((r[0], r[1]) for r in w.rows())
    assert rows["Limiter"] == "ON"
    assert "!" not in rows                      # не пилим, когда всё правильно


def test_pit_helper_shows_excess_speed():
    W = _widget("Pit helper")
    w = W.__new__(W)
    w.store = _Store(race={"on_pit": True, "warnings": []},
                     live={"speed": 26.4}, strategy={})     # 95 км/ч
    rows = dict((r[0], r[1]) for r in w.rows())
    assert rows["Over limit"].startswith("+35")


# ── доведённые виджеты: проверяем смысл, а не отрисовку ─────────────────────

class _Cfg:
    """Конфиг-заглушка: отдаёт значения по умолчанию либо заданные."""

    def __init__(self, **opts):
        self._o = opts

    def widget_opt(self, key, name, default=None):
        return self._o.get(name, default)


def _mk(title, store, **opts):
    """Виджет без конструктора Qt: нужны только rows() и настройки."""
    W = _widget(title)
    w = W.__new__(W)
    w.store = store
    w.config = _Cfg(**opts)
    return w


def test_laps_shows_delta_to_best_and_marks_personal_best():
    """Разница с лучшим — то, ради чего на виджет смотрят посреди круга."""
    w = _mk("Laps", _Store(race={"last_lap_time": 92.4, "best_lap_time": 91.8}))
    rows = {r[0]: r[1] for r in w.rows()}
    assert rows["Δ to best"] == "+0.600"

    w = _mk("Laps", _Store(race={"last_lap_time": 91.5, "best_lap_time": 91.5}))
    rows = w.rows()
    last = next(r for r in rows if r[0] == "Last")
    assert last[2] == PURPLE                      # личный рекорд виден сразу


def test_shift_offset_moves_the_threshold():
    """Многие переключают раньше SDK — сдвиг обязан менять момент подсказки."""
    store = _Store(race={"rpm": 6600, "shift_rpm": 7000})
    assert {r[0]: r[1] for r in _mk("RPM & shift", store).rows()}["To shift"] == "400"
    # сдвинули точку на 600 ниже — переключаться пора уже сейчас
    early = _mk("RPM & shift", store, shift_offset=-600)
    assert {r[0]: r[1] for r in early.rows()}["To shift"] == "NOW"


def test_session_warns_in_last_five_minutes():
    w = _mk("Session", _Store(session={"time_remain": 240.0}))
    tl = next(r for r in w.rows() if r[0] == "Time left")
    assert tl[2] == RED
    w = _mk("Session", _Store(session={"time_remain": 1800.0}))
    tl = next(r for r in w.rows() if r[0] == "Time left")
    assert tl[2] != RED


def test_weather_shows_temperatures_and_converts_units():
    """Раньше виджет молчал про температуры — два самых нужных числа."""
    store = _Store(race={}, live={"track_temp": 27.0, "air_temp": 21.0})
    rows = {r[0]: r[1] for r in _mk("Weather", store).rows()}
    assert rows["Track"] == "27°C" and rows["Air"] == "21°C"
    rows = {r[0]: r[1] for r in _mk("Weather", store, units="f").rows()}
    assert rows["Track"] == "81°F"


def test_top_speed_resets_max_on_new_lap():
    """Максимум за сессию снимается один раз; полезен максимум ЗА КРУГ."""
    w = _mk("Top speed", _Store(live={"speed": 80.0}, race={"lap": 3}))
    w.rows()
    w.store = _Store(live={"speed": 50.0}, race={"lap": 3})
    assert {r[0]: r[1] for r in w.rows()}["This lap"] == "288 km/h"
    w.store = _Store(live={"speed": 50.0}, race={"lap": 4})     # новый круг
    rows = {r[0]: r[1] for r in w.rows()}
    assert rows["This lap"] == "180 km/h"
    assert rows["Last lap"] == "288 km/h"
    assert rows["Session"] == "288 km/h"                        # за сессию помним


def test_slip_learns_the_car_then_tells_understeer_from_oversteer():
    """Снос и занос лечатся противоположным — одно слово на оба бесполезно.

    Норму связи «руль → рыскание» виджет выучивает сам: она зависит от
    передаточного числа рулевой и базы, а SDK отдаёт угол руля, не колёс.
    """
    w = _mk("Slip", _Store(live={}))

    # спокойные круги: машина держит, копим норму этой машины
    for _ in range(60):
        w.store = _Store(live={"yaw_rate": 0.30, "steer": 0.20, "speed": 50.0})
        w.rows()
    assert {r[0]: r[1] for r in w.rows()}["Balance"] == "balanced"

    # тот же руль и скорость, а рыскания почти нет — не поворачивает
    w.store = _Store(live={"yaw_rate": 0.05, "steer": 0.20, "speed": 50.0})
    assert {r[0]: r[1] for r in w.rows()}["Balance"] == "understeer"

    # рыскание втрое выше нормы при том же руле — поехала задняя ось
    w.store = _Store(live={"yaw_rate": 1.00, "steer": 0.20, "speed": 50.0})
    assert {r[0]: r[1] for r in w.rows()}["Balance"] == "oversteer"


def test_slip_says_it_is_still_learning():
    """Пока нормы нет — честное «учусь», а не выдуманный вердикт."""
    w = _mk("Slip", _Store(live={"yaw_rate": 0.3, "steer": 0.2, "speed": 50.0}))
    assert {r[0]: r[1] for r in w.rows()}["Balance"] == "learning…"


def test_slip_stays_quiet_in_the_pits():
    """На малой скорости руль вывернут, но это не срыв."""
    w = _mk("Slip", _Store(live={"yaw_rate": 0.1, "steer": 0.9, "speed": 3.0}))
    assert {r[0]: r[1] for r in w.rows()}["Balance"] == "—"


# ── вторая половина доведённых виджетов ─────────────────────────────────────

def test_fuel_shows_three_burn_scenarios():
    """Средний расход говорит «хватит ли как ехал». Гонке нужен вопрос
    «а если поеду быстрее» — отсюда три сценария."""
    w = _mk("Fuel & pit", _Store(strategy={
        "fuel": 30.0, "avg_burn": 3.0, "max_burn": 3.5, "min_burn": 2.5,
        "laps_on_fuel": 10.0}))
    rows = {r[0]: r[1] for r in w.rows()}
    assert rows["Average"].startswith("10.0 laps")
    assert rows["Pushing"].startswith("8.6 laps")     # 30/3.5
    assert rows["Saving"].startswith("12.0 laps")     # 30/2.5


def test_fuel_turns_red_on_last_laps():
    w = _mk("Fuel & pit", _Store(strategy={"fuel": 3.0, "laps_on_fuel": 1.0}))
    rng = next(r for r in w.rows() if r[0] == "Range")
    assert rng[2] == RED


def test_wear_trend_says_whether_tyres_last_to_the_end():
    """«Осталось 25 кругов» бесполезно без ответа: хватит ли до финиша."""
    ok = _mk("Wear trend", _Store(strategy={
        "tire_laps_left": 25.0, "laps_to_go": 18, "tire_min": 0.7,
        "tire_wear_per_lap": 0.01}))
    assert {r[0]: r[1] for r in ok.rows()}["Verdict"] == "will last"

    short = _mk("Wear trend", _Store(strategy={
        "tire_laps_left": 8.0, "laps_to_go": 18, "tire_min": 0.3,
        "tire_wear_per_lap": 0.03}))
    assert {r[0]: r[1] for r in short.rows()}["Verdict"] == "short by 10"


def test_team_incidents_counts_room_to_the_limit():
    """В командной гонке лимит общий и штраф прилетает всей машине."""
    w = _mk("Team incidents", _Store(damage={"team_incidents": 14, "incidents": 7}),
            limit=17)
    rows = {r[0]: r[1] for r in w.rows()}
    assert rows["Left"] == "3 to limit"
    assert rows["My share"] == "50%"


def test_balance_translates_temperature_into_handling():
    """Разница температур ничего не подсказывает новичку — нужен перевод."""
    front = _mk("Front/rear balance",
                _Store(result={"symptoms": {"tire": {"front_rear_balance": 6.0}}}))
    rows = {r[0]: r[1] for r in front.rows()}
    assert rows["Feels like"] == "understeer"
    assert "front" in rows["Try"]

    calm = _mk("Front/rear balance",
               _Store(result={"symptoms": {"tire": {"front_rear_balance": 1.0}}}))
    assert {r[0]: r[1] for r in calm.rows()}["Verdict"] == "balanced"


def test_symptoms_separates_global_problem_from_a_local_one():
    """Одна беда во всех фазах лечится иначе, чем беда только на входе."""
    every = _mk("Symptoms", _Store(result={"symptoms": {"balance": {
        "entry": {"tendency": "understeer"},
        "mid": {"tendency": "understeer"},
        "exit": {"tendency": "understeer"}}}}))
    assert {r[0]: r[1] for r in every.rows()}["Verdict"] == "understeer everywhere"

    local = _mk("Symptoms", _Store(result={"symptoms": {"balance": {
        "entry": {"tendency": "neutral"},
        "mid": {"tendency": "neutral"},
        "exit": {"tendency": "oversteer"}}}}))
    rows = {r[0]: r[1] for r in local.rows()}
    assert rows["Worst at"] == "exit"
    assert "Verdict" not in rows


def test_position_gaps_marks_a_closing_gap():
    """Полторы секунды — атака, если было три, и оборона, если была одна."""
    w = _mk("Position & gaps", _Store(race={"gap_ahead": 3.0, "gap_behind": 5.0}))
    for _ in range(120):
        w.rows()
    w.store = _Store(race={"gap_ahead": 1.5, "gap_behind": 5.0})
    ahead = next(r for r in w.rows() if r[0] == "Ahead")
    assert "▲" in ahead[1] and ahead[2] == GREEN


def test_ers_compares_deploy_with_previous_lap():
    w = _mk("ERS / hybrid", _Store(race={"energy_pct": 0.8, "deploy_pct": 0.60, "lap": 4}))
    w.rows()
    w.store = _Store(race={"energy_pct": 0.5, "deploy_pct": 0.75, "lap": 5})
    rows = {r[0]: r[1] for r in w.rows()}
    assert rows["Last lap"] == "60%"
    assert rows["Vs last"] == "+15%"


# ── два виджета, взятых из RaceLab ──────────────────────────────────────────

def test_laptime_log_marks_the_best_lap_and_shows_deltas():
    """График показывает форму, таблица — конкретные цифры.
    Температура рядом со временем объясняет медленный круг."""
    W = _widget("Laptime log")
    w = W.__new__(W)
    w.store = _Store(race={"lap_log": [
        {"lap": 5, "time": 92.5, "track_temp": 33.0},
        {"lap": 6, "time": 91.8, "track_temp": 32.0},
        {"lap": 7, "time": 92.1, "track_temp": 32.0}]})
    w.config = _Cfg()
    rows = [x for x in w.store.get("race")["lap_log"]]
    best = min(x["time"] for x in rows)
    assert best == 91.8                              # именно шестой круг лучший


def test_laptime_log_survives_empty_and_broken_rows():
    """Круг с нулевым временем (обрыв, боксы) не должен ломать таблицу."""
    W = _widget("Laptime log")
    w = W.__new__(W)
    w.config = _Cfg()
    for log in ([], [{"lap": 3}], [{"lap": 3, "time": 0}], [{"lap": 3, "time": None}]):
        w.store = _Store(race={"lap_log": log})
        good = [x for x in log if isinstance(x.get("time"), (int, float)) and x["time"] > 0]
        assert good == []                            # всё отсеивается, рисуем заглушку


def test_blind_spot_reads_the_same_channel_as_spotter():
    """Данные те же, что у Spotter, — разница только в подаче: панель по краю
    экрана видно боковым зрением, а маленький виджет надо найти глазами."""
    W = _widget("Blind spot")
    assert "race" in W.ENDPOINTS
    assert W.DEFAULT[0] > 500                        # широкая по замыслу


def test_download_page_is_served_and_linked():
    """Сайт рассказывал про продукт, но не давал его взять."""
    c = TestClient(app)
    r = c.get("/download")
    assert r.status_code == 200
    assert "Get it running" in r.text
    assert '<a href="/download"' in c.get("/about").text     # есть в навигации


def test_panel_shot_route_serves_png_and_refuses_traversal():
    c = TestClient(app)
    import pathlib
    shots = sorted((pathlib.Path(__file__).resolve().parents[1]
                    / "docs" / "panel").glob("*.png"))
    if shots:
        ok = c.get(f"/panel/{shots[0].name}")
        assert ok.status_code == 200 and ok.headers["content-type"] == "image/png"
    # hero.png лежит на уровень выше каталога снимков — именно то, куда
    # попыталась бы уйти обратная косая. Экранированный вариант доходит
    # до роута (обычный «..» схлопывает ещё сервер), и basename его режет.
    assert c.get("/panel/%2e%2e%2f%2e%2e%2fhero.png").status_code == 404
    assert c.get("/panel/notes.txt").status_code == 404


def test_corner_analysis_endpoint_answers_without_laps():
    """До первых кругов разбор невозможен — но отвечать он обязан внятно,
    а не 500-й ошибкой."""
    r = TestClient(app).get("/api/corners")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    if not body["ok"]:
        assert body["reason"]


def test_corner_endpoint_takes_only_a_file_name():
    """Путь приходит из адреса. basename режет попытку уйти из папки кругов."""
    r = TestClient(app).get("/api/corners", params={"lap": "../../secret.json.gz"})
    assert r.status_code == 200
    assert r.json().get("ok") is False


def test_stint_plan_endpoint_reads_drivers_and_offsets():
    """Пилоты и часовые пояса приходят от человека, темп и расход — из гонки."""
    from ire.dashboard.server import STATE
    STATE["strategy"] = {"avg_lap_time": 100.0, "avg_burn": 3.0, "tank": 60.0}
    STATE["session"] = {"time_remain": 3600.0}
    try:
        r = TestClient(app).get("/api/stintplan", params={
            "drivers": "A, B", "start": "2026-09-05T10:00:00",
            "pit": 55, "offsets": "B:-4"}).json()
        assert r["ok"]
        assert {s["driver"] for s in r["stints"]} == {"A", "B"}
        b = next(s for s in r["stints"] if s["driver"] == "B")
        assert b["local_start"] != b["clock_start"], "смещение часового пояса потеряно"
    finally:
        STATE["strategy"], STATE["session"] = {}, {}


def test_stint_plan_without_drivers_is_a_clean_refusal():
    r = TestClient(app).get("/api/stintplan").json()
    assert r["ok"] is False and r["reason"]


def test_saved_laps_endpoint_hides_absolute_paths():
    """Отдавать наружу полный путь по диску незачем: имени файла хватает,
    а путь — это лишние сведения о чужой машине."""
    for m in TestClient(app).get("/api/laps").json():
        assert "path" not in m
        assert "file" in m and "\\" not in m["file"] and "/" not in m["file"]


def test_corner_endpoint_says_which_laps_it_picked():
    """Без этого выпадашки на странице показывают первый круг списка и
    расходятся с временами в шапке — интерфейс сам себе противоречит."""
    r = TestClient(app).get("/api/corners").json()
    if r.get("ok"):
        assert r["lap_file"] and r["ref_file"]
        assert r["lap_file"] != r["ref_file"], "круг сравнивается сам с собой"


def test_stint_plan_can_be_downloaded_as_text():
    """План уносят в Discord одним сообщением, а не пересказывают по строчкам."""
    from ire.dashboard.server import STATE
    STATE["strategy"] = {"avg_lap_time": 100.0, "avg_burn": 3.0, "tank": 60.0}
    STATE["session"] = {"time_remain": 3600.0}
    try:
        r = TestClient(app).get("/api/stintplan", params={
            "drivers": "A,B", "start": "2026-09-05T10:00:00", "fmt": "text"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "attachment" in r.headers["content-disposition"]
        assert "TEAM STINT PLAN" in r.text and "DRIVER" in r.text
    finally:
        STATE["strategy"], STATE["session"] = {}, {}


def test_availability_reaches_the_planner_through_the_url():
    """Окна доступности вводятся строкой в поле — проверяем, что они
    доезжают до расчёта, а не теряются по дороге."""
    from ire.dashboard.server import STATE
    STATE["strategy"] = {"avg_lap_time": 100.0, "avg_burn": 3.0, "tank": 60.0}
    STATE["session"] = {"time_remain": 7200.0}
    try:
        c = TestClient(app)
        free = c.get("/api/stintplan", params={"drivers": "A,B"}).json()
        limited = c.get("/api/stintplan", params={"drivers": "A,B",
                                                  "free": "B 0-5"}).json()
        assert free["ok"] and limited["ok"]
        b_free = sum(1 for s in free["stints"] if s["driver"] == "B")
        b_limited = sum(1 for s in limited["stints"] if s["driver"] == "B")
        assert b_limited < b_free, "окна доступности не повлияли на план"
    finally:
        STATE["strategy"], STATE["session"] = {}, {}


def test_a_widget_never_starts_reading_the_live_sim_by_itself():
    """Раньше fastval() лениво поднимал фоновый поток к общей памяти iRacing
    при первом же обращении. Из-за этого тесты отвечали по-разному в
    зависимости от того, открыт ли сейчас сим: на машине с запущенной игрой
    набор падал, на пустой проходил. Поймать такое почти невозможно, а
    программа готовится к продаже — у покупателя игра будет открыта.

    Поднимать живую телеметрию должен тот, кому она нужна, — оверлей в
    store.start(). Виджет обязан обойтись тем, что пришло по HTTP.
    """
    from overlay import telemetry, widgets

    before = telemetry._FEED
    telemetry._FEED = None
    try:
        w = _mk("Slip", _Store(live={"yaw_rate": 0.1, "steer": 0.9, "speed": 3.0}))
        assert {r[0]: r[1] for r in w.rows()}["Balance"] == "—"
        assert telemetry._FEED is None, "виджет сам полез в живой сим"
        assert widgets.fastval("speed", 42.0) == 42.0, "взял не то, что дали"
    finally:
        telemetry._FEED = before


def test_every_plain_api_endpoint_answers_without_parameters():
    """Дешёвый пояс на все карточки сразу. Setup Optimiser в первой редакции
    падал с KeyError на двух фазах из трёх и отдавал бы 500 ровно на самых
    частых вопросах — такой тест поймал бы это за секунду."""
    from fastapi.testclient import TestClient

    from ire.dashboard.server import app

    c = TestClient(app)
    bad = []
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/") or "{" in path:
            continue
        try:
            if c.get(path).status_code != 200:
                bad.append(path)
        except Exception as e:                               # noqa: BLE001
            bad.append(f"{path}: {type(e).__name__}")
    assert not bad, bad


def test_the_optimiser_answers_in_every_phase():
    """Именно те три запроса, на которых падала первая редакция."""
    from fastapi.testclient import TestClient

    from ire.dashboard.server import app

    c = TestClient(app)
    for phase in ("entry", "mid", "exit"):
        r = c.get(f"/api/setup/advise?phase={phase}&symptom=understeer")
        assert r.status_code == 200, phase
        assert r.json()["moves"], phase
