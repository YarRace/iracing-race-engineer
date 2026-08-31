"""Tyre Tool: чтение температур и давлений шин.

Числа в тестах — НАСТОЯЩИЕ, снятые из его же файлов .ibt, а не придуманные.
Так видно, что инструмент отвечает то же, что видно глазами в телеметрии.

  Road America, Super Formula Lights, реальные круги:
      LF  in 63.3  mid 60.8  out 61.2      RF  in 60.4  mid 56.7  out 53.6
      LR  in 63.0  mid 61.3  out 60.7      RR  in 62.0  mid 60.3  out 54.8

  Road Atlanta, Ferrari 499P, сессия без выезда (максимум 198 км/ч на
  одном отрезке, кромки сходятся в ноль).
"""
from ire.metrics.tyres import (MIN_MOVING, camber, crown, pressures, report,
                               target_from_history)

ROAD_AMERICA = {
    "LF": {"inner": 63.3, "tm": 60.8, "outer": 61.2},
    "RF": {"inner": 60.4, "tm": 56.7, "outer": 53.6},
    "LR": {"inner": 63.0, "tm": 61.3, "outer": 60.7},
    "RR": {"inner": 62.0, "tm": 60.3, "outer": 54.8},
    "front_rear_balance": -1.0,
}

DROVE = [{"speed": 60.0}] * (MIN_MOVING + 10)


# ── развал ──────────────────────────────────────────────────────────────────

def test_a_slightly_hotter_inner_edge_is_not_a_fault():
    """Отрицательный развал ДОЛЖЕН греть внутреннюю кромку. Объявлять это
    ошибкой — значит гонять человека по гаражу без причины: у половины его
    колёс разница как раз около градуса."""
    assert camber(63.3, 61.2)[0] == "working"
    assert camber(36.4, 35.7)[0] == "even"


def test_a_much_hotter_inner_edge_is_too_much_camber():
    assert camber(60.4, 53.6) == ("too_much", 6.8)


def test_a_hotter_outer_edge_means_not_enough_camber():
    """Тот самый вердикт, который раньше выходил наоборот."""
    assert camber(53.6, 60.4) == ("not_enough", -6.8)


def test_a_missing_temperature_says_unknown_rather_than_guessing():
    assert camber(None, 60.0) == ("unknown", None)


# ── давление по короне ──────────────────────────────────────────────────────

def test_a_hot_middle_means_the_tyre_is_over_inflated():
    assert crown(70.0, 60.0, 60.0)[0] == "high"


def test_a_cold_middle_means_it_is_under_inflated():
    assert crown(50.0, 60.0, 60.0)[0] == "low"


def test_his_real_corners_are_within_the_normal_band():
    """По его данным корона почти всегда около нуля — и инструмент обязан
    честно говорить «в норме», а не искать проблему там, где её нет."""
    for c in ("LF", "RF", "LR", "RR"):
        t = ROAD_AMERICA[c]
        assert crown(t["tm"], t["inner"], t["outer"])[0] == "even"


# ── давления из сетапа ──────────────────────────────────────────────────────

def test_pressures_are_found_whatever_section_the_car_puts_them_in():
    """Путь к полю у разных машин разный. Жёсткий путь молча давал бы пустоту
    на половине машин — а пустая карточка читается как поломка."""
    got = pressures({
        "TiresAero.LeftFront.StartingPressure": "152 kPa",
        "Chassis.RightRear.StartingPressure": "24.8 psi",
        "TiresAero.LeftFront.LastHotPressure": "165 kPa",
    })
    assert got["LF"] == {"cold": 152.0, "unit": "kPa",
                         "shown": "152 kPa", "hot": 165.0}
    assert got["RR"]["cold"] == 24.8 and got["RR"]["unit"] == "psi"
    assert "RF" not in got, "придумали давление там, где его не отдавали"


def test_a_car_without_pressures_gives_nothing_rather_than_zeros():
    assert pressures({"Chassis.Front.ArbSize": "3"}) == {}


# ── свод ────────────────────────────────────────────────────────────────────

def test_the_real_session_finds_the_two_corners_that_stand_out():
    """Так это и выглядит в его телеметрии: правые колёса греют внутреннюю
    кромку заметно сильнее левых."""
    r = report(ROAD_AMERICA, frames=DROVE)
    assert r["ok"]
    bad = {t["corner"] for t in r["todo"]}
    assert bad == {"RF", "RR"}
    assert all(t["what"] == "camber" for t in r["todo"])


def test_when_nothing_stands_out_it_says_so_out_loud():
    """Пустая карточка читается как поломка программы. «Менять нечего» —
    это ответ, и его надо произнести."""
    even = {c: {"inner": 60.0, "tm": 60.0, "outer": 60.0}
            for c in ("LF", "RF", "LR", "RR")}
    r = report(even, frames=DROVE)
    assert r["todo"] == []
    assert r["verdict"] == "nothing to change on the tyres"


def test_a_session_where_the_car_never_drove_gets_no_verdict():
    """Главная ловушка: в гараже шины тоже тёплые, но кромки сходятся в ноль,
    и «менять нечего» звучало бы как ложное успокоение."""
    r = report(ROAD_AMERICA, frames=[{"speed": 2.0}] * 5000)
    assert r["ok"] is False
    assert "barely moved" in r["reason"]


def test_without_frames_it_still_answers():
    """Кадров может не быть вовсе — например, разбор по сохранённому стинту.
    Отказ в этом случае был бы отказом на ровном месте."""
    assert report(ROAD_AMERICA)["ok"] is True


def test_the_numbers_are_always_next_to_the_verdict():
    """Полосы измерены по двум машинам. Если полоса ошибётся, число всё
    равно верное — и человек увидит, на чём вердикт построен."""
    r = report(ROAD_AMERICA, frames=DROVE)
    v = r["corners"]["RF"]
    assert v["camber_delta"] == 6.8 and v["inner"] == 60.4 and v["outer"] == 53.6


# ── цель из своей истории ───────────────────────────────────────────────────

def test_the_target_comes_from_the_fastest_stint_that_recorded_pressures():
    """Цель, которую не надо выдумывать: круг по ней уже проехан."""
    stints = [
        {"id": 1, "mean_lap": 92.4, "pressures": {"LF": 152}},
        {"id": 2, "mean_lap": 91.1, "pressures": {"LF": 148}},   # быстрее
        {"id": 3, "mean_lap": 90.0},                             # без давлений
    ]
    t = target_from_history(stints)
    assert t["from_stint"] == 2 and t["pressures"] == {"LF": 148}


def test_no_recorded_pressures_means_no_target_rather_than_a_made_up_one():
    """До сегодняшнего дня давления не сохранялись. Подставить сюда число
    неизвестного происхождения было бы хуже, чем не ответить."""
    assert target_from_history([{"id": 1, "mean_lap": 90.0}]) is None
    assert target_from_history([]) is None


def test_the_temperature_sits_next_to_the_verdict():
    """На выездном круге шины у него были 36°, кромки сошлись в ноль. Голое
    «менять нечего» прозвучало бы как «сетап хорош», а рядом с числом сразу
    видно, что резина была холодная и смотреть там не на что."""
    cold = {c: {"inner": 36.4, "tm": 36.4, "outer": 35.7}
            for c in ("LF", "RF", "LR", "RR")}
    r = report(cold, frames=DROVE)
    assert r["verdict"] == "nothing to change on the tyres"
    assert r["mean_temp"] == 36.4, "температуру не показали вовсе"
