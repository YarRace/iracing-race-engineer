"""Порог развала, измеренный на своей машине, а не выдуманный один на всех.

Общее число `CAMBER_MUCH = 6.0` срабатывало на 2% колёс Ferrari 499P, 39%
колёс Super Formula Lights и 0% колёс Porsche 963 GTP — то есть описывало
машину, а не физику. Здесь проверяется, что порог теперь берётся с его
собственных заездов, что он РАЗНЫЙ для передней и задней оси, и что при
нехватке данных программа честно возвращается к общему числу вместо того,
чтобы посчитать порог по трём колёсам.
"""
import json

import pytest

from ire.metrics import tyre_baseline as tb
from ire.metrics.tire import CAMBER_MUCH
from ire.metrics.tyres import report

# Настоящие числа с 25 записей Porsche 963 GTP (Ле-Ман).
PORSCHE_F, PORSCHE_R = 3.48, 4.55


def _samples(front, rear, car="porsche963gtp"):
    return {(car, "F"): front, (car, "R"): rear}


def _spread(mid, n):
    """n значений вокруг mid — чтобы p90 попал примерно в mid + 1."""
    return [mid - 1 + i * 2 / (n - 1) for i in range(n)]


def test_a_car_with_enough_laps_gets_its_own_threshold():
    b = tb.build(_samples(_spread(2.5, 40), _spread(3.6, 40)))
    f = tb.ref_for(b, "porsche963gtp", "LF")
    r = tb.ref_for(b, "porsche963gtp", "LR")
    assert f["basis"] == "car" and r["basis"] == "car"
    assert f["much"] != r["much"], "перед и зад обязаны отличаться"
    assert f["n"] == 40


def test_too_few_wheels_falls_back_and_says_so():
    """Двенадцать колёс дают порог с ошибкой в полтора градуса — измерено."""
    b = tb.build(_samples(_spread(2.5, tb.MIN_WHEELS - 1), _spread(3.6, 10)))
    ref = tb.ref_for(b, "porsche963gtp", "LF")
    assert ref["basis"] == "default"
    assert ref["much"] == CAMBER_MUCH


def test_a_car_with_no_readable_spread_is_not_given_a_threshold():
    """Порог ниже шума назвал бы «слишком большим развалом» дрожание датчика."""
    b = tb.build(_samples([0.2] * 40, [0.1] * 40))
    assert b["cars"] == {}
    assert tb.ref_for(b, "porsche963gtp", "LF")["basis"] == "default"


@pytest.mark.parametrize("name", [
    "porsche963gtp",           # как приходит из телеметрии (CarPath)
    "Porsche 963 GTP",         # как лежит в истории
    "PORSCHE  963-GTP",        # и любое между
])
def test_the_same_car_is_found_under_any_spelling(name):
    """Источников два, и промах здесь молча вернул бы общий порог."""
    b = tb.build(_samples(_spread(2.5, 40), _spread(3.6, 40)))
    assert tb.ref_for(b, name, "LR")["basis"] == "car"


def test_an_unknown_car_gets_the_shared_number():
    b = tb.build(_samples(_spread(2.5, 40), _spread(3.6, 40)))
    assert tb.ref_for(b, "Ferrari 499P", "LF")["basis"] == "default"


def test_the_axle_is_read_from_the_corner():
    assert tb.axle("LF") == tb.axle("RF") == "F"
    assert tb.axle("LR") == tb.axle("RR") == "R"


