"""Официальная геометрия трассы — из публичного репо iTelemetry/iracing-tracks.

SDK НЕ отдаёт форму трассы, только LapDistPct. Но по `WeekendInfo.TrackID` можно
скачать официальный SVG контура (`svgs/{id}.svg`) + конфиг (`configs/{id}.json` =
{baseline, clockwise}). Парсим bezier-путь в точки, нормализуем в бокс 0..100 и
привязываем каждую точку к LapDistPct (через baseline/направление) — тогда карта
ПОЛНАЯ и точная (не полкруга из телеметрии), а машины ставятся по LapDistPct.

Всё сетевое/парсинг — чистые функции, тестируются. Кэш на диск per-track_id.
"""
from __future__ import annotations

import json
import math
import os
import re

# jsDelivr первым (CDN, доступен там, где GitHub raw режется, напр. в РФ), raw запасным
SOURCES = [
    "https://cdn.jsdelivr.net/gh/iTelemetry/iracing-tracks@master",
    "https://raw.githubusercontent.com/iTelemetry/iracing-tracks/master",
]
RAW = SOURCES[1]                                          # совместимость
LAST_ERROR = ""                                          # почему официальная не скачалась (для UI)
_TOK = re.compile(r"[MmCcLlHhVvZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _is_num(t):
    try:
        float(t)
        return True
    except ValueError:
        return False


def _cubic(pts, p0, p1, p2, p3, steps):
    for s in range(1, steps + 1):
        tt = s / steps
        u = 1 - tt
        pts.append((u * u * u * p0[0] + 3 * u * u * tt * p1[0] + 3 * u * tt * tt * p2[0] + tt ** 3 * p3[0],
                    u * u * u * p0[1] + 3 * u * u * tt * p1[1] + 3 * u * tt * tt * p2[1] + tt ** 3 * p3[1]))


_NEED = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}


def _flatten(d, steps=12):
    """SVG-путь `d` (M/L/H/V/C/S, abs+rel, с неявным повтором) → ломаная [(x,y)]."""
    toks = _TOK.findall(d)
    pts, i, cx, cy, cmd = [], 0, 0.0, 0.0, "M"
    while i < len(toks):
        if not _is_num(toks[i]):                         # команда
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                cmd = "M"
            continue
        C = cmd.upper()
        rel = cmd.islower()
        need = _NEED.get(C, 2)
        if i + need > len(toks) or not all(_is_num(toks[i + k]) for k in range(need)):
            i += 1                                       # неполная группа — пропустить токен
            continue
        v = [float(toks[i + k]) for k in range(need)]
        i += need
        if C in ("M", "L", "T"):
            cx, cy = (cx + v[-2], cy + v[-1]) if rel else (v[-2], v[-1])
            pts.append((cx, cy))
            if C == "M":
                cmd = "l" if rel else "L"                # неявные пары после M — lineto
        elif C == "H":
            cx = cx + v[0] if rel else v[0]
            pts.append((cx, cy))
        elif C == "V":
            cy = cy + v[0] if rel else v[0]
            pts.append((cx, cy))
        elif C == "C":
            p1 = (cx + v[0], cy + v[1]) if rel else (v[0], v[1])
            p2 = (cx + v[2], cy + v[3]) if rel else (v[2], v[3])
            p3 = (cx + v[4], cy + v[5]) if rel else (v[4], v[5])
            _cubic(pts, (cx, cy), p1, p2, p3, steps)
            cx, cy = p3
        elif C in ("S", "Q"):                            # гладкая/квадратичная — упрощённо через p2,end
            p2 = (cx + v[0], cy + v[1]) if rel else (v[0], v[1])
            p3 = (cx + v[2], cy + v[3]) if rel else (v[2], v[3])
            _cubic(pts, (cx, cy), (cx, cy), p2, p3, steps)
            cx, cy = p3
        else:                                            # A и прочее — просто к концевой точке
            cx, cy = (cx + v[-2], cy + v[-1]) if rel else (v[-2], v[-1])
            pts.append((cx, cy))
    return pts


