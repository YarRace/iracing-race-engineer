import os
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
