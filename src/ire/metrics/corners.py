"""Разбор круга по поворотам: где именно потеряно время и почему.

Вкладка «Time lost» уже показывала потерю по трём секторам iRacing. Три
сектора на круг — это слишком крупно, чтобы что-то с этим делать: «потерял
0.4 в первом секторе» не говорит, В КАКОМ повороте и что было не так.

Здесь круг режется на сегменты по САМОЙ телеметрии, а не по разметке
iRacing: поворот — там, где машина реально гружена вбок. Сегментов
получается столько, сколько на трассе поворотов, и каждый можно разобрать
отдельно.

Два круга сравниваются честно, потому что оба лежат на ОДНОЙ сетке по
дистанции (`storage/laps.py`, 1000 точек): в каждой точке трассы сравнимы
скорости, а не «примерно в этом месте».

Чего здесь нет намеренно: траектории. Lat/Lon в кадре круга не пишутся,
и рисовать «твоя линия против эталонной» было бы выдумкой.
"""
from __future__ import annotations

import math

MIN_SPEED = 3.0            # м/с: ниже — деление на скорость даёт мусор
MIN_PROMINENCE = 0.06      # доля размаха скорости: мельче — не поворот, а шум
MIN_CORNER_GAP = 25        # ближе друг к другу — считаем связкой, а не двумя


def _clean(seq, n):
    """Список нужной длины из чисел. Пропуски и мусор — нули."""
    out = []
    for i in range(n):
        v = seq[i] if i < len(seq) else 0.0
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        out.append(0.0 if math.isnan(v) or math.isinf(v) else v)
    return out


def find_corners(channels, points=None):
    """Апексы поворотов — по МИНИМУМАМ СКОРОСТИ, а не по боковому ускорению.

    Первая версия искала повороты по |lat_accel| выше доли от максимума.
    Работало, но неустойчиво: сдвиг порога с 0.25 на 0.28 менял разбивку
    Road Atlanta с пяти сегментов на шесть и переставлял апексы. Разбор,
    который меняется от настроечного числа, доверия не вызывает.

    Скорость надёжнее и ближе к делу: поворот — это место, где пришлось
    замедлиться. Берём локальные минимумы и оставляем те, у которых
    достаточная ВЫРАЗИТЕЛЬНОСТЬ — насколько глубоко минимум сидит
    относительно вершин по обе стороны. Так мелкая рябь на прямой
    отсеивается сама, без подбора порогов под трассу.
    """
    speed = channels.get("speed") or []
    n = points or len(speed)
    if n < 40:
        return []
    v = _clean(speed, n)
    lo, hi = min(v), max(v)
    span = hi - lo
    if span < 5.0:                        # круг за машиной безопасности
        return []

    mins = [i for i in range(1, n - 1) if v[i] <= v[i - 1] and v[i] < v[i + 1]]
    if not mins:
        return []

    kept = []
    for i in mins:
        left = max(v[:i] or [v[i]])
        right = max(v[i + 1:] or [v[i]])
        prominence = min(left, right) - v[i]
        if prominence >= span * MIN_PROMINENCE:
            kept.append((i, prominence))

    # Связки (шикана, esses) — один сегмент: разбирать их по отдельности
    # бессмысленно, время там теряется и отыгрывается разом.
    merged = []
    for i, prom in kept:
        if merged and i - merged[-1][0] < MIN_CORNER_GAP:
            if prom > merged[-1][1]:      # оставляем более выраженный
                merged[-1] = (i, prom)
        else:
            merged.append((i, prom))
    return [i for i, _ in merged]


