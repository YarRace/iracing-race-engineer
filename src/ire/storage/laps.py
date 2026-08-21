"""Телеметрия круга на диске — то, без чего невозможен разбор круга.

Раньше кадры жили только в памяти `run.py` и обнулялись при смене сессии.
В историю писалось лишь время круга и три сектора, а формы торможения,
точки первого газа и скорости в апексе не оставалось нигде. Поэтому «где
я потерял время в седьмом повороте» ответить было не из чего.

Каждый круг ресемплится на сетку ПО ДИСТАНЦИИ и кладётся отдельным файлом.
Сетка по дистанции, а не по времени, принципиальна: два круга с разным
временем нужно сравнивать в одной и той же точке трассы, иначе к концу
круга графики разъезжаются и разница читается как ошибка там, где её нет.

Сетка задана в долях круга, а не в метрах: SDK не отдаёт длину трассы.
POINTS=1000 — это 0.1% дистанции, около пяти метров на пятикилометровой
трассе, чего хватает даже для точки начала торможения.

Формат — gzip поверх JSON: без внешних зависимостей, читается любым
инструментом, круг весит порядка 30 КБ. Файлы лежат в data/laps/, папка
уже в .gitignore.
"""
import gzip
import json
import pathlib

from . import history

POINTS = 1000

# Каналы, которые нужны для разбора круга. Температуры и износ сюда не
# попадают: они меняются на масштабе стинта, а не поворота, и хранятся
# в метаданных одним значением.
CHANNELS = ("speed", "throttle", "brake", "steer", "gear",
            "lat_accel", "long_accel", "yaw_rate")


def default_root():
    """data/laps рядом с базой истории."""
    return pathlib.Path(history.default_path()).parent / "laps"


def split_laps(frames):
    """Режет поток кадров на круги. Возвращает [(номер, кадры), …].

    Неполные круги отбрасываются. Первый круг почти всегда начинается
    с середины (выезд из боксов), последний обрывается на входе в них —
    сравнивать по ним нельзя, а испортить статистику они могут.
    """
    if not frames:
        return []
    out, cur, num = [], [], frames[0].get("lap")
    for f in frames:
        if f.get("lap") != num:
            out.append((num, cur))
            cur, num = [], f.get("lap")
        cur.append(f)
    out.append((num, cur))

    full = []
    for n, fr in out:
        if len(fr) < 10:
            continue
        p = [x.get("lap_dist_pct") for x in fr if x.get("lap_dist_pct") is not None]
        # круг считаем полным, если он начался у линии и дошёл до конца
        if p and min(p) < 0.05 and max(p) > 0.95:
            full.append((n, fr))
    return full


def lap_time(frames):
    """Длительность круга по меткам времени кадров."""
    ts = [f.get("t") for f in frames if f.get("t") is not None]
    return (max(ts) - min(ts)) if len(ts) >= 2 else None


def resample(frames, points=POINTS):
    """Каналы на равномерной сетке по доле дистанции.

    Кадры сортируются по дистанции: SDK изредка отдаёт долю с дрожанием
    назад, и без сортировки линейная интерполяция даёт пилу.
    """
    pts = [(f.get("lap_dist_pct"), f) for f in frames if f.get("lap_dist_pct") is not None]
    if len(pts) < 2:
        return {}
    pts.sort(key=lambda x: x[0])
    xs = [p for p, _ in pts]

    out = {}
    for ch in CHANNELS:
        ys = [_num(f.get(ch)) for _, f in pts]
        out[ch] = [_interp(xs, ys, i / (points - 1)) for i in range(points)]
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _interp(xs, ys, x):
    """Линейная интерполяция по возрастающему xs. За краями — крайнее значение."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:                       # двоичный поиск: круг из 1000 точек
        mid = (lo + hi) // 2                 # иначе строится за квадрат
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    dx = xs[hi] - xs[lo]
    if dx <= 0:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / dx


def _slug(s):
    """Имя файла из произвольной строки: без пробелов и служебных символов."""
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in (s or "unknown").lower()]
    return "".join(keep).strip("-") or "unknown"


def save_lap(root, identity, lap_num, lap_t, frames, valid=None):
    """Пишет круг на диск. Возвращает путь либо None, если круг не годится.

    Невалидные круги (заезд в боксы, обрыв) не пишутся: база эталонов
    засоряется мгновенно, а пользы от таких кругов нет.
    """
    if valid is None:
        valid = history.is_valid_lap(lap_t)
    if not valid:
        return None
    ch = resample(frames)
    if not ch:
        return None

    first = frames[0]
    meta = {
        "track": identity.get("track"), "track_display": identity.get("track_display"),
        "config": identity.get("config"), "car": identity.get("car"),
        "car_path": identity.get("car_path"), "car_class": identity.get("car_class"),
        "session_type": identity.get("session_type"),
        "lap_num": lap_num, "lap_time": lap_t, "points": POINTS,
        # условия круга: без них нельзя честно выбрать эталон — круг на полном
        # баке по холодной трассе несравним с кругом на пустом по горячей
        "fuel_start": _num(first.get("fuel")),
        "track_temp": _num(first.get("track_temp")),
        "air_temp": _num(first.get("air_temp")),
        "ts": history._now(),
    }

    d = pathlib.Path(root) / _slug(identity.get("track"))
    d.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(identity.get('car'))}-{meta['ts'][:19].replace(':', '')}-l{lap_num}.json.gz"
    path = d / name
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({**meta, "channels": ch}, fh, separators=(",", ":"))
    return path


def load_lap(path):
    """Круг целиком: метаданные и каналы."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def list_laps(root, track=None, car=None):
    """Метаданные сохранённых кругов, от быстрого к медленному.

    Каналы не читаются — только шапка файла, поэтому список строится быстро
    даже на тысяче кругов. Битые файлы пропускаются молча: один сбой записи
    не должен ломать весь экран сравнения.
    """
    root = pathlib.Path(root)
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*.json.gz")):
        try:
            m = load_lap(p)
        except Exception:
            continue
        if track and m.get("track") != track:
            continue
        if car and m.get("car") != car:
            continue
        m.pop("channels", None)
        m["path"] = str(p)
        out.append(m)
    out.sort(key=lambda m: (m.get("lap_time") is None, m.get("lap_time")))
    return out
