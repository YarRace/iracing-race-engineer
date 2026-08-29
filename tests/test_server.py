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
    for path, must in (("/about", "Гоночный инженер"),
                       ("/catalog", "Виджеты и карточки"),
                       ("/news", "Что изменилось")):
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


def test_russian_plurals_on_site():
    """«42 виджетов» и «6 вкладки» сразу выдают, что текст собрала машина."""
    from ire.dashboard.site import plural
    assert plural(1, "виджет", "виджета", "виджетов") == "виджет"
    assert plural(42, "виджет", "виджета", "виджетов") == "виджета"
    assert plural(6, "вкладка", "вкладки", "вкладок") == "вкладок"
    assert plural(11, "круг", "круга", "кругов") == "кругов"     # 11, а не 1
    assert plural(61, "карточка", "карточки", "карточек") == "карточка"
    assert plural(13, "эндпоинт", "эндпоинта", "эндпоинтов") == "эндпоинтов"


# ── виджеты оверлея: износ по зонам и пит-лимитер ───────────────────────────

from overlay.widgets import PURPLE, RED          # цвета для проверок


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