def segments(channels, points=None):
    """Сегменты, покрывающие круг ЦЕЛИКОМ: поворот плюс подход к нему.

    Покрывать целиком важно: если сегменты — только повороты, сумма их
    потерь не сходится с разницей кругов, и таблица выглядит сломанной.
    Граница — по МАКСИМУМУ скорости между апексами, то есть по концу
    прямой. Тогда торможение и разгон достаются тому повороту, к которому
    относятся, а не соседнему.
    """
    speed = channels.get("speed") or []
    n = points or len(speed)
    apexes = find_corners(channels, n)
    if not apexes:
        return [{"index": 1, "start": 0, "end": n, "apex": n // 2}] if n else []

    v = _clean(speed, n)
    cuts = [0]
    for a, b in zip(apexes, apexes[1:]):
        cuts.append(max(range(a, b), key=lambda k: v[k]))
    cuts.append(n)

    return [{"index": i, "start": lo, "end": hi, "apex": apex}
            for i, (apex, lo, hi) in enumerate(zip(apexes, cuts, cuts[1:]), 1)]


def cell_length(speed, lap_time):
    """Длина одной ячейки сетки в метрах.

    Длину трассы мы не храним, но она выводится из круга: время круга —
    это сумма ds/v по всем ячейкам, значит ds = время / Σ(1/v).
    """
    inv = sum(1.0 / max(v, MIN_SPEED) for v in speed)
    return (lap_time / inv) if inv > 0 else 0.0


def delta_trace(lap, ref):
    """Накопленная разница по дистанции: сколько секунд потеряно к точке k.

    Итог подгоняется под настоящую разницу времён кругов. Без этого сумма
    по сегментам не сходится с разницей в шапке — на пару сотых, но именно
    такие мелочи и заставляют не верить всей таблице.
    """
    a = _clean(lap["channels"].get("speed") or [], lap["points"])
    b = _clean(ref["channels"].get("speed") or [], ref["points"])
    n = min(len(a), len(b))
    if not n:
        return []
    ds = cell_length(b[:n], float(ref["lap_time"]))

    trace, acc = [], 0.0
    for i in range(n):
        acc += ds * (1.0 / max(a[i], MIN_SPEED) - 1.0 / max(b[i], MIN_SPEED))
        trace.append(acc)

    want = float(lap["lap_time"]) - float(ref["lap_time"])
    if abs(acc) > 1e-6:
        k = want / acc
        # Поправка только если она разумная. Иначе круги несравнимы (разные
        # трассы, обрезанный круг) — лучше сырые числа, чем растянутые в разы.
        if 0.5 <= k <= 2.0:
            trace = [v * k for v in trace]
    return trace


def _phase_loss(trace, lo, hi):
    return (trace[hi - 1] if hi - 1 < len(trace) else trace[-1]) - \
           (trace[lo - 1] if lo > 0 else 0.0)


def _first(seq, lo, hi, test):
    for i in range(lo, min(hi, len(seq))):
        if test(seq[i]):
            return i
    return None


def verdict(lap, ref, seg, trace):
    """Одна фраза о том, что пошло не так в этом сегменте.

    Считается из телеметрии, без модели: ранняя точка торможения, скорость
    в апексе и момент возврата на газ — этого хватает, чтобы назвать фазу.
    Модель здесь только пересказала бы те же три числа своими словами,
    зато иногда врала бы.
    """
    ca, cb = lap["channels"], ref["channels"]
    n = min(lap["points"], ref["points"])
    lo, hi, apex = seg["start"], min(seg["end"], n), seg["apex"]

    loss = _phase_loss(trace, lo, hi) if trace else 0.0
    if abs(loss) < 0.01:
        return {"loss": loss, "phase": "none",
                "text": "Matched the reference through here."}
    if loss < 0:
        return {"loss": loss, "phase": "gain",
                "text": "You were quicker than the reference here."}

    sp_a = _clean(ca.get("speed") or [], n)
    sp_b = _clean(cb.get("speed") or [], n)
    br_a = _clean(ca.get("brake") or [], n)
    br_b = _clean(cb.get("brake") or [], n)
    th_a = _clean(ca.get("throttle") or [], n)
    th_b = _clean(cb.get("throttle") or [], n)

    entry = _phase_loss(trace, lo, apex)
    exit_ = _phase_loss(trace, apex, hi)

    brake_a = _first(br_a, lo, apex, lambda v: v > 0.2)
    brake_b = _first(br_b, lo, apex, lambda v: v > 0.2)
    gas_a = _first(th_a, apex, hi, lambda v: v > 0.8)
    gas_b = _first(th_b, apex, hi, lambda v: v > 0.8)

    v_apex_a = min(sp_a[lo:hi]) if hi > lo else 0.0
    v_apex_b = min(sp_b[lo:hi]) if hi > lo else 0.0

    braked = brake_a is not None and brake_b is not None
    if braked and brake_a < brake_b - 3 and entry > 0.01:
        m = round((brake_b - brake_a) * 100.0 / n * 10)   # грубо, в метрах круга
        return {"loss": loss, "phase": "braking",
                "text": f"You braked earlier than the reference "
                        f"(about {m} m) and lost {entry:.2f}s on entry."}

    if v_apex_a < v_apex_b - 1.0 and entry > 0.005:
        return {"loss": loss, "phase": "apex",
                "text": f"Your minimum speed was {(v_apex_b - v_apex_a) * 3.6:.0f}"
                        f" km/h lower — {loss:.2f}s through the corner."}

    if gas_a is not None and gas_b is not None and gas_a > gas_b + 3 and exit_ > 0.01:
        return {"loss": loss, "phase": "exit",
                "text": f"You got back to full throttle later and lost "
                        f"{exit_:.2f}s on the exit."}

    if not braked and min(th_a[lo:hi] or [0]) > 0.9:
        return {"loss": loss, "phase": "flat",
                "text": f"Flat out through here, {loss:.2f}s slower — "
                        f"you arrived with less speed."}

    where = "on entry" if entry >= exit_ else "on the exit"
    return {"loss": loss, "phase": "entry" if entry >= exit_ else "exit",
            "text": f"Lost {loss:.2f}s here, most of it {where}."}


def analyse(lap, ref):
    """Полный разбор круга против эталона.

    Возвращает всё, что нужно нарисовать: сегменты с потерями и вердиктом,
    накопленную дельту и обе трассы скорости для графика.
    """
    if not lap or not ref or not lap.get("channels") or not ref.get("channels"):
        return {"ok": False, "reason": "need two laps with telemetry"}
    if lap.get("track") != ref.get("track"):
        return {"ok": False, "reason": "laps are from different tracks"}

    n = min(lap.get("points") or 0, ref.get("points") or 0)
    if n < 50:
        return {"ok": False, "reason": "lap is too short to split"}

    trace = delta_trace(lap, ref)

    # Сумма по сегментам ОБЯЗАНА сойтись с разницей кругов. Когда не сходится,
    # круги не выровнены — например у одного обрезано начало, и недостающее
    # место заполнено ровной полкой на постоянной скорости. 31.08.2026 такой
    # круг дал «+19.8с в первом повороте» при разнице круга в одну секунду.
    # Показать эти числа как ни в чём не бывало хуже, чем не показать ничего.
    want = (lap.get("lap_time") or 0) - (ref.get("lap_time") or 0)
    got = trace[-1] if trace else 0.0
    if abs(got - want) > max(0.15, abs(want) * 0.25):
        return {"ok": False, "reason":
                "these two laps do not line up — one of them is missing part "
                "of the lap, so the per-corner numbers would be made up",
                "delta": want, "raw_sum": got}

    segs = []
    for seg in segments(lap["channels"], n):
        v = verdict(lap, ref, seg, trace)
        segs.append({**seg, **v})

    return {
        "ok": True,
        "track": lap.get("track_display") or lap.get("track"),
        "car": lap.get("car"),
        "lap_time": lap.get("lap_time"),
        "ref_time": ref.get("lap_time"),
        "delta": (lap.get("lap_time") or 0) - (ref.get("lap_time") or 0),
        "points": n,
        "segments": segs,
        "trace": trace,
        "speed": _clean(lap["channels"].get("speed") or [], n),
        "ref_speed": _clean(ref["channels"].get("speed") or [], n),
        "throttle": _clean(lap["channels"].get("throttle") or [], n),
        "ref_throttle": _clean(ref["channels"].get("throttle") or [], n),
        "brake": _clean(lap["channels"].get("brake") or [], n),
        "ref_brake": _clean(ref["channels"].get("brake") or [], n),
    }


def pick_reference(laps_meta, lap_meta):
    """Эталон — лучший сохранённый круг на той же трассе и машине.

    На той же МАШИНЕ обязательно: круг GTP не эталон для GT3, разница
    в двадцать секунд превратит разбор в шум.
    """
    same = [m for m in laps_meta
            if m.get("track") == lap_meta.get("track")
            and m.get("car") == lap_meta.get("car")
            and m.get("path") != lap_meta.get("path")
            and isinstance(m.get("lap_time"), (int, float))]
    if not same:
        return None
    return min(same, key=lambda m: m["lap_time"])
