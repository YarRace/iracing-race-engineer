"""Фаза 1: локальное хранилище истории (SQLite) — фундамент для рекордов,
истории и прогресса.

Каждый завершённый круг пишется в таблицу `laps`, каждый закрытый стинт — в
`stints`. На этих данных потом строятся рекорды по трассам, графики прогресса и
сравнение (замена Garage61 в личной части).

Чистые функции, тестируются без сима на in-memory базе (`connect(":memory:")`).
Читатели (API дашборда) открывают свой коннект на запрос — SQLite сам разводит
одновременные чтение/запись (включён WAL). Путь к базе можно задать переменной
окружения IRE_DB_PATH; по умолчанию — <корень проекта>/data/history.db.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3

# min/max «настоящего» круга — как в consistency: отсекаем рестарты, заезд в пит.
MIN_LAP = 15.0
MAX_LAP = 1200.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS laps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    track         TEXT,
    track_display TEXT,
    config        TEXT,
    car           TEXT,
    car_path      TEXT,
    car_class     TEXT,
    session_type  TEXT,
    lap_num       INTEGER,
    lap_time      REAL,
    s1            REAL,
    s2            REAL,
    s3            REAL,
    sectors       TEXT,
    valid         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_laps_track_car ON laps (track, car);

CREATE TABLE IF NOT EXISTS stints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    track         TEXT,
    track_display TEXT,
    config        TEXT,
    car           TEXT,
    car_path      TEXT,
    car_class     TEXT,
    session_type  TEXT,
    laps          INTEGER,
    best_lap      REAL,
    mean_lap      REAL,
    spread        REAL,
    incidents     INTEGER,
    pressures     TEXT,
    tyre_temps    TEXT
);
"""

# Колонки, добавленные после первого релиза — досоздаём в старых базах (миграция).
_MIGRATIONS = {"laps": [("car_class", "TEXT"),
                        # ПОЛНЫЙ список секторов. Трёх колонок не хватало, и
                        # это была настоящая потеря: на Спа секторов четыре
                        # (32 секунды из 123 не попадали в базу — 26% круга),
                        # на Монце 33%, на Road America 52%. Всё, что дальше
                        # третьего, пропадало молча, и разбирать было нечего.
                        ("sectors", "TEXT")],
               "stints": [("car_class", "TEXT"),
                          # Давления и температуры шин со стинта. Без них
                          # Tyre Tool не может сказать «целься как в свой
                          # лучший стинт» — сравнивать не с чем.
                          ("pressures", "TEXT"), ("tyre_temps", "TEXT")]}


def default_path():
    """Путь к базе: IRE_DB_PATH или <данные пользователя>/data/history.db.

    Именно ПОЛЬЗОВАТЕЛЬСКИЕ данные, а не корень исходников: в собранном
    .exe это разные каталоги, и положить базу внутрь сборки значило бы
    стирать всю историю при каждом обновлении программы (см. ire.paths).
    """
    env = os.environ.get("IRE_DB_PATH")
    if env:
        return env
    from ire import paths
    return str(paths.data_dir() / "history.db")


def connect(path=None):
    """Открывает (создаёт при отсутствии) базу и гарантирует схему.
    path=":memory:" — для тестов. check_same_thread=False: писатель и читатели
    живут в разных потоках (live-цикл и API-сервер)."""
    path = path or default_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")   # читатели не блокируют писателя
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn):
    """Досоздаёт недостающие колонки в уже существующих базах (без потери данных)."""
    for table, cols in _MIGRATIONS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, coltype in cols:
            if name not in have:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")
                except sqlite3.OperationalError:
                    # База занята живым циклом — колонку добавит он сам при
                    # своём connect(). Уронить из-за этого запрос дашборда
                    # нельзя: человек увидит белый экран посреди гонки.
                    pass


def is_valid_lap(lap_time):
    return lap_time is not None and MIN_LAP <= lap_time <= MAX_LAP


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def save_lap(conn, identity, lap_num, lap_time, sectors=None, valid=None):
    """Пишет один завершённый круг. identity — dict из session_identity()."""
    if valid is None:
        valid = is_valid_lap(lap_time)
    s = list(sectors or [])
    s1, s2, s3 = (s + [None, None, None])[:3]
    # s1..s3 остаются ради прежних читателей (рекорды, график прогресса), но
    # правда о круге теперь в sectors. Список пишем, только если в нём есть
    # хоть одно число: [None, None, None] в JSON читался бы как «записано
    # пусто», а это другое утверждение, чем «не записано».
    full = _json(s) if any(isinstance(x, (int, float)) for x in s) else None
    conn.execute(
        "INSERT INTO laps (ts, track, track_display, config, car, car_path, car_class, "
        "session_type, lap_num, lap_time, s1, s2, s3, sectors, valid) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (_now(), identity.get("track"), identity.get("track_display"),
         identity.get("config"), identity.get("car"), identity.get("car_path"),
         identity.get("car_class"), identity.get("session_type"), lap_num, lap_time,
         s1, s2, s3, full, int(bool(valid))),
    )
    conn.commit()


