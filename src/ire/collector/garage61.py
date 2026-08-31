"""Garage 61: круги других пилотов как эталон для разбора.

Свой лучший круг — плохой эталон для того, кто хочет ехать быстрее: он
показывает, где ты хуже СЕБЯ, а не где вообще можно быстрее. Garage 61
отдаёт круги других пилотов на той же трассе и машине вместе с телеметрией,
и вот против них разбор уже отвечает на нужный вопрос.

Что проверено на живом API (31.08.2026):

  • токен даёт driving_data, и чужие круги отдаются: Road Atlanta Full —
    20 кругов, среди них GTP на 1:07.6;
  • телеметрия приходит CSV по /laps/{id}/csv: 4083 строки на круг, все
    восемь наших каналов ПЛЮС Lat/Lon — настоящие координаты трассы;
  • `canViewTelemetry: true` НЕ гарантирует доступ: часть кругов отвечает
    403 forbidden_lap. Значит по списку идём вниз, а не упираемся в первый;
  • сервер собирает CSV на лету и иногда не успевает — отдаёт 504.

Отсюда две вещи в устройстве модуля. Первая: скачанный круг кладётся на
диск и больше не качается — на трассу их нужно один-два, а качается круг
десятками секунд. Вторая: любая ошибка сети возвращается значением, а не
исключением, — инженер крутится в живом цикле рядом с гонкой, и падать
из-за чужого сервера он не имеет права.

Токен НИКОГДА не печатается и не уезжает в логи.
"""
from __future__ import annotations

import gzip
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from ire import paths
from ire.storage import laps as lap_store

BASE = "https://garage61.net/api/v1"
CATALOG_TTL = 7 * 24 * 3600        # справочник трасс и машин меняется раз в сезон
LAP_TIMEOUT = 200                  # с: CSV сервер собирает на лету
LIST_TIMEOUT = 40
RATING_TTL = 24 * 3600            # рейтинг меняется после гонки, не при каждом открытии окна

# Колонка CSV → наш канал. Совпадает с laps.CHANNELS, чтобы разбор по
# поворотам работал с чужим кругом ровно так же, как со своим.
COLUMNS = {
    "Speed": "speed", "Throttle": "throttle", "Brake": "brake",
    "SteeringWheelAngle": "steer", "Gear": "gear",
    "LatAccel": "lat_accel", "LongAccel": "long_accel", "YawRate": "yaw_rate",
    # Координаты — тем же именем, что и у своих кругов, чтобы разбор
    # траектории не разбирал, откуда круг приехал.
    "Lat": "lat", "Lon": "lon",
}


def _dir():
    d = paths.data_dir() / "garage61"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def token():
    """Токен из окружения или из data/garage61_token.txt. Пустой — если нет."""
    t = os.environ.get("GARAGE61_TOKEN", "").strip()
    if t:
        return t
    f = paths.data_dir() / "garage61_token.txt"
    try:
        # utf-8-sig: Блокнот дописывает BOM, а он ломает заголовок Authorization
        return f.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def available():
    return bool(token())


def get(path, timeout=LIST_TIMEOUT, **params):
    """(код, данные). Ошибки возвращаются, а не бросаются.

    Живой цикл инженера крутится рядом с гонкой: упасть из-за того, что
    у чужого сервера плохой день, он не имеет права.
    """
    tok = token()
    if not tok:
        return 0, "no token"
    url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tok,
        "Accept": "application/json",
        "User-Agent": "iracing-race-engineer/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            ct = r.headers.get("Content-Type", "")
            if "json" in ct:
                return r.status, json.loads(body)
            return r.status, body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:                                   # сеть, таймаут, VPN
        return 0, str(e)


def _items(data):
    """Списки приходят конвертом {"items": [...], "total": N}, а не голыми."""
    if isinstance(data, dict):
        return data.get("items", [])
    return data if isinstance(data, list) else []


