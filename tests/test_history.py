from ire.storage import history

IDENT = {
    "track": "watkinsglen 2021 fullcourse", "track_display": "Watkins Glen",
    "config": "Boot", "car": "Cadillac V-Series.R", "car_path": "cadillacvseriesrgtp",
    "car_class": "GTP", "session_type": "Race",
}


def _conn():
    return history.connect(":memory:")


def test_save_and_best_lap():
    c = _conn()
    history.save_lap(c, IDENT, 1, 92.5, sectors=[30.0, 31.0, 31.5])
    history.save_lap(c, IDENT, 2, 91.0, sectors=[29.8, 30.8, 30.4])
    assert history.best_lap(c, IDENT["track"], IDENT["car"]) == 91.0


def test_invalid_lap_excluded_from_best():
    c = _conn()
    history.save_lap(c, IDENT, 1, 91.0)              # валидный
    history.save_lap(c, IDENT, 2, 3.0)               # мусор (заезд в пит) — valid=0
    assert not history.is_valid_lap(3.0)
    assert history.best_lap(c, IDENT["track"], IDENT["car"]) == 91.0


def test_records_grouped_best_per_track_car():
    c = _conn()
    history.save_lap(c, IDENT, 1, 92.0)
    history.save_lap(c, IDENT, 2, 90.5)
    recs = history.records(c)
    assert len(recs) == 1
    r = recs[0]
    assert r["track_display"] == "Watkins Glen"
    assert r["car"] == "Cadillac V-Series.R"
    assert r["car_class"] == "GTP"
    assert r["best_lap"] == 90.5
    assert r["laps"] == 2


def test_records_split_by_session_type():
    # как «Personal Bests»: практика и гонка на одной трассе — отдельные строки
    c = _conn()
    prac = dict(IDENT, session_type="Practice")
    race = dict(IDENT, session_type="Race")
    history.save_lap(c, prac, 1, 91.2)
    history.save_lap(c, race, 1, 90.4)
    recs = history.records(c)
    assert len(recs) == 2
    by_ev = {r["session_type"]: r["best_lap"] for r in recs}
    assert by_ev == {"Practice": 91.2, "Race": 90.4}


def test_track_history_only_valid_ordered():
    c = _conn()
    history.save_lap(c, IDENT, 1, 92.0)
    history.save_lap(c, IDENT, 2, 2.0)               # мусор — не попадёт
    history.save_lap(c, IDENT, 3, 91.0)
    h = history.track_history(c, IDENT["track"], IDENT["car"])
    assert [row["lap_time"] for row in h] == [92.0, 91.0]


def test_migration_adds_car_class_to_old_db(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    old = sqlite3.connect(p)
    old.executescript(
        "CREATE TABLE laps (id INTEGER PRIMARY KEY, ts TEXT, track TEXT, car TEXT, "
        "lap_time REAL, valid INTEGER);"
        "CREATE TABLE stints (id INTEGER PRIMARY KEY, ts TEXT);")
    old.execute("INSERT INTO laps (ts,track,car,lap_time,valid) VALUES ('t','wg','Cad',90.0,1)")
    old.commit()
    old.close()
    c = history.connect(str(p))               # должна досоздать car_class, не теряя данные
    cols = {r[1] for r in c.execute("PRAGMA table_info(laps)")}
    assert "car_class" in cols
    assert c.execute("SELECT COUNT(*) FROM laps").fetchone()[0] == 1


def test_save_stint_and_recent():
    c = _conn()
    history.save_stint(c, IDENT, {"laps": 10, "best_lap": 90.5, "mean_lap": 91.2,
                                  "spread": 1.4, "incidents": 2})
    st = history.recent_stints(c)
    assert len(st) == 1
    assert st[0]["laps"] == 10
    assert st[0]["best_lap"] == 90.5
    assert st[0]["spread"] == 1.4
