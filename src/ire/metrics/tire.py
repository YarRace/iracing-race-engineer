"""Температуры шин по кромкам: что они говорят про развал и давление.

КАКАЯ КРОМКА ВНУТРЕННЯЯ. Каналы tl/tm/tr — это стороны шины в системе
координат МАШИНЫ, а не самой шины. Дословное описание из заголовка .ibt:
«LF tire left surface temperature». Значит:

    левые колёса  (LF, LR):  tl = ВНЕШНЯЯ кромка, tr = ВНУТРЕННЯЯ
    правые колёса (RF, RR):  tl = ВНУТРЕННЯЯ,     tr = ВНЕШНЯЯ

Здесь это раньше стояло наоборот, и совет по развалу выходил ровно обратным:
«убавь развал» там, где надо было прибавить. Проверено дважды и независимо —
описанием канала в SDK и его собственными 32 сессиями: отрицательный развал
стоит на любой гоночной машине и греет внутреннюю кромку, и во всех 14
сессиях, где разница выше шума, горячее оказалась сторона к центру машины.
Обратных случаев не нашлось ни одного.
"""

# Пороги разницы кромок живут ЗДЕСЬ и только здесь. Раньше их было два:
# EDGE_NOISE = 8 в этом файле и CAMBER_NOISE/CAMBER_MUCH в metrics/tyres.py.
# Числа разошлись, и 15 колёс из 96 получали «even» от одного модуля и
# «too much camber» от другого — причём оба видны человеку: первое уходит
# в разбор ИИ, второе стоит в карточке Tyre Tool.
CAMBER_NOISE = 2.0         # ниже — шум, а не признак
CAMBER_MUCH = 6.0          # выше — внутренняя кромка греется заметно сильнее


def camber(inner, outer):
    """Вердикт по разнице кромок. (вердикт, разница) — число всегда рядом.

    ОГОВОРКА, измеренная и важная: порог CAMBER_MUCH не универсален. На
    Ferrari 499P он срабатывает на 2% колёс, на Super Formula Lights — на
    39%. Это разница в двадцать раз, то есть число описывает не «слишком
    большой развал вообще», а привычку конкретной машины. Менять его пока
    не на что: телеметрии больше двух машин нет, а машина и трасса в этих
    записях не разделены (Ferrari только Road Atlanta, SF только Road
    America). Перемерить помогает tools/measure_tyres.py.
    """
    if inner is None or outer is None:
        return "unknown", None
    d = round(inner - outer, 1)
    if d < -CAMBER_NOISE:
        # Внешняя кромка горячее — развала не хватает. ВНИМАНИЕ: эта ветка
        # не подтверждена ни одним наблюдением: из 96 колёс она не
        # сработала ни разу, минимум по всем данным −0.85.
        return "not_enough", d
    if d > CAMBER_MUCH:
        return "too_much", d
    if d > CAMBER_NOISE:
        # Внутренняя кромка слегка горячее — так и должно быть при
        # отрицательном развале. Это НЕ ошибка, и говорить о ней как об
        # ошибке значит гонять человека по гаражу без причины.
        return "working", d
    return "even", d


def _avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return sum(xs) / len(xs) if xs else 0.0


def edges(corner, tl, tr):
    """(внутренняя, внешняя) для этого колеса — см. пояснение в шапке."""
    return (tr, tl) if corner[0] == "L" else (tl, tr)


def tire_metrics(frames):
    out = {}
    corner_means = {}
    for c in ("LF", "RF", "LR", "RR"):
        tl = _avg([f["tires"][c]["tl"] for f in frames])
        tm = _avg([f["tires"][c]["tm"] for f in frames])
        tr = _avg([f["tires"][c]["tr"] for f in frames])
        inner, outer = edges(c, tl, tr)
        spread = round(max(tl, tm, tr) - min(tl, tm, tr), 1)
        # bias выводится ИЗ ТОГО ЖЕ вердикта, что показывает Tyre Tool:
        # разъехаться им теперь нечем.
        verdict, _ = camber(inner, outer)
        bias = {"too_much": "inner_hot", "not_enough": "outer_hot"}.get(verdict, "even")
        out[c] = {"tl": round(tl, 1), "tm": round(tm, 1), "tr": round(tr, 1),
                  "inner": round(inner, 1), "outer": round(outer, 1),
                  "spread": spread, "bias": bias}
        corner_means[c] = _avg([tl, tm, tr])
    front = _avg([corner_means["LF"], corner_means["RF"]])
    rear = _avg([corner_means["LR"], corner_means["RR"]])
    out["front_rear_balance"] = round(front - rear, 1)
    return out
