"""Tyre Tool: что температуры и давления шин говорят про сетап.

ОТКУДА ПОРОГИ. Измерены по .ibt из сессий Ярослава — но с ДВУМЯ важными
оговорками, которых в первой версии этой шапки не было.

Первая: числа, стоявшие здесь раньше, были посчитаны на ГРЯЗНОМ наборе — в
него попали девять сессий, где машина не выезжала из боксов, а тот же модуль
ниже велит такие выбрасывать. Правильные числа (96 колесо-сессий, только
ездившие) заметно другие на нижнем конце:

    внутренняя минус внешняя кромка      середина минус кромки
        25%   +1.11   (было +0.0)            25%   -0.49   (было -0.20)
        50%   +2.28   (было +1.2)            50%   +0.48   (было +0.00)
        75%   +5.12   (было +4.1)            75%   +1.61   (было +0.89)
        95%   +7.58                          95%   +2.45

Вторая, важнее: ПОРОГ НЕ УНИВЕРСАЛЕН, и это измерено, а не предположено.
CAMBER_MUCH срабатывает на 2% колёс Ferrari 499P и на 39% колёс Super
Formula Lights — разница в двадцать раз. Значит число описывает не «слишком
большой развал вообще», а привычку конкретной машины.

Менять его пока не на что: телеметрия есть по трём машинам, причём у
третьей всего одна сессия, и машина с трассой в этих записях не разделены
(Ferrari ездил только Road Atlanta, SF Lights только Road America) — любой
эффект можно с равным правом приписать трассе. Половина реального пробега (303 круга на
Porsche и Cadillac) телеметрии не оставила вовсе. Перемерить, когда данных
станет больше, помогает tools/measure_tyres.py.

Ровно поэтому в ответе всегда стоит и само число: если полоса ошибается,
число остаётся верным.

ЧЕГО ЗДЕСЬ НЕТ. Целевых давлений «по машине», как в Go Fast, здесь нет и
выдумать их нельзя: у нас нет ни одного источника, где написано, сколько
должно быть на Ferrari 499P. Вместо выдумки — две честные опоры:

  • физика протектора, одинаковая для всех машин: горячая внутренняя кромка
    значит избыток развала, горячая середина — перекачано;
  • ЕГО СОБСТВЕННЫЕ данные: `target_from_history()` берёт давления и
    температуры с самого быстрого стинта на этой машине и трассе. Такая цель
    не выдумана — она уже была на машине, и круг по ней уже проехан.

Второе начнёт работать, когда накопятся стинты с записанными давлениями:
до сегодняшнего дня они не сохранялись вовсе.
"""
from __future__ import annotations

import re

from ire.metrics.tire import CAMBER_MUCH, CAMBER_NOISE, camber   # noqa: F401

CORNERS = ("LF", "RF", "LR", "RR")
SETUP_CORNER = {"LF": "LeftFront", "RF": "RightFront",
                "LR": "LeftRear", "RR": "RightRear"}

# CAMBER_NOISE, CAMBER_MUCH и сам вердикт camber() живут в metrics/tire.py —
# там же, где понятие кромки. Держать их в двух местах уже пробовали: числа
# разошлись, и 15 колёс из 96 получали «even» от одного модуля и «too much
# camber» от другого.
#
# Корона: σ 1.33 на чистых данных, 95-й процентиль +2.45.
CROWN_BAND = 2.5

# Сессия, в которой машина не ездила, всё равно даёт температуры — от
# подогрева и воздуха, — но кромки в ней расходятся ровно на ноль. Это видно
# в его файлах без исключений:
#
#     максимум 0–60 км/ч (гараж, пит-лейн)  →  перекос кромок  0.0 … -0.7
#     максимум 234–308 км/ч (реальные круги) →  перекос кромок +1.4 … +9.3
#
# Поэтому вердикт «менять нечего» выдаётся ТОЛЬКО когда машина правда ездила.
# Иначе выходит ложное успокоение: на непрогретых шинах не видно ничего, а
# звучит это как «всё в порядке».
MOVING_MS = 15.0            # м/с ≈ 54 км/ч: быстрее, чем катятся по пит-лейну
MIN_MOVING = 300            # кадров в движении — меньше не о чем говорить

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _num(v):
    """Число из «152 kPa» / «25.5 psi» / 152. None, если числа нет вовсе."""
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUM.search(str(v or ""))
    return float(m.group()) if m else None


def _unit(v):
    s = str(v or "")
    for u in ("kPa", "psi", "bar"):
        if u.lower() in s.lower():
            return u
    return ""


def pressures(fields):
    """Давления по колёсам из CarSetup. {} — если машина их не отдаёт.

    Путь к полю у разных машин разный (TiresAero.*, Chassis.* и так далее),
    поэтому ищем по ИМЕНИ угла и окончанию, а не по одному жёсткому пути:
    жёсткий путь молча давал бы пустоту на половине машин.
    """
    out = {}
    for c, name in SETUP_CORNER.items():
        row = {}
        for key, val in (fields or {}).items():
            if name not in key:
                continue
            tail = key.rsplit(".", 1)[-1]
            if tail == "StartingPressure":
                row["cold"], row["unit"], row["shown"] = _num(val), _unit(val), str(val)
            elif tail == "LastHotPressure":
                row["hot"] = _num(val)
        if row.get("cold") is not None or row.get("hot") is not None:
            out[c] = row
    return out


