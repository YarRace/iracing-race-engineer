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


# ── шины вместе со стинтом ──────────────────────────────────────────────────

def test_a_stint_carries_its_tyre_pressures_and_temperatures():
    """Без этого Tyre Tool не может сказать «целься как в своём лучшем
    стинте»: сравнивать не с чем, а подставить число неизвестного
    происхождения хуже, чем не ответить."""
    conn = history.connect(":memory:")
    history.save_stint(conn, {"track": "roadatlanta", "car": "ferrari499p"},
                       {"laps": 12, "best_lap": 91.2, "mean_lap": 91.9,
                        "pressures": {"LF": "152 kPa"},
                        "tyre_temps": {"LF": {"inner": 63.3, "outer": 61.2}}})
    s = history.recent_stints(conn, 1)[0]
    # Наружу — словари, а не строки JSON: иначе каждый читатель разбирал бы
    # их сам, и рано или поздно кто-нибудь забыл бы.
    assert s["pressures"] == {"LF": "152 kPa"}
    assert s["tyre_temps"]["LF"]["inner"] == 63.3
    conn.close()


def test_a_stint_without_tyre_data_stores_nothing_rather_than_empty_strings():
    """None и «записано пусто» — разные вещи. Пустая строка потом читалась бы
    как «давления были и они пустые»."""
    conn = history.connect(":memory:")
    history.save_stint(conn, {"track": "spa", "car": "ferrari499p"},
                       {"laps": 3, "mean_lap": 130.0})
    s = history.recent_stints(conn, 1)[0]
    assert s["pressures"] is None and s["tyre_temps"] is None
    conn.close()


def test_an_old_database_gets_the_new_columns_without_losing_its_rows():
    """Проверено на копии его настоящей базы: 637 кругов и 219 стинтов на
    месте. Здесь то же самое, но воспроизводимо."""
    import sqlite3
    import tempfile
    import os
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE stints (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, "
                "track TEXT, track_display TEXT, config TEXT, car TEXT, car_path TEXT, "
                "session_type TEXT, laps INTEGER, best_lap REAL, mean_lap REAL, "
                "spread REAL, incidents INTEGER)")
    old.execute("INSERT INTO stints (ts, track, car, laps, mean_lap) "
                "VALUES ('2026-01-01', 'spa', 'ferrari499p', 7, 130.0)")
    old.commit()
    old.close()

    conn = history.connect(path)
    rows = history.recent_stints(conn, 10)
    assert len(rows) == 1 and rows[0]["laps"] == 7, "старый стинт пропал"
    assert rows[0]["pressures"] is None
    history.save_stint(conn, {"track": "spa", "car": "ferrari499p"},
                       {"laps": 5, "mean_lap": 129.0, "pressures": {"LF": "150 kPa"}})
    assert history.recent_stints(conn, 1)[0]["pressures"] == {"LF": "150 kPa"}
    conn.close()
