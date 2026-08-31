"""Командный план стинтов на эндуранс: кто, когда и сколько едет.

Вкладка Strategy отвечала на личные вопросы — хватит ли топлива, когда
заезжать. На командный вопрос «во сколько мне садиться за руль» она не
отвечала никак, а на 24-часовой гонке это главный вопрос: пилоты живут
в разных часовых поясах и спят между сменами.

Отсюда план на всю гонку целиком: список стинтов с водителями, временем
старта и конца, кругами, топливом и пит-стопом между ними. Время
показывается и от старта гонки, и по НАСТОЯЩИМ часам каждого пилота —
«стинт 14 начинается через 9 часов 40 минут» бесполезно, когда надо
поставить будильник.

Считается детерминированно из тех же чисел, что уже собирает стратегия:
расход на круг, объём бака, темп. Никакой модели здесь нет и не нужно —
это арифметика, и она обязана сходиться.
"""
from __future__ import annotations

import datetime

MIN_LAP = 20.0            # с: быстрее — это не круг, а ошибка в данных
MIN_TANK = 1.0            # л
DEFAULT_PIT = 60.0        # с: заправка плюс проезд пит-лейна


def _num(v, default=0.0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if v != v or v in (float("inf"), float("-inf")) else v


def stint_laps(tank, fuel_per_lap, max_minutes=None, lap_time=None):
    """Сколько кругов помещается в один стинт.

    Ограничений два, и берётся жёсткое из них: бак и правило гонки на
    длину стинта (в некоторых сериях оно есть). Дробный круг не считается:
    доехать «полкруга на топливе» нельзя.
    """
    tank, fuel_per_lap = _num(tank), _num(fuel_per_lap)
    if tank < MIN_TANK or fuel_per_lap <= 0:
        return 0
    by_fuel = int(tank // fuel_per_lap)
    if max_minutes and lap_time and _num(lap_time) >= MIN_LAP:
        by_rule = int((max_minutes * 60.0) // _num(lap_time))
        return max(1, min(by_fuel, by_rule))
    return max(1, by_fuel)


def plan(race_seconds, drivers, lap_time, fuel_per_lap, tank,
         pit_seconds=DEFAULT_PIT, start=None, max_stint_minutes=None):
    """Полный план гонки. Возвращает список стинтов и сводку.

    Последний стинт УКОРАЧИВАЕТСЯ до финиша, а не округляется вверх: план,
    который обещает на два круга больше, чем длится гонка, заставляет
    заправляться под финиш без нужды — а это лишние 30 секунд.
    """
    race_seconds = _num(race_seconds)
    lap_time = _num(lap_time)
    names = [str(d).strip() for d in (drivers or []) if str(d).strip()]
    if race_seconds <= 0 or lap_time < MIN_LAP or not names:
        return {"ok": False, "reason": "need race length, lap time and drivers",
                "stints": [], "summary": {}}

    per_stint = stint_laps(tank, fuel_per_lap, max_stint_minutes, lap_time)
    if per_stint <= 0:
        return {"ok": False, "reason": "need tank size and fuel per lap",
                "stints": [], "summary": {}}

    total_laps = int(race_seconds // lap_time)
    if total_laps <= 0:
        return {"ok": False, "reason": "race is shorter than one lap",
                "stints": [], "summary": {}}

    pit = _num(pit_seconds, DEFAULT_PIT)
    stints, t, laps_left, i = [], 0.0, total_laps, 0
    while laps_left > 0 and len(stints) < 400:      # 400 — защита от зацикливания
        laps = min(per_stint, laps_left)
        length = laps * lap_time
        last = laps_left - laps <= 0
        stints.append({
            "n": len(stints) + 1,
            "driver": names[i % len(names)],
            "start": t,
            "end": t + length,
            "seconds": length,
            "laps": laps,
            "fuel": round(laps * _num(fuel_per_lap), 1),
            "pit_after": None if last else pit,
        })
        t += length + (0.0 if last else pit)
        laps_left -= laps
        i += 1

    return {"ok": True, "stints": stints,
            "summary": summary(stints, names, race_seconds, pit),
            "start": start}


def summary(stints, drivers, race_seconds=0.0, pit_seconds=DEFAULT_PIT):
    """Итоги плана — то же, что показывает вкладка Analytics у iRacePlan."""
    if not stints:
        return {}
    laps = sum(s["laps"] for s in stints)
    by_driver = {}
    for s in stints:
        d = by_driver.setdefault(s["driver"], {"driver": s["driver"], "laps": 0,
                                               "stints": 0, "seconds": 0.0})
        d["laps"] += s["laps"]
        d["stints"] += 1
        d["seconds"] += s["seconds"]
    for d in by_driver.values():
        d["share"] = round(d["laps"] * 100.0 / laps, 1) if laps else 0.0

    longest = max(stints, key=lambda s: s["seconds"])
    shares = [d["laps"] for d in by_driver.values()]
    fair = (max(shares) - min(shares)) <= max(1, round(laps * 0.05))
    # Подряд два стинта одному пилоту — это не ошибка, но об этом надо
    # сказать: человек за рулём полтора часа без перерыва.
    back_to_back = sum(1 for a, b in zip(stints, stints[1:])
                       if a["driver"] == b["driver"])
    return {
        "laps": laps,
        "stints": len(stints),
        "pit_stops": sum(1 for s in stints if s["pit_after"]),
        "pit_seconds": sum(s["pit_after"] or 0.0 for s in stints),
        "avg_stint": sum(s["seconds"] for s in stints) / len(stints),
        "longest": {"n": longest["n"], "driver": longest["driver"],
                    "seconds": longest["seconds"]},
        "drivers": sorted(by_driver.values(), key=lambda d: -d["laps"]),
        "fair_share": round(laps / len(drivers), 1) if drivers else 0.0,
        "balanced": fair,
        "back_to_back": back_to_back,
        "race_seconds": race_seconds,
        "planned_seconds": stints[-1]["end"],
    }


def with_clock(stints, start_iso, offsets=None):
    """Добавить настоящее время начала и конца каждого стинта.

    Без часов план бесполезен ночью: «стинт 14 через 9 часов 40 минут» не
    ставится будильником, а «03:41 по твоему времени» — ставится. Смещение
    задаётся на пилота в часах: команда собирается из разных стран, и это
    ровно та мелочь, из-за которой человек просыпает свою смену.
    """
    try:
        t0 = datetime.datetime.fromisoformat(str(start_iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return stints
    offsets = offsets or {}
    out = []
    for s in stints:
        a = t0 + datetime.timedelta(seconds=s["start"])
        b = t0 + datetime.timedelta(seconds=s["end"])
        off = _num(offsets.get(s["driver"]), 0.0)
        shift = datetime.timedelta(hours=off)
        out.append({**s,
                    "clock_start": a.strftime("%d %b %H:%M"),
                    "clock_end": b.strftime("%d %b %H:%M"),
                    "local_start": (a + shift).strftime("%d %b %H:%M"),
                    "local_end": (b + shift).strftime("%d %b %H:%M"),
                    "tz_offset": off})
    return out


def from_live(strategy, session, drivers, pit_seconds=DEFAULT_PIT,
              start=None, offsets=None, max_stint_minutes=None):
    """План из живых данных: расход и темп берутся из того, как ты едешь.

    Именно из живых, а не из справочника: расход зависит от того, как
    сегодня едут, а не от того, что написано в характеристиках машины.
    """
    strategy = strategy or {}
    session = session or {}
    left = session.get("time_remain")
    if not _num(left):
        left = session.get("time_total")
    res = plan(left, drivers,
               strategy.get("avg_lap_time"), strategy.get("avg_burn"),
               strategy.get("tank"), pit_seconds, start, max_stint_minutes)
    if res["ok"] and start:
        res["stints"] = with_clock(res["stints"], start, offsets)
    return res