def crown(mid, inner, outer):
    """Середина против кромок: перекачано / недокачано / в норме."""
    if None in (mid, inner, outer):
        return "unknown", None
    d = round(mid - (inner + outer) / 2, 1)
    if d > CROWN_BAND:
        return "high", d
    if d < -CROWN_BAND:
        return "low", d
    return "even", d


WHY = {
    "too_much": "inner edge much hotter — too much negative camber",
    "not_enough": "outer edge hotter — not enough negative camber",
    "working": "inner edge slightly hotter — camber is doing its job",
    "even": "edges are even",
    "high": "middle hotter than the edges — pressure is high",
    "low": "middle cooler than the edges — pressure is low",
    "unknown": "not enough data",
}


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 1) if xs else None


def moving_frames(frames):
    """Сколько кадров машина реально ехала, а не стояла в боксах."""
    return sum(1 for f in (frames or [])
               if isinstance(f.get("speed"), (int, float)) and f["speed"] > MOVING_MS)


def report(temps, fields=None, frames=None):
    """Свод по четырём колёсам: что видно и что с этим делать.

    temps — то, что вернул `tire.tire_metrics`.
    frames — кадры телеметрии, если есть: по ним проверяется, что машина
    вообще ездила. Без них вердикт даётся как раньше.
    """
    if not temps:
        return {"ok": False, "reason": "no tyre temperatures in this session"}

    if frames is not None and moving_frames(frames) < MIN_MOVING:
        return {"ok": False,
                "reason": "the car barely moved in this session — the tyre "
                          "edges say nothing yet",
                "moving": moving_frames(frames)}

    press = pressures(fields or {})
    corners = {}
    for c in CORNERS:
        t = temps.get(c) or {}
        cam, cam_d = camber(t.get("inner"), t.get("outer"))
        crw, crw_d = crown(t.get("tm"), t.get("inner"), t.get("outer"))
        corners[c] = {
            "inner": t.get("inner"), "middle": t.get("tm"), "outer": t.get("outer"),
            "camber": cam, "camber_delta": cam_d, "camber_why": WHY[cam],
            "crown": crw, "crown_delta": crw_d, "crown_why": WHY[crw],
            "pressure": press.get(c) or {},
        }

    todo = []
    for c in CORNERS:
        v = corners[c]
        if v["camber"] in ("too_much", "not_enough"):
            todo.append({"corner": c, "what": "camber", "why": v["camber_why"],
                         "delta": v["camber_delta"]})
        if v["crown"] in ("high", "low"):
            todo.append({"corner": c, "what": "pressure", "why": v["crown_why"],
                         "delta": v["crown_delta"]})

    # Средняя температура идёт рядом с вердиктом НАМЕРЕННО. На выездном круге
    # шины у него были 36°, кромки сошлись в ноль — и «менять нечего» звучало
    # бы как «сетап хорош», хотя на холодной резине просто ничего не видно.
    # Задавать «рабочий диапазон по машине» мы не можем: такого источника у
    # нас нет, и выдумывать его — то же враньё, только с цифрой. А число
    # человек прочтёт сам и поймёт, холодные они были или нет.
    mean_temp = _mean([corners[c]["middle"] for c in CORNERS])

    return {"ok": True,
            "corners": corners,
            "mean_temp": mean_temp,
            "balance": temps.get("front_rear_balance"),
            "front_camber": _mean([corners[c]["camber_delta"] for c in ("LF", "RF")]),
            "rear_camber": _mean([corners[c]["camber_delta"] for c in ("LR", "RR")]),
            "todo": todo,
            # Пустой список — это ответ, а не молчание: «всё в порядке» надо
            # сказать вслух, иначе пустая карточка читается как поломка.
            "verdict": "nothing to change on the tyres" if not todo else "",
            "have_pressures": bool(press)}


def target_from_history(stints):
    """Цель = что стояло на машине в самом быстром стинте на этой связке.

    Такую цель не надо выдумывать: круг по ней уже проехан. Работает только
    по стинтам, где давления записаны; до сегодняшнего дня они не писались,
    поэтому на старых стинтах вернётся None — и это честнее подставленного
    числа неизвестного происхождения.
    """
    good = [s for s in (stints or [])
            if s.get("mean_lap") and (s.get("pressures") or s.get("tyre_temps"))]
    if not good:
        return None
    best = min(good, key=lambda s: s["mean_lap"])
    return {"from_stint": best.get("id"), "when": best.get("ts"),
            "mean_lap": best.get("mean_lap"), "laps": best.get("laps"),
            "pressures": best.get("pressures"), "tyre_temps": best.get("tyre_temps")}