def _resample(pts, n=260):
    """Равномерно по длине дуги → n точек (плавно и легко для рендера)."""
    if len(pts) < 2:
        return pts
    cum, total = [0.0], 0.0
    for a, b in zip(pts, pts[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
        cum.append(total)
    if total <= 0:
        return pts
    out, j = [], 0
    for k in range(n):
        target = total * k / (n - 1)
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = (cum[j + 1] - cum[j]) or 1e-9
        f = (target - cum[j]) / seg
        out.append((pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f,
                    pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f))
    return out


def build_points(svg_text, baseline=0.0, clockwise=True, n=260):
    """SVG + конфиг → [{pct,x,y}] в боксе 0..100, pct привязан к LapDistPct."""
    # именно path-данные: атрибут d (не «d» внутри id=…), значение начинается с M/m
    m = re.search(r'(?<![\w-])d="\s*([Mm][^"]+)"', svg_text)
    if not m:
        return None
    pts = _resample(_flatten(m.group(1)), n)
    if len(pts) < 10:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    scale = 90.0 / max(w, h)
    ox, oy = (100 - w * scale) / 2, (100 - h * scale) / 2
    direction = -1 if clockwise else 1                   # флип: машины ехали наоборот (проверено на Монце)
    out = []
    for i, (x, y) in enumerate(pts):
        f = i / (len(pts) - 1)
        pct = (baseline + direction * f) % 1.0
        out.append({"pct": round(pct, 4),
                    "x": round(ox + (x - minx) * scale, 2),
                    "y": round(oy + (y - miny) * scale, 2)})
    out.sort(key=lambda p: p["pct"])                     # монотонный pct для привязки машин
    return out


def _cache_path(track_id):
    from ire.collector.track_map import _maps_dir
    d = _maps_dir()
    os.makedirs(d, exist_ok=True)
    # v3 — после починки калибровки. Прежние кэши строились с baseline 0 и
    # clockwise True, когда конфиг не скачался, и лежали так навсегда: точка
    # на карте отставала или убегала на треть круга. Их надо перестроить, а
    # не подправить, поэтому новое имя.
    return os.path.join(d, f"official_v3_{track_id}.json")


def fetch(track_id, timeout=8.0):
    """Официальная карта трассы по track_id (из кэша, иначе скачать с jsDelivr/raw).
    None если не вышло; причина — в модульном LAST_ERROR (для показа в UI)."""
    global LAST_ERROR
    LAST_ERROR = ""
    if not track_id:
        LAST_ERROR = "track_id empty"
        return None
    cache = _cache_path(track_id)
    try:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)                          # уже скачано ранее
    except (OSError, ValueError):
        pass
    try:
        import httpx
    except ImportError:
        LAST_ERROR = "no httpx"
        return None
    for base in SOURCES:
        host = base.split("/")[2]
        try:
            svg = httpx.get(f"{base}/svgs/{track_id}.svg", timeout=timeout, follow_redirects=True)
            if svg.status_code != 200:
                LAST_ERROR = f"not in database (id {track_id})"
                continue
            # Конфиг ОБЯЗАТЕЛЕН. В нём линия старта (baseline) и направление
            # движения — без них геометрия есть, а привязки к LapDistPct нет.
            # Раньше при неудаче молча подставлялись нули, карта строилась и
            # кэшировалась навсегда: на Road Atlanta baseline 0.383 означает,
            # что точка на карте убегала на 38% круга — проезжаешь первый
            # поворот, а на карте уже четвёртый. Карта, уверенно показывающая
            # не туда, хуже отсутствия карты: своя, из телеметрии, привязана к
            # LapDistPct по построению.
            c = None
            try:
                cfg = httpx.get(f"{base}/configs/{track_id}.json", timeout=timeout,
                                follow_redirects=True)
                if cfg.status_code == 200:
                    c = cfg.json()
            except Exception:                                # noqa: BLE001
                c = None
            if not isinstance(c, dict) or "baseline" not in c:
                LAST_ERROR = (f"no calibration for track {track_id} — the shape is "
                              f"there but nothing says where the start line is")
                continue
            pts = build_points(svg.text, c.get("baseline", 0.0), c.get("clockwise", True))
            if not pts:
                LAST_ERROR = "SVG parse failed"
                continue
            try:
                with open(cache, "w", encoding="utf-8") as f:
                    json.dump(pts, f)
            except OSError:
                pass
            LAST_ERROR = ""
            return pts
        except Exception as e:
            LAST_ERROR = f"no access to {host} ({type(e).__name__})"
            continue
    return None