def catalog(kind, force=False):
    """Справочник трасс или машин, с кэшем на диске.

    468 трасс приходят за секунду, но дёргать их на каждый вопрос «а какой
    id у Road Atlanta» незачем: список меняется раз в сезон.
    """
    f = _dir() / f"{kind}.json"
    if not force:
        try:
            if time.time() - f.stat().st_mtime < CATALOG_TTL:
                return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    code, data = get("/" + kind)
    if code != 200:
        try:                                    # сеть отвалилась — берём старый
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    rows = _items(data)
    try:
        f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return rows


def _norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def find_track(name, config=None):
    """Наш идентификатор трассы → запись Garage 61.

    Мы храним «roadatlanta full» и config «Full Course», у них — name
    «Road Atlanta» и variant «Full Course». Сопоставляем по склеенным
    буквам: пробелы и дефисы у всех расставлены по-разному.
    """
    want, cfg = _norm(name), _norm(config)
    rows = catalog("tracks")
    hits = [t for t in rows if _norm(t.get("name")) and _norm(t.get("name")) in want]
    if not hits:
        hits = [t for t in rows if want and want.startswith(_norm(t.get("name")))]
    if not hits:
        return None
    if cfg:
        exact = [t for t in hits if _norm(t.get("variant")) == cfg]
        if exact:
            return exact[0]
    # Без конфигурации берём вариант, чьё имя встречается в нашем: «roadatlanta
    # full» → «Full Course». Иначе — самый первый, но это уже гадание.
    named = [t for t in hits if _norm(t.get("variant")) and _norm(t.get("variant"))[:4] in want]
    return (named or hits)[0]


def find_car(name):
    want = _norm(name)
    if not want:
        return None
    rows = catalog("cars")
    for c in rows:
        if _norm(c.get("name")) == want:
            return c
    for c in rows:
        n = _norm(c.get("name"))
        if n and (n in want or want in n):
            return c
    return None


def list_laps(track, car=None, limit=20):
    """Круги с Garage 61. track/car — НАШИ названия, не их id."""
    ours = track if isinstance(track, str) else ""
    t = find_track(track) if isinstance(track, str) else track
    if not t:
        return {"ok": False, "reason": "track not found in Garage 61", "laps": []}
    q = {"tracks": t["id"], "limit": max(1, min(int(limit), 100))}
    c = find_car(car) if isinstance(car, str) else car
    if c:
        q["cars"] = c["id"]
    code, data = get("/laps", **q)
    if code != 200:
        return {"ok": False, "reason": f"Garage 61 answered {code}", "laps": []}

    out = []
    for x in _items(data):
        d = x.get("driver") or {}
        out.append({
            "id": x.get("id"),
            "lap_time": x.get("lapTime"),
            "driver": (f"{d.get('firstName', '')} {d.get('lastName', '')}".strip()
                       or d.get("slug") or "?"),
            "car": (x.get("car") or {}).get("name"),
            # НАШ идентификатор трассы, а не их название. Разбор сверяет
            # трассы строкой, и «Road Atlanta» против «roadatlanta full»
            # он честно считает разными — сравнение просто не состоится.
            "track": ours or t.get("name"),
            "track_display": t.get("name"),
            "config": t.get("variant"),
            "telemetry": bool(x.get("canViewTelemetry")),
        })
    out.sort(key=lambda x: x["lap_time"] if isinstance(x["lap_time"], (int, float)) else 9e9)
    return {"ok": True, "track": t.get("name"), "config": t.get("variant"), "laps": out}


def parse_csv(text):
    """CSV Garage 61 → кадры в нашем виде, с долей дистанции.

    Заодно вытаскиваем Lat/Lon: iRacing SDK координат не даёт вовсе, и это
    единственный источник настоящей геометрии трассы, который у нас есть.
    """
    lines = (text or "").splitlines()
    if len(lines) < 3:
        return [], []
    head = [h.strip() for h in lines[0].split(",")]
    idx = {h: i for i, h in enumerate(head)}
    if "LapDistPct" not in idx:
        return [], []

    frames, shape = [], []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(head):
            continue

        def num(col):
            i = idx.get(col)
            if i is None:
                return 0.0
            try:
                return float(parts[i])
            except (TypeError, ValueError):
                return 0.0

        f = {"lap_dist_pct": num("LapDistPct")}
        for col, ch in COLUMNS.items():
            f[ch] = num(col)
        frames.append(f)
        if "Lat" in idx and "Lon" in idx:
            # Вместе с ДОЛЕЙ ДИСТАНЦИИ: без неё по контуру нельзя поставить
            # машинку — точка есть, а куда её класть на круге, неизвестно.
            shape.append((f["lap_dist_pct"], num("Lat"), num("Lon")))
    return frames, shape