def test_the_verdict_actually_changes_with_the_measured_threshold():
    """Главное. Колесо, которое общий порог пропускал, свой ловит.

    Задняя кромка на 5.0 °C: при общем пороге 6.0 это «камбер работает»,
    при измеренном на Porsche 4.55 — «перебор». Разница видна человеку.
    """
    temps = {c: {"inner": 85.0, "outer": 80.0, "tm": 82.0}
             for c in ("LF", "RF", "LR", "RR")}
    temps["front_rear_balance"] = 0.0

    common = report(temps)
    assert common["corners"]["LR"]["camber"] == "working"
    assert common["corners"]["LR"]["camber_basis"] == "default"

    b = {"cars": {"porsche963gtp": {"name": "Porsche 963 GTP",
                                    "F": {"much": PORSCHE_F, "n": 38},
                                    "R": {"much": PORSCHE_R, "n": 38}}}}
    own = report(temps, car="porsche963gtp", baseline=b)
    assert own["corners"]["LR"]["camber"] == "too_much"
    assert own["corners"]["LR"]["camber_much"] == PORSCHE_R
    assert own["corners"]["LR"]["camber_basis"] == "car"
    assert any(t["corner"] == "LR" and t["what"] == "camber"
               for t in own["todo"]), "совет обязан появиться в списке дел"


def test_the_front_uses_the_front_threshold():
    """Перед и зад различаются на 2 °C — один порог сравнивал бы зад с передом."""
    temps = {c: {"inner": 84.0, "outer": 80.0, "tm": 82.0}
             for c in ("LF", "RF", "LR", "RR")}
    temps["front_rear_balance"] = 0.0
    b = {"cars": {"porsche963gtp": {"name": "Porsche 963 GTP",
                                    "F": {"much": PORSCHE_F, "n": 38},
                                    "R": {"much": PORSCHE_R, "n": 38}}}}
    r = report(temps, car="porsche963gtp", baseline=b)
    assert r["corners"]["LF"]["camber"] == "too_much", "4.0 выше переднего 3.48"
    assert r["corners"]["LR"]["camber"] == "working", "4.0 ниже заднего 4.55"


def test_history_without_tyre_temps_is_skipped_not_guessed():
    """Стинты, записанные до появления колонки, температур не содержат."""
    stints = [{"car_path": "porsche963gtp", "tyre_temps": None},
              {"car_path": "porsche963gtp", "tyre_temps": {}},
              {"car_path": "porsche963gtp",
               "tyre_temps": {"LF": {"inner": 85, "outer": 80},
                              "LR": {"inner": 88, "outer": 82}}},
              {"car": "", "tyre_temps": {"LF": {"inner": 85, "outer": 80}}}]
    cam, crown = tb.from_stints(stints)
    assert cam == {("porsche963gtp", "F"): [5.0],
                   ("porsche963gtp", "R"): [6.0]}
    # Короны нет: середины в этих стинтах не записано, а считать её из двух
    # кромок значило бы выдумать третье число.
    assert crown == {}


def test_a_half_written_corner_is_not_counted_as_zero():
    stints = [{"car_path": "x", "tyre_temps": {"LF": {"inner": 85, "outer": None},
                                               "RF": {"inner": None, "outer": 80}}}]
    assert tb.from_stints(stints) == ({}, {})


def test_the_crown_is_collected_when_the_middle_was_recorded():
    stints = [{"car_path": "p", "tyre_temps": {
        "LF": {"inner": 86, "middle": 84, "outer": 80},
        "LR": {"inner": 90, "middle": 88, "outer": 84}}}]
    cam, crown = tb.from_stints(stints)
    assert cam == {("p", "F"): [6.0], ("p", "R"): [6.0]}
    # середина 84 против средней кромки 83 → +1.0
    assert crown == {("p", "F"): [1.0], ("p", "R"): [1.0]}


def test_it_survives_a_round_trip_through_the_file(tmp_path):
    b = tb.build(_samples(_spread(2.5, 40), _spread(3.6, 40)))
    tb.save(b, tmp_path)
    assert tb.load(tmp_path) == b


def test_a_missing_or_broken_file_means_the_shared_number(tmp_path):
    assert tb.load(tmp_path) is None
    (tmp_path / tb.FILE).write_text("{сломано", encoding="utf-8")
    assert tb.load(tmp_path) is None
    (tmp_path / tb.FILE).write_text(json.dumps({"cars": {}}), encoding="utf-8")
    assert tb.load(tmp_path) is None


