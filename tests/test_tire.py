"""Температуры кромок шин: какая сторона внутренняя и что это значит.

Раньше здесь было закреплено ПЕРЕПУТАННОЕ соответствие: тест утверждал, что
tl у левого колеса — внутренняя кромка, и совет по развалу выходил обратным.
Правда установлена дважды и независимо:

  1. описание канала в заголовке .ibt: «LF tire left surface temperature» —
     стороны заданы в системе координат МАШИНЫ;
  2. 32 сессии Ярослава: отрицательный развал стоит на любой гоночной машине
     и греет ВНУТРЕННЮЮ кромку. Во всех 14 сессиях, где разница выше шума,
     горячее оказалась сторона к центру машины. Обратных случаев ноль.
"""
from ire.metrics.tire import CAMBER_NOISE, camber, edges, tire_metrics


def _frame(temps):
    return {"tires": {c: {"tl": t[0], "tm": t[1], "tr": t[2]}
                      for c, t in temps.items()}}


def _even():
    return {c: (90, 90, 90) for c in ("LF", "RF", "LR", "RR")}


def test_which_edge_is_the_inner_one():
    """Левые колёса смотрят наружу левой стороной, правые — правой."""
    assert edges("LF", 100, 80) == (80, 100), "у левого колеса внутренняя — tr"
    assert edges("LR", 100, 80) == (80, 100)
    assert edges("RF", 100, 80) == (100, 80), "у правого колеса внутренняя — tl"
    assert edges("RR", 100, 80) == (100, 80)


def test_the_side_towards_the_car_being_hot_means_too_much_camber():
    """Именно так выглядят его настоящие сессии: внутренняя кромка горячее."""
    t = _even()
    t["LF"] = (80, 95, 110)      # у левого колеса tr — внутренняя
    t["RF"] = (110, 95, 80)      # у правого внутренняя — tl
    m = tire_metrics([_frame(t)])
    assert m["LF"]["bias"] == "inner_hot"
    assert m["RF"]["bias"] == "inner_hot"
    assert m["LF"]["inner"] == 110 and m["LF"]["outer"] == 80


def test_the_outer_side_being_hot_is_the_opposite_advice():
    """Тот самый случай, который раньше читался наоборот: не хватает развала,
    а программа советовала его убавить."""
    t = _even()
    t["LF"] = (110, 95, 80)
    t["RF"] = (80, 95, 110)
    m = tire_metrics([_frame(t)])
    assert m["LF"]["bias"] == "outer_hot"
    assert m["RF"]["bias"] == "outer_hot"


def test_a_small_difference_is_noise_not_a_verdict():
    """В его сессиях без перекоса кромки расходятся на градус. Объявлять это
    ошибкой развала — значит гонять человека по гаражу за шумом."""
    t = _even()
    t["LF"] = (90, 90, 90 + CAMBER_NOISE - 0.5)
    m = tire_metrics([_frame(t)])
    assert m["LF"]["bias"] == "even"


def test_the_front_rear_balance_still_says_which_end_works_harder():
    t = _even()
    t.update({"LF": (110, 110, 110), "RF": (110, 110, 110)})
    m = tire_metrics([_frame(t)])
    assert m["front_rear_balance"] == 20.0


def test_a_missing_channel_does_not_take_the_whole_lap_down():
    """Кадр читается шестьдесят раз в секунду; падать посреди гонки нельзя."""
    t = _even()
    m = tire_metrics([_frame(t), {"tires": {c: {"tl": None, "tm": None, "tr": None}
                                            for c in ("LF", "RF", "LR", "RR")}}])
    assert m["LF"]["spread"] == 0.0


def test_the_two_modules_can_no_longer_disagree_about_the_same_wheel():
    """Пороги были в двух местах: EDGE_NOISE = 8 здесь и CAMBER_MUCH = 6.0 в
    tyres.py. Числа разошлись, и 15 колёс из 96 получали «even» от одного
    модуля и «too much camber» от другого — причём человек видел оба: первое
    уходит в разбор ИИ, второе стоит в карточке Tyre Tool.
    """
    from ire.metrics import tyres

    assert tyres.camber is camber, "у Tyre Tool снова свой вердикт"
    t = _even()
    t["LF"] = (80, 95, 87)                      # внутренняя горячее на 7°
    m = tire_metrics([_frame(t)])
    assert m["LF"]["bias"] == "inner_hot"
    assert camber(m["LF"]["inner"], m["LF"]["outer"])[0] == "too_much"


def test_the_verdict_carries_the_number_that_produced_it():
    """Порог не универсален (2% колёс Ferrari против 39% Super Formula
    Lights). Если полоса ошибается, число обязано остаться верным."""
    assert camber(60.4, 53.6) == ("too_much", 6.8)


def test_a_missing_channel_is_not_reported_as_zero_degrees():
    """Раньше среднее по пустому списку давало ноль, и «канала нет»
    превращалось в «ноль градусов»: разница кромок выходила ровно 0.0,
    вердикт — уверенное «even», и на машине без поверхностных каналов Tyre
    Tool спокойно сообщал, что с развалом всё в порядке."""
    frames = [{"tires": {c: {"tl": None, "tm": None, "tr": None}
                         for c in ("LF", "RF", "LR", "RR")}}]
    m = tire_metrics(frames)
    assert m["LF"]["bias"] == "unknown", "отсутствие данных выдали за «ровно»"
    assert m["LF"]["spread"] is None
    assert m["front_rear_balance"] is None


def test_one_missing_corner_does_not_poison_the_others():
    """Канал может пропасть на одном колесе. Остальные три обязаны считаться."""
    t = _even()
    frames = [_frame(t)]
    frames[0]["tires"]["LF"] = {"tl": None, "tm": None, "tr": None}
    m = tire_metrics(frames)
    assert m["LF"]["bias"] == "unknown"
    assert m["RF"]["spread"] == 0.0, "исправное колесо потеряли вместе с пустым"
