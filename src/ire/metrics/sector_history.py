"""Разбор секторов ПОСЛЕ заезда: что теряется каждый круг, а что разово.

Виджет секторов в оверлее живой — он показывает отставание прямо сейчас. Но
живьём не отличить двух разных болезней. Сектор, стабильно медленнее на две
десятых, — это сетап или техника, и лечится он в гараже. Сектор, потерявший
три секунды в одном круге, — ошибка, и в гараже с ней делать нечего. Одно
число «потеряно 3.2с» уводит не в ту сторону.

Опора — МЕДИАНА, а не среднее: один заезд в бокс добавляет к сектору 37
секунд (измерено на базе Ярослава — Монца, круг 18), и среднее после такого
круга описывает пит-стоп, а не езду.

Про «стабильно» разрешено говорить не всегда. Разделимость проверяется
стандартной ошибкой медианы (1.253·1.4826·MAD/√n — обе константы взяты из
статистики, а не подобраны под трассу). Порог MIN_STABLE_LAPS измерен на
настоящей базе (508 кругов после дедупа; подвыборки из четырёх заездов по
41–47 кругов): правило ошибалось в 52% случаев на трёх кругах, 39% на пяти,
21% на восьми, 12% на десяти, 9% на двенадцати, 4% на пятнадцати. Ниже
двенадцати модуль молчит и объясняет, чего не хватает. Число, неверное в
половине случаев, хуже, чем отсутствие числа.
"""
from __future__ import annotations

import datetime
import math
import statistics

MIN_STABLE_LAPS = 12       # измерено: ниже правило ошибается чаще 1 раза из 10
RUN_GAP_S = 1800.0         # перерыв больше получаса — это уже другой выезд
_SE_MEDIAN = 1.253         # ст. ошибка медианы против ст. ошибки среднего
_MAD_TO_SIGMA = 1.4826     # MAD нормального распределения → сигма
# Во сколько раз сектор должен быть длиннее типичного, чтобы это перестало
# быть ездой. Измерено по 1101 замеру сектор-круг из его базы:
#
#     обычная езда, включая ошибки   до ×1.47   (90% укладываются в ×1.02)
#     ПУСТО                          ×1.47 … ×2.58
#     заезды в боксы и вылеты        от ×2.58   (до ×4.94)
#
# ×1.8 стоит посреди пустоты. Первая версия отсекала по пяти сигмам времени
# КРУГА, и это было неверно: у ровно едущего человека сигма мала, и правило
# выбрасывало настоящие ошибки вместе с питами. Отношение к типичному от
# ровности езды не зависит вовсе.
_NOT_DRIVING = 1.8
# Полсекунды — это округление времён до сотых, а не пропущенный сектор.
_ROUNDING = 0.5
# Меньше трёх кругов разбирать нечем: медиана из двух — это просто среднее,
# и фильтр пит-кругов тоже не работает (ему нужен типичный сектор, которого
# из двух значений не получить). На настоящем заезде в два круга выходило
# «типичный S1 = 116.95» при лучшем 10.33 — это заезд в боксы, поделённый
# пополам, и выдавать такое за разбор нельзя.
MIN_LAPS = 3
# Сумма лучших секторов обязана быть близка к лучшему кругу. Если она меньше
# на проценты — значит сектора покрывают не весь круг, и число врёт: на
# старой Монце выходило 64.6 при лучшем круге 95.97.
_OPTIMAL_SANE = 0.95


def _ts(v):
    try:
        return datetime.datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _mad(v, med):
    return statistics.median([abs(x - med) for x in v])


def _key(r):
    return (r.get("track"), r.get("config"), r.get("car"), r.get("session_type"))


def _numeric(sectors):
    return bool(sectors) and all(isinstance(x, (int, float)) and x > 0
                                 for x in sectors)


def dedupe(rows):
    """Убирает круги, записанные дважды.

    В базе Ярослава таких 53 из 637 (8%): одинаковые ts/lap_num/lap_time —
    два писателя на одну базу. Дубль вдвое занижает разброс, и правило
    «стабильно теряет» становится самоуверенным на ровном месте.

    Ключ длинный НАМЕРЕННО. По короткому (ts, lap_num, lap_time) лишних
    выходит 114, потому что 61 пара — это разные трассы и сессии, попавшие
    в одну секунду. Короткий ключ съел бы настоящие круги.
    """
    seen, out = set(), []
    for r in rows:
        k = (r.get("ts"), _key(r), r.get("lap_num"), r.get("lap_time"))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def split_runs(rows, gap=RUN_GAP_S):
    """Режет круги на ЗАЕЗДЫ: смена трассы или машины, откат номера круга,
    перерыв больше получаса.

    Считать «стабильность» через две недели и другой сетап — это считать
    двух разных гонщиков за одного.
    """
    if not rows:
        return []
    runs, cur = [], [rows[0]]
    for prev, r in zip(rows, rows[1:]):
        a, b = _ts(prev.get("ts")), _ts(r.get("ts"))
        far = bool(a and b and (b - a).total_seconds() > gap)
        back = (r.get("lap_num") or 0) < (prev.get("lap_num") or 0)
        if far or back or _key(r) != _key(prev):
            runs.append(cur)
            cur = []
        cur.append(r)
    runs.append(cur)
    return [r for r in runs if r]