def _cache_path(lap_id):
    return _dir() / "laps" / f"{lap_id}.json.gz"


def load_cached(lap_id):
    p = _cache_path(lap_id)
    try:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def download_lap(meta, force=False):
    """Круг целиком в НАШЕМ формате: 1000 точек по дистанции.

    Ровно тот же формат, что у своих кругов, поэтому `metrics/corners`
    разбирает чужой круг без единой правки — и это главное: одна логика
    сравнения, а не две почти одинаковые.

    Скачанное кладётся на диск навсегда. Круг качается десятками секунд,
    а нужен он на трассу один-два: перекачивать его при каждом открытии
    вкладки — впустую жечь и время, и чужой сервер.
    """
    lap_id = meta.get("id") if isinstance(meta, dict) else meta
    if not lap_id:
        return None
    if not force:
        hit = load_cached(lap_id)
        if hit:
            return hit

    code, csv = get(f"/laps/{lap_id}/csv", timeout=LAP_TIMEOUT)
    if code != 200 or not isinstance(csv, str):
        return None
    frames, shape = parse_csv(csv)
    if len(frames) < 50:
        return None

    channels = lap_store.resample(frames)
    if not channels:
        return None
    m = meta if isinstance(meta, dict) else {}
    out = {
        "source": "garage61",
        "g61_id": lap_id,
        "track": m.get("track"),
        "track_display": m.get("track_display") or m.get("track"),
        "config": m.get("config"), "car": m.get("car"),
        "driver": m.get("driver"),
        "lap_time": m.get("lap_time"),
        "points": lap_store.POINTS,
        "channels": channels,
        # Контур трассы по координатам. Прореживаем: 4000 точек рисовать
        # незачем, форма от 600 не меняется, а вес карты падает всемеро.
        "shape": shape[::max(1, len(shape) // 600)] if shape else [],
    }
    try:
        _cache_path(lap_id).parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(_cache_path(lap_id), "wt", encoding="utf-8") as fh:
            json.dump(out, fh, separators=(",", ":"))
    except OSError:
        pass                                   # не записалось — не беда, круг уже в руках
    return out


def best_reference(track, car=None, tries=4, slower_than=None):
    """Самый быстрый круг, который реально отдаётся.

    Идём по списку вниз: `canViewTelemetry: true` не гарантирует доступ —
    часть кругов отвечает 403, а часть 504, когда сервер не успел собрать
    CSV. Упереться в самый быстрый значит не получить ничего.

    Свои круги из выдачи НЕ выбрасываем: Garage 61 хранит и их, и там
    вполне может лежать твой же круг быстрее сохранённого локально.
    Кто это был, видно по полю driver — пусть решает человек.

    slower_than отсекает круги медленнее твоего: эталон, который хуже
    разбираемого круга, показал бы, где ты ЛУЧШЕ, — это не разбор.
    """
    listing = list_laps(track, car, limit=25)
    if not listing["ok"]:
        return None, listing["reason"]
    cand = [x for x in listing["laps"]
            if x["telemetry"] and isinstance(x["lap_time"], (int, float))]
    if slower_than:
        # Быстрее твоего — предпочтительно. Но если быстрее нет (ты первый
        # в таблице), сравнение всё равно полезно: в ОТДЕЛЬНЫХ поворотах
        # человек медленнее тебя кругом вполне мог проехать лучше. Пустой
        # ответ «эталона нет» здесь был бы отказом там, где есть что сказать.
        faster = [x for x in cand if x["lap_time"] < slower_than]
        cand = faster or [x for x in cand if abs(x["lap_time"] - slower_than) > 1e-6]
    if not cand:
        return None, "no laps with telemetry on this track and car"
    for meta in cand[:tries]:
        lap = download_lap(meta)
        if lap:
            return lap, ""
    return None, "Garage 61 did not hand over any lap (403 or 504)"


def me():
    """Кто мы для Garage 61 — чтобы отметить свои круги в таблице.

    Ответ кэшируется на диск: он не меняется вовсе, а без сети таблица
    всё равно должна показать, где ты.
    """
    f = _dir() / "me.json"
    code, data = get("/me")
    if code == 200 and isinstance(data, dict):
        try:
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return data
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def leaderboard(track, car=None, season=None, limit=100, clean_only=True):
    """Таблица времён: кто, за сколько, отставание от лидера.

    Ровно тот вопрос, ради которого Garage 61 и нужен: не «где я хуже себя»,
    а «на каком я месте и сколько до первого». Свой круг помечается — без
    этого таблицу приходится глазами обыскивать на свою фамилию.

    Сезон фильтруется НА НАШЕЙ стороне: параметр `seasons` сервер принимает,
    но выдачу по нему не сужает — проверено 31.08.2026. Молча положиться
    на него значило бы показывать прошлогодние времена как сегодняшние.

    clean_only отбрасывает круги с вылетами и обрезанные: сравнивать свой
    чистый круг с чужим, срезанным по траве, бессмысленно.
    """
    t = find_track(track) if isinstance(track, str) else track
    if not t:
        return {"ok": False, "reason": "track not found in Garage 61", "rows": []}
    q = {"tracks": t["id"], "limit": max(1, min(int(limit), 200))}
    c = find_car(car) if isinstance(car, str) else car
    if c:
        q["cars"] = c["id"]
    code, data = get("/laps", **q)
    if code != 200:
        return {"ok": False, "reason": f"Garage 61 answered {code}", "rows": []}

    mine = (me() or {}).get("id")
    seasons, rows = {}, []
    for x in _items(data):
        lt = x.get("lapTime")
        if not isinstance(lt, (int, float)) or lt <= 0:
            continue
        if x.get("incomplete") or x.get("missing"):
            continue
        if clean_only and (x.get("offtrack") or x.get("clean") is False):
            continue
        se = x.get("season") or {}
        if se.get("id"):
            seasons[se["id"]] = se.get("shortName") or se.get("name") or ""
        if season and se.get("id") != season:
            continue
        d = x.get("driver") or {}
        rows.append({
            "lap_id": x.get("id"),
            "driver": (f"{d.get('firstName', '')} {d.get('lastName', '')}".strip()
                       or d.get("slug") or "?"),
            "is_me": bool(mine) and d.get("id") == mine,
            "lap_time": lt,
            "car": (x.get("car") or {}).get("name"),
            # driverRating — рейтинг пилота на момент круга. Не iRating
            # (тот только у самого iRacing), но того же порядка и той же
            # природы: пока официальный вход у них закрыт, это единственное
            # число, которым можно подписать человека в таблице.
            "rating": x.get("driverRating"),
            "season": se.get("shortName") or se.get("name") or "",
            "season_id": se.get("id"),
            "when": (x.get("startTime") or "")[:10],
            "sectors": [s.get("sectorTime") for s in (x.get("sectors") or [])],
            "telemetry": bool(x.get("canViewTelemetry")),
        })

    # Один пилот — один круг, лучший. Иначе таблица превращается в список
    # заездов одного быстрого человека, и мест в ней не разглядеть.
    best = {}
    for r in rows:
        cur = best.get(r["driver"])
        if cur is None or r["lap_time"] < cur["lap_time"]:
            best[r["driver"]] = r
    rows = sorted(best.values(), key=lambda r: r["lap_time"])

    leader = rows[0]["lap_time"] if rows else 0.0
    for i, r in enumerate(rows, 1):
        r["pos"] = i
        r["gap"] = round(r["lap_time"] - leader, 3)

    my_row = next((r for r in rows if r["is_me"]), None)
    return {
        "ok": True,
        "track": t.get("name"), "config": t.get("variant"),
        "car": (c or {}).get("name") if c else None,
        "seasons": [{"id": k, "name": v} for k, v in sorted(seasons.items(), reverse=True)],
        "season": season,
        "rows": rows,
        "my_pos": my_row["pos"] if my_row else None,
        "my_gap": my_row["gap"] if my_row else None,
    }


def sector_table(track, car=None, season=None, limit=60):
    """Сектора всех пилотов и «идеальный круг» из лучших секторов.

    Garage 61 отдаёт сектора вместе с кругом, а мы их выбрасывали. Между
    тем это отдельный и очень прямой ответ: «первый сектор у тебя лучший
    в таблице, второй — восьмой». По одному времени круга такого не видно,
    а работать надо именно над вторым.

    «Идеальный круг» здесь — сумма ЛУЧШИХ секторов разных людей. Никто его
    не проезжал, и это честно написано: он показывает, сколько лежит на
    столе, а не чей-то результат.
    """
    board = leaderboard(track, car, season, limit=limit)
    if not board["ok"]:
        return board

    rows = []
    for r in board["rows"]:
        sec = [x for x in (r.get("sectors") or []) if isinstance(x, (int, float))]
        if sec:
            rows.append({**r, "sectors": sec})
    if not rows:
        return {**board, "rows": [], "reason": "no sector times on this track"}

    n = min(len(r["sectors"]) for r in rows)
    best = []
    for i in range(n):
        cand = min(rows, key=lambda r: r["sectors"][i])
        best.append({"sector": i + 1, "time": cand["sectors"][i],
                     "driver": cand["driver"], "is_me": cand["is_me"]})

    me = next((r for r in rows if r["is_me"]), None)
    my_ranks = []
    if me:
        for i in range(n):
            faster = sum(1 for r in rows if r["sectors"][i] < me["sectors"][i])
            my_ranks.append({"sector": i + 1, "time": me["sectors"][i],
                             "pos": faster + 1,
                             "gap": round(me["sectors"][i] - best[i]["time"], 3)})

    return {**board, "rows": rows, "sectors": n, "best": best,
            "ideal": round(sum(b["time"] for b in best), 3),
            "mine": my_ranks,
            "my_lap": me["lap_time"] if me else None}


def my_rating(track=None, car=None, force=False):
    """Мой рейтинг по последним кругам в Garage 61.

    Официальный iRating закрыт: iRacing перевёл вход на форму в браузере
    (см. `collector/iracing_api.py`). Здесь берётся `driverRating` из
    моих же кругов — число другой природы, и подписывать его словом
    «iRating» было бы враньём.

    Берём САМЫЙ СВЕЖИЙ круг, а не лучший: рейтинг меняется со временем,
    и «мой рейтинг» — это последний известный, а не рекордный.

    Ответ кладётся на диск на сутки. Живьём это два запроса и пять секунд,
    а строка рисуется при каждом открытии главной — без кэша окно каждый
    раз пять секунд стоит с пустой строкой вместо имени.
    """
    cache = _dir() / "garage61_rating.json"
    if not force:
        try:
            if time.time() - cache.stat().st_mtime < RATING_TTL:
                return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    who = (me() or {}).get("id")
    if not who:
        return None
    # /laps ТРЕБУЕТ трассу: без неё сервер отвечает 400, а не пустым списком.
    # Это записано в шапке модуля, и я же на этом споткнулся — поэтому
    # трасса берётся из последнего своего круга, когда её не передали.
    if not track:
        try:
            from ire.storage import laps as L
            saved = L.list_laps(L.default_root())
            if saved:
                latest = max(saved, key=lambda m: m.get("ts") or "")
                track, car = latest.get("track"), car or latest.get("car")
        except Exception:                                    # noqa: BLE001
            pass
    t = find_track(track) if track else None
    if not t:
        return None
    code, data = get("/laps", tracks=t["id"], limit=50)
    if code != 200:
        return None
    mine = [x for x in _items(data)
            if (x.get("driver") or {}).get("id") == who
            and isinstance(x.get("driverRating"), int)]
    if not mine:
        return None
    latest = max(mine, key=lambda x: x.get("startTime") or "")
    out = {"rating": latest["driverRating"],
           "name": f"{(me() or {}).get('firstName','')} "
                   f"{(me() or {}).get('lastName','')}".strip(),
           "when": (latest.get("startTime") or "")[:10],
           "source": "Garage 61 driver rating"}
    try:
        cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out