# --- КОРОНА: та же болезнь, то же лечение ---------------------------------
#
# Общая полоса ±2.5 °C срабатывает на 0% колёс Porsche 963 GTP и спереди, и
# сзади — то есть не говорит ничего и никогда. И ось здесь тоже разная:
# перед медиана −0.31, зад +0.80.

PORSCHE_CROWN_F = (-1.76, 0.59)     # p10 … p90 по его 36 колёсам
PORSCHE_CROWN_R = (0.0, 1.49)


def _crown_baseline():
    return {"cars": {"p": {"name": "P",
                           "F": {"crown": {"low": PORSCHE_CROWN_F[0],
                                           "high": PORSCHE_CROWN_F[1], "n": 36}},
                           "R": {"crown": {"low": PORSCHE_CROWN_R[0],
                                           "high": PORSCHE_CROWN_R[1], "n": 36}}}}}


def test_the_crown_band_comes_from_the_car_when_there_is_enough():
    b = tb.build({}, {("p", "F"): _spread(0.0, 40), ("p", "R"): _spread(1.0, 40)})
    f = tb.crown_ref(b, "p", "LF")
    r = tb.crown_ref(b, "p", "LR")
    assert f["basis"] == "car" and r["basis"] == "car"
    assert f["high"] != r["high"], "перед и зад обязаны отличаться"


def test_too_few_wheels_keeps_the_shared_crown_band():
    from ire.metrics.tyres import CROWN_BAND

    b = tb.build({}, {("p", "F"): _spread(0.0, tb.MIN_WHEELS - 1)})
    ref = tb.crown_ref(b, "p", "LF")
    assert ref["basis"] == "default"
    assert (ref["high"], ref["low"]) == (CROWN_BAND, -CROWN_BAND)


def test_the_crown_band_never_crosses_zero():
    """Ноль здесь физика, а не произвольная точка.

    Середина горячее кромок — перекачано, кромки горячее середины —
    недокачано. У задней оси Porsche десятый процентиль равен +0.02: полоса
    по нему называла бы «недокачано» колесо с ровной короной.
    """
    b = tb.build({}, {("p", "R"): _spread(2.0, 40)})     # всё положительное
    ref = tb.crown_ref(b, "p", "LR")
    assert ref["low"] <= 0.0, f"нижняя граница ушла за ноль: {ref['low']}"
    b2 = tb.build({}, {("p", "F"): _spread(-2.0, 40)})   # всё отрицательное
    assert tb.crown_ref(b2, "p", "LF")["high"] >= 0.0


def test_the_verdict_changes_with_the_measured_band():
    """Колесо, которое общая полоса пропускала, своя ловит."""
    temps = {c: {"inner": 85.0, "outer": 80.0, "tm": 83.5}
             for c in ("LF", "RF", "LR", "RR")}
    temps["front_rear_balance"] = 0.0

    # корона = 83.5 - 82.5 = +1.0: внутри общей полосы 2.5
    assert report(temps)["corners"]["LF"]["crown"] == "even"

    own = report(temps, car="p", baseline=_crown_baseline())
    assert own["corners"]["LF"]["crown"] == "high", "выше его переднего 0.59"
    assert own["corners"]["LR"]["crown"] == "even", "ниже его заднего 1.49"
    assert own["corners"]["LF"]["crown_basis"] == "car"


def test_the_card_is_told_which_band_it_is():
    temps = {c: {"inner": 85.0, "outer": 80.0, "tm": 83.5}
             for c in ("LF", "RF", "LR", "RR")}
    temps["front_rear_balance"] = 0.0
    plain = report(temps)["corners"]["LF"]
    assert plain["crown_basis"] == "default"
    assert plain["crown_high"] > 0 > plain["crown_low"]