def clean(laps):
    """Круги, на которых человек ЕХАЛ: без заездов в боксы и вылетов.

    Смотрим на СЕКТОР, а не на время круга, и на отношение, а не на сигмы.
    Заезд в боксы растягивает свой сектор втрое (S1 на Спа: 108 секунд при
    типичных 33.8), а ошибка — на проценты. Между ними в его данных пусто,
    и порог стоит ровно в этой пустоте.

    Важно, что ошибки при этом ОСТАЮТСЯ: их и надо показать в графе
    «разово». Первая версия резала по пяти сигмам времени круга, и у ровно
    едущего человека сигма выходила такой маленькой, что вместе с питами
    выбрасывались настоящие ошибки на две-три секунды.
    """
    good = [l for l in laps if _numeric(l.get("sectors"))]
    if len(good) < 3:
        return list(laps)
    n = len(good[0]["sectors"])
    meds = [statistics.median([l["sectors"][i] for l in good]) for i in range(n)]
    return [l for l in good
            if all(m <= 0 or l["sectors"][i] <= m * _NOT_DRIVING
                   for i, m in enumerate(meds))]


def report(laps):
    """Итог заезда по секторам: что теряется каждый круг, а что разово."""
    laps = dedupe(laps)
    lens = [len(l.get("sectors") or []) for l in laps if _numeric(l.get("sectors"))]
    if not lens:
        return {"ok": False, "reason":
                "no lap in this run has a complete set of sector times — the "
                "track had no split points, or every lap was an out-lap"}

    # Самая частая длина, а не максимум: у выезда из боксов первого сектора
    # нет, и по максимуму такой круг задал бы длину, под которую не подходит
    # ни один нормальный круг.
    n = max(set(lens), key=lens.count)
    good = [l for l in laps if _numeric(l.get("sectors")) and len(l["sectors"]) == n]
    base = clean(good)
    if len(base) < MIN_LAPS:
        return {"ok": False, "reason":
                f"only {len(base)} clean lap{'s' if len(base) != 1 else ''} in this "
                f"run — it takes {MIN_LAPS} before a typical lap means anything"}

    out = []
    for i in range(n):
        v = [l["sectors"][i] for l in base]
        best, med = min(v), statistics.median(v)
        sigma = _MAD_TO_SIGMA * _mad(v, med)
        se = _SE_MEDIAN * sigma / math.sqrt(len(v))
        every = med - best
        # Разовое ищем по ЧИСТЫМ кругам, а не по всем. Первая версия брала
        # все, и на Спа выходило «разово потеряно 129.50с в S1» — это два
        # заезда в боксы (S1 = 85 и 108 секунд при типичных 33.8), а не
        # ошибка, которую можно исправить. Настоящие ошибки при этом
        # остаются: фильтр отсекает сектора длиннее типичного в 1.8 раза,
        # а ошибка растягивает сектор на проценты, не в разы.
        exc = sorted(((l.get("lap_num"), l["sectors"][i] - med)
                      for l in base if l["sectors"][i] > med),
                     key=lambda x: -x[1])
        bucket = sum(e for _, e in exc)
        # Называем круги, дающие БОЛЬШЕ ПОЛОВИНЫ разовой потери. Правило
        # большинства, а не подобранный порог: если превышение размазано по
        # тридцати кругам, список выйдет длинным — и это правильный ответ
        # «разового здесь нет».
        worst, acc = [], 0.0
        for lap_num, e in exc:
            worst.append({"lap": lap_num, "plus": round(e, 2)})
            acc += e
            if acc >= bucket / 2:
                break
        shown = worst[:5]
        # Число рядом со списком номеров обязано быть суммой ИМЕННО этих
        # номеров. bucket — превышение по ВСЕМ кругам сектора, и печатать его
        # над тремя номерами значит послать человека искать семь секунд там,
        # где их четыре (проверено на Спа: карточка говорила +6.91s на четырёх
        # кругах, а те четыре стоили 3.98s).
        named = round(sum(x["plus"] for x in shown), 2)
        out.append({"i": i + 1,
                    "best": round(best, 2), "median": round(med, 2),
                    "scatter": round(sigma, 3),
                    "every_lap": round(every, 3), "se": round(se, 3),
                    "every_lap_total": round(every * len(base), 2),
                    "one_off_total": round(bucket, 2),
                    "one_off_named": named,
                    "one_off_spread": len(exc),
                    "one_off_laps": shown, "one_off_count": len(worst)})

    stable, why = _stable_sector(out, len(base))
    missing = _unrecorded(base)
    # Теоретический круг: сумма лучших секторов. Такого круга не было, и
    # подписан он именно так — но это верхняя граница того, что уже
    # получалось по частям, и она честнее любой «цели» со стороны.
    #
    # ТОЛЬКО когда круг записан целиком. На старых кругах Монцы сумма трёх
    # записанных секторов даёт 64.6 при лучшем круге 95.97 — если такое
    # число попадёт на экран под словом «optimal», человек решит, что может
    # проехать на тридцать секунд быстрее.
    optimal = None if missing else round(sum(s["best"] for s in out), 2)
    real_best = min((l["lap_time"] for l in base
                     if isinstance(l.get("lap_time"), (int, float))), default=None)
    # Второй пояс на тот же случай: даже когда невязка не поймала пропажу,
    # оптимальный круг не может быть на проценты быстрее настоящего лучшего.
    if optimal is not None and real_best and optimal < real_best * _OPTIMAL_SANE:
        optimal = None
    return {"ok": True, "count": n, "laps": len(good), "clean_laps": len(base),
            "optimal": optimal, "best_lap": real_best,
            "sectors": out, "stable": stable, "why": why,
            "headline": _headline(out, stable, why, len(base)),
            # Пит-круги и вылеты, оставленные за скобками. Молча выбросить
            # три круга из сорока пяти нельзя: человек посчитает свои круги
            # сам и не поймёт, почему у нас их меньше.
            "skipped": len(good) - len(base),
            # Круги заезда, у которых длина набора не совпала с общей. Так
            # бывает ровно один раз на трассу — в заезде, начатом до правки
            # хранилища и продолженном после. Промолчать нельзя: человек
            # увидит «20 laps», проехав 26, и не поймёт, куда делись шесть.
            "dropped": len(laps) - len(good),
            "partial": any(not l.get("recorded_all", True) for l in base),
            "unrecorded": missing}


