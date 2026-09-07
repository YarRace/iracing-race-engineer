"""Порог развала, измеренный НА ЭТОЙ МАШИНЕ, а не выдуманный один на всех.

ЗАЧЕМ. Единый порог `CAMBER_MUCH = 6.0` срабатывал на 2% колёс Ferrari
499P, на 39% колёс Super Formula Lights и на 0% колёс Porsche 963 GTP.
Разница не в сетапе — число описывало привычку конкретной машины, а
выдавалось за физику. На одной машине оно молчало всегда, на другой
кричало на каждом втором колесе; и то и другое одинаково бесполезно.

ЕЩЁ ОДНА РАЗНИЦА, КРУПНЕЕ. На 25 записях Porsche 963 GTP (Ле-Ман, одна
машина, одна трасса — значит эффект машины и трассы здесь ни при чём)
задняя ось горячее передней по внутренней кромке:

    перед  медиана +1.02   p75 +1.64   p90 +3.48
    зад    медиана +3.41   p75 +3.97   p90 +4.55

Задняя ось оказалась горячее передней в 19 сессиях из 19, медиана
разницы +2.06 °C, ни одного обратного случая; перестановочный тест по
медианам даёт p < 0.0001 на 20000 перестановок. Значит один порог на все
четыре колеса сравнивает зад с планкой, поставленной по переду.

ЧТО ЗДЕСЬ СЧИТАЕТСЯ. Для пары «машина + ось» берётся 90-й процентиль её
собственной разницы кромок. Это прямо и означает «десятая часть самых
горячих колёс на этой машине», а не «много вообще».

СКОЛЬКО НУЖНО ДАННЫХ — ИЗМЕРЕНО, А НЕ ВЫБРАНО. Бутстрап по тем же 76
колесо-сессиям, 4000 повторов, ошибка оценки p90 против оценки по всему
набору:

        n колёс     |ошибка| p95, перед     зад
           10             1.99             0.77
           20             1.45             0.51
           24             1.45             0.38
           30             0.84             0.22

Ниже тридцати порог гуляет на полтора градуса при том, что весь разброс
укладывается в пять. Поэтому MIN_WHEELS = 30 — это пятнадцать сессий,
где машина реально выезжала. Меньше — молчим и честно говорим, что
пользуемся общим числом.

ОГОВОРКА, которую нельзя опускать: «выше, чем обычно на этой машине» —
не то же самое, что «слишком много развала». Если человек всегда ездит с
перебором, его собственный p90 переберёт вместе с ним. Поэтому рядом с
вердиктом всегда стоит само число, а на карточке написано, на чём порог
посчитан и сколько колёс за ним стоит.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re

from ire.metrics.tire import CAMBER_MUCH, CAMBER_NOISE

# Измерено бутстрапом (см. шапку): ниже этого числа оценка порога гуляет
# сильнее, чем полезна.
MIN_WHEELS = 30

# Порог = «десятая часть самых горячих колёс этой машины на этой оси».
TAIL = 0.90

FILE = "tyre_baseline.json"


def _p(values, q):
    v = sorted(values)
    return v[int(q * (len(v) - 1))]


def axle(corner):
    """F или R. Ось — не мелочь: у Porsche зад горячее переда на 2 °C."""
    return corner[1].upper()


def key(car):
    """Ключ машины. Приводим к одному виду, потому что источников два.

    Из телеметрии приходит `CarPath` — «porsche963gtp». Из истории может
    прийти отображаемое имя — «Porsche 963 GTP». Это одна машина, и
    промахнуться здесь значит молча вернуться к общему порогу, ничего не
    сказав человеку.
    """
    return re.sub(r"[^a-z0-9]", "", (car or "").lower())


def build(samples, now=None):
    """samples: {(машина, ось): [разницы кромок]} -> опись порогов.

    Пары, где данных мало, В ОПИСЬ НЕ ПОПАДАЮТ вовсе. Записать порог с
    пометкой «ненадёжный» значит рано или поздно им воспользоваться.
    """
    cars = {}
    for (car, ax), vals in sorted(samples.items()):
        vals = [v for v in vals if isinstance(v, (int, float))]
        if len(vals) < MIN_WHEELS:
            continue
        much = round(_p(vals, TAIL), 2)
        if much <= CAMBER_NOISE:
            # Машина не даёт читаемого перекоса вовсе: её собственный порог
            # оказался ниже шума измерения. Такой порог назвал бы «слишком
            # большим развалом» любое дрожание датчика.
            continue
        entry = cars.setdefault(key(car), {"name": car})
        entry[ax] = {
            "much": much,
            "n": len(vals),
            "median": round(_p(vals, 0.5), 2),
        }
    return {"built": (now or datetime.datetime.now()).strftime("%Y-%m-%d"),
            "min_wheels": MIN_WHEELS,
            "tail": TAIL,
            "cars": cars}


def path(data_dir=None):
    if data_dir is not None:
        return pathlib.Path(data_dir) / FILE
    from ire import paths
    return pathlib.Path(paths.data_dir()) / FILE


def load(data_dir=None):
    """Опись порогов или None. Нет файла — работаем на общем числе."""
    f = path(data_dir)
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return d if isinstance(d, dict) and d.get("cars") else None


def save(baseline, data_dir=None):
    f = path(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(baseline, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return f


def ref_for(baseline, car, corner):
    """Порог для этого колеса: свой или общий — и ВСЕГДА сказано, какой.

    Возвращает {"much", "basis", "n"}. basis: "car" — посчитан на его
    собственных заездах в этой машине; "default" — общее число, которое
    на разных машинах ошибается по-разному.
    """
    entry = ((baseline or {}).get("cars") or {}).get(key(car)) or {}
    ref = entry.get(axle(corner)) if corner else None
    if isinstance(ref, dict) and ref.get("much"):
        return {"much": float(ref["much"]), "basis": "car",
                "n": int(ref.get("n", 0)), "median": ref.get("median"),
                "car": entry.get("name") or car}
    return {"much": CAMBER_MUCH, "basis": "default", "n": 0,
            "median": None, "car": car}


def from_stints(stints):
    """Сырьё из истории: сохранённые стинты -> {(машина, ось): [разницы]}.

    Копится само по мере езды. Стинты, записанные до появления колонки
    `tyre_temps`, температур не содержат и просто пропускаются.
    """
    out = {}
    for s in stints or []:
        # car_path устойчив, отображаемое имя — запасной вариант.
        car = (s.get("car_path") or s.get("car") or "").strip()
        temps = s.get("tyre_temps") or {}
        if not car or not isinstance(temps, dict):
            continue
        for corner, t in temps.items():
            if not isinstance(t, dict):
                continue
            inner, outer = t.get("inner"), t.get("outer")
            if isinstance(inner, (int, float)) and isinstance(outer, (int, float)):
                out.setdefault((car, axle(corner)), []).append(inner - outer)
    return out


def refresh_from_history(conn, data_dir=None, limit=400):
    """Пересчитать опись по накопленным стинтам. Возвращает опись или None.

    Зовётся при закрытии стинта: порог обязан догонять человека. Он
    меняет сетап, меняет манеру, и планка, посчитанная в июле, к сентябрю
    описывает уже не его.

    Тихо возвращает None, когда данных ещё мало: это нормальное состояние
    первых пятнадцати сессий, а не ошибка.
    """
    from ire.storage import history

    samples = from_stints(history.recent_stints(conn, limit=limit))
    baseline = build(samples)
    if not baseline["cars"]:
        return None
    save(baseline, data_dir)
    return baseline
