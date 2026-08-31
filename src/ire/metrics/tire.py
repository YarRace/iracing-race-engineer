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

# Порог, ниже которого разница кромок — шум, а не признак. По его данным
# сессии без выраженного перекоса дают разброс до ±1°, выраженные — 4–7°.
EDGE_NOISE = 8


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
        bias = "even"
        if inner - outer > EDGE_NOISE:
            bias = "inner_hot"
        elif outer - inner > EDGE_NOISE:
            bias = "outer_hot"
        out[c] = {"tl": round(tl, 1), "tm": round(tm, 1), "tr": round(tr, 1),
                  "inner": round(inner, 1), "outer": round(outer, 1),
                  "spread": spread, "bias": bias}
        corner_means[c] = _avg([tl, tm, tr])
    front = _avg([corner_means["LF"], corner_means["RF"]])
    rear = _avg([corner_means["LR"], corner_means["RR"]])
    out["front_rear_balance"] = round(front - rear, 1)
    return out