def _stable_sector(sectors, n_clean):
    """Какой сектор теряет ВСЕГДА — или почему этого пока не видно."""
    if n_clean < MIN_STABLE_LAPS:
        return None, (
            f"{n_clean} clean laps is too few to call a sector consistently "
            f"slow. On laps like these it takes about {MIN_STABLE_LAPS}: below "
            f"that the answer was wrong more than once in ten runs, so I am not "
            f"giving you one. The per-sector figures below are still real.")
    ranked = sorted(sectors, key=lambda s: -s["every_lap"])
    top = ranked[0]
    if len(ranked) < 2:
        return top["i"], ""
    second = ranked[1]
    noise = top["se"] + second["se"]
    gap = top["every_lap"] - second["every_lap"]
    if gap <= noise:
        return None, (
            f"S{top['i']} and S{second['i']} are {gap:.2f}s apart while the "
            f"lap-to-lap noise is {noise:.2f}s — I cannot tell them apart yet. "
            f"More clean laps will separate them.")
    return top["i"], ""


def _headline(sectors, stable, why, laps):
    if not stable:
        return why
    s = next(x for x in sectors if x["i"] == stable)
    return (f"S{stable} costs you {s['every_lap']:.2f}s on every single lap "
            f"({s['every_lap_total']:.1f}s over {laps} laps). That is setup or "
            f"technique — not a mistake you can drive around.")


def _unrecorded(base):
    """Сколько круга НЕ записано.

    До 31.08.2026 в базу шли только три сектора, а на Спа их четыре, на Road
    America — пять: от четверти до половины круга нет вообще. Промолчать
    нельзя — человек решит, что видит весь круг, и будет искать потерю там,
    где её просто не измеряли.
    """
    rest = [l["lap_time"] - sum(l["sectors"]) for l in base
            if isinstance(l.get("lap_time"), (int, float))]
    if not rest:
        return None
    miss = statistics.median(rest)
    lap = statistics.median([l["lap_time"] for l in base
                             if isinstance(l.get("lap_time"), (int, float))])
    if miss <= _ROUNDING or not lap:
        return None
    return {"seconds": round(miss, 2), "share": round(miss / lap, 3)}


def latest_run(laps):
    """Самый свежий заезд из выборки — то, что человек только что проехал."""
    runs = split_runs(dedupe(laps))
    return runs[-1] if runs else []