def _json(v):
    """Словарь → строка для SQLite. None остаётся None: пустая строка потом
    читалась бы как «записано пусто», а это разные вещи."""
    return json.dumps(v, ensure_ascii=False) if v else None


def _unjson(v):
    try:
        return json.loads(v) if v else None
    except (TypeError, ValueError):
        return None


def save_stint(conn, identity, summary):
    """Пишет сводку стинта. summary — dict с laps/best_lap/mean_lap/spread/incidents."""
    conn.execute(
        "INSERT INTO stints (ts, track, track_display, config, car, car_path, car_class, "
        "session_type, laps, best_lap, mean_lap, spread, incidents, "
        "pressures, tyre_temps) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (_now(), identity.get("track"), identity.get("track_display"),
         identity.get("config"), identity.get("car"), identity.get("car_path"),
         identity.get("car_class"), identity.get("session_type"), summary.get("laps"),
         summary.get("best_lap"), summary.get("mean_lap"), summary.get("spread"),
         summary.get("incidents"), _json(summary.get("pressures")),
         _json(summary.get("tyre_temps"))),
    )
    conn.commit()


def best_lap(conn, track, car):
    """Личный рекорд (мин. валидный круг) на трассе+машине, или None."""
    row = conn.execute(
        "SELECT MIN(lap_time) AS best FROM laps WHERE valid=1 AND track=? AND car=?",
        (track, car),
    ).fetchone()
    return row["best"] if row else None


def records(conn):
    """Список рекордов: лучший валидный круг по каждой связке трасса+конфиг+машина."""
    # как «Personal Bests» в iRacing: лучший круг по каждой связке
    # машина + трасса(+конфиг) + тип сессии (Практика/Гонка — отдельными строками).
    rows = conn.execute(
        "SELECT track, track_display, config, car, car_path, MAX(car_class) AS car_class, "
        "session_type, MIN(lap_time) AS best_lap, COUNT(*) AS laps, MAX(ts) AS last_seen "
        "FROM laps WHERE valid=1 GROUP BY car, track, config, session_type "
        "ORDER BY car, track_display, session_type"
    ).fetchall()
    return [dict(r) for r in rows]


def track_history(conn, track, car, limit=100):
    """Валидные круги на трассе+машине по времени (для графика прогресса)."""
    rows = conn.execute(
        "SELECT ts, lap_num, lap_time, s1, s2, s3 FROM laps "
        "WHERE valid=1 AND track=? AND car=? ORDER BY ts, id LIMIT ?",
        (track, car, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_stints(conn, limit=20):
    rows = conn.execute(
        "SELECT * FROM stints ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # Наружу отдаём словари, а не строки JSON: иначе каждый читатель
        # разбирал бы их сам, и рано или поздно кто-нибудь забыл бы.
        d["pressures"] = _unjson(d.get("pressures"))
        d["tyre_temps"] = _unjson(d.get("tyre_temps"))
        out.append(d)
    return out


def lap_sectors(conn, track=None, car=None, session_type=None, limit=2000):
    """Завершённые круги с посекторными временами — сырьё для разбора заезда.

    Отдаётся ПОЛНЫЙ список секторов и признак `recorded_all`. У кругов,
    записанных до 31.08.2026, списка нет, и он собирается из s1..s3 — но это
    не весь круг: на Спа четвёртый сектор длиной 32 секунды в базу не попал.
    Врать здесь нельзя, тот кто читает обязан знать, что смотрит на кусок.

    Порядок берём по id, а не по ts: два круга подряд ложатся в одну секунду,
    и сортировка по времени переставляла бы их местами — «разовая потеря»
    привязалась бы к чужому номеру круга.

    Отбор — по id DESC, то есть СВЕЖИЕ круги. Сортировка по трассе с обрезкой
    отрезала бы алфавитно последние трассы вместо старых кругов, и свежий
    заезд на Спа однажды молча не попал бы в выборку.
    """
    q = ("SELECT id, ts, track, track_display, config, car, car_class, session_type, "
         "lap_num, lap_time, s1, s2, s3, sectors FROM laps "
         "WHERE valid=1 AND s1 IS NOT NULL")
    args = []
    for col, val in (("track", track), ("car", car), ("session_type", session_type)):
        if val:
            q += f" AND {col}=?"
            args.append(val)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)

    out = []
    for r in conn.execute(q, args):
        d = dict(r)
        full = _unjson(d.pop("sectors"))
        d["recorded_all"] = bool(full)
        d["sectors"] = full if full else [d["s1"], d["s2"], d["s3"]]
        out.append(d)
    out.reverse()                       # обратно в порядок заездов: старые первыми
    return out
