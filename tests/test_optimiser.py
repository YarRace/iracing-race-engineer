"""Setup Optimiser: по ощущениям человека — что покрутить в гараже.

Главное, что здесь проверяется, — НАПРАВЛЕНИЯ. В этом проекте уже находили
перевёрнутый совет по развалу, и он хуже отсутствия инструмента: человек
уезжает в гараж и делает противоположное. Поэтому каждое направление
закреплено отдельным тестом с объяснением, почему оно такое.

Второе по важности — что ответ вообще выдаётся. Первая версия падала с
KeyError на двух фазах из трёх, и карточка отдавала бы 500 ровно на самых
частых вопросах: «в середине поворота» и «на выходе».
"""
import itertools
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire.setup.optimiser import (PHASES, QUESTIONS, SKIPPED, SYMPTOMS,  # noqa: E402
                                 advise)
from ire.setup.sto_reader import read_sto                               # noqa: E402


@pytest.fixture(scope="module")
def setup_fields():
    return read_sto(str(ROOT / "tests" / "fixtures" / "sample_setup.json"))["fields"]


def move(res, lever_part):
    return next((m for m in res["moves"] if lever_part in m["lever"]), None)


# ── направления ─────────────────────────────────────────────────────────────

def test_understeer_softens_the_front_bar_not_the_rear(setup_fields):
    """Жёсткий стабилизатор гонит через свою ось больше переноса веса, а шина
    в нагрузке отдаёт меньше, чем теряет в разгрузке. Значит смягчать надо ту
    ось, которой не хватает, — при сносе это перед."""
    m = move(advise("mid", "understeer", fields=setup_fields), "anti-roll")
    assert m and "Front" in m["lever"] and m["move"] == "softer"


def test_oversteer_softens_the_rear_bar(setup_fields):
    m = move(advise("mid", "oversteer", fields=setup_fields), "anti-roll")
    assert m and "Rear" in m["lever"] and m["move"] == "softer"


def test_understeer_moves_brake_bias_rearward_and_says_it_is_a_smaller_number(
        setup_fields):
    """Физика однозначна: перед не может тормозить и поворачивать сразу. Но в
    гараже крутят ЧИСЛО, а это доля СПЕРЕДИ — «назад» значит уменьшить. Без
    этой оговорки половина пользы теряется на переводе."""
    m = move(advise("entry", "understeer", brake="braking", fields=setup_fields),
             "Brake bias")
    assert m and "rear" in m["move"] and "smaller" in m["move"]
    assert "FRONT" in m["caution"]


def test_oversteer_moves_brake_bias_forward(setup_fields):
    m = move(advise("entry", "oversteer", brake="braking", fields=setup_fields),
             "Brake bias")
    assert m and "front" in m["move"] and "larger" in m["move"]


def test_understeer_takes_rear_wing_off(setup_fields):
    """Крыло грузит заднюю ось, значит меньше угла — баланс прижима вперёд."""
    m = move(advise("exit", "understeer", speed="fast", fields=setup_fields), "wing")
    assert m and m["move"] == "less angle"


def test_the_wing_advice_admits_it_takes_grip_away_rather_than_adding_it(
        setup_fields):
    """Это лечение сноса ОТНИМАНИЕМ сцепления сзади. В быстром повороте
    машина станет быстрее по кругу и страшнее — об этом надо сказать."""
    m = move(advise("exit", "understeer", speed="fast", fields=setup_fields), "wing")
    assert "takes grip away from the rear" in m["caution"]


def test_understeer_lowers_the_front_pressure(setup_fields):
    m = move(advise("mid", "understeer", fields=setup_fields), "pressure")
    assert m and "lower" in m["move"] and "Front" in m["lever"]


def test_front_toe_advice_warns_that_the_field_counts_toe_in(setup_fields):
    """Поле называется ToeIn и на этой машине равно −1.3 мм. «Больше toe-out»
    значит сделать число ещё отрицательнее — без оговорки человек прибавит."""
    m = move(advise("entry", "understeer", fields=setup_fields), "toe")
    assert m and m["move"] == "more toe-out"
    assert "negative" in m["caution"]


def test_oversteer_adds_rear_toe_in(setup_fields):
    m = move(advise("mid", "oversteer", fields=setup_fields), "toe")
    assert m and m["move"] == "more toe-in" and "Rear" in m["lever"]


# ── чего мы НЕ советуем ─────────────────────────────────────────────────────

def test_camber_is_never_advised_from_a_feeling(setup_fields):
    """Сторона развала зависит от того, по какую сторону оптимума мы сейчас,
    а это измеряется. Именно здесь уже был перевёрнутый совет."""
    for ph, sy in itertools.product(PHASES, SYMPTOMS):
        r = advise(ph, sy, fields=setup_fields)
        assert not any("amber" in m["lever"] for m in r["moves"]), (ph, sy)
    assert any(s["lever"] == "Camber" for s in SKIPPED)


def test_preload_is_advised_on_entry_but_not_on_the_way_out(setup_fields):
    """На входе и накате блокировка от преднатяга — единственная, и знак
    однозначен. Под тягой её задают углы рамп, а преднатяг лишь добавка, и
    помогает он в разную сторону в зависимости от того, буксует ли внутреннее
    колесо. Ровно та неопределённость, из-за которой рампы не советуются."""
    assert move(advise("entry", "understeer", brake="coasting",
                       fields=setup_fields), "preload")
    assert move(advise("exit", "understeer", fields=setup_fields), "preload") is None

    out = advise("exit", "understeer", fields=setup_fields)["skipped"]
    row = next(s for s in out if "preload" in s["lever"].lower())
    assert row["kind"] == "uncertain" and "ramp" in row["why"]


def test_every_skipped_lever_says_why(setup_fields):
    """Молчание про рычаг читается как «мы про него не знаем». Причина — это
    и есть польза списка."""
    for s in advise("mid", "understeer", fields=setup_fields)["skipped"]:
        assert s["why"] and s["kind"] in ("uncertain", "last_resort", "not_now")


def test_the_wing_is_not_offered_in_slow_corners(setup_fields):
    r = advise("exit", "understeer", speed="slow", fields=setup_fields)
    assert move(r, "wing") is None
    assert any(s["lever"] == "Rear wing" and s["kind"] == "not_now"
               for s in r["skipped"])


def test_brake_bias_is_not_offered_once_you_are_off_the_brakes(setup_fields):
    r = advise("entry", "understeer", brake="coasting", fields=setup_fields)
    assert move(r, "Brake bias") is None


# ── устойчивость ────────────────────────────────────────────────────────────

def test_no_combination_of_answers_falls_over(setup_fields):
    """Первая версия падала на phase=mid и phase=exit: тормозной баланс не
    имел ранга в этих фазах, и обращение к ключу роняло запрос. Карточка
    отдавала бы 500 на самых частых вопросах."""
    n = 0
    for ph, sy, br, sp in itertools.product(
            PHASES, SYMPTOMS, ("any", "braking", "coasting"),
            ("any", "slow", "fast")):
        for f in (None, setup_fields):
            r = advise(ph, sy, br, sp, fields=f)
            assert r["ok"] and r["moves"], (ph, sy, br, sp)
            n += 1
    assert n == 108


def test_rubbish_from_the_address_bar_does_not_crash_it(setup_fields):
    """Параметры приходят из адресной строки, и туда можно вписать что угодно."""
    r = advise("mid", "understeer", brake="xyz", speed="сойка", fields=setup_fields)
    assert r["ok"] and r["brake"] == "any" and r["speed"] == "any"


def test_an_unanswered_questionnaire_asks_rather_than_guesses():
    r = advise("", "", fields={})
    assert r["ok"] is False and "answer the two questions" in r["reason"]


def test_it_works_with_no_setup_at_all():
    """Смысл инструмента в том, что он нужен, когда телеметрии и сима нет:
    первый заезд, чужая машина, запись не велась."""
    r = advise("mid", "understeer")
    assert r["ok"] and r["moves"]
    assert r["have_setup"] is False
    assert all(m["now"] is None for m in r["moves"])


def test_a_lever_the_car_does_not_have_is_named_rather_than_dropped():
    """Молча пропасть — значит оставить человека гадать, почему совета нет."""
    r = advise("mid", "understeer", fields={"Chassis.Front.ArbSize": "Medium"})
    assert r["unavailable"], "ни одного пропущенного рычага не названо"
    assert all(u["why"] for u in r["unavailable"])


# ── упоры ───────────────────────────────────────────────────────────────────

def test_a_lever_already_at_its_limit_says_so(setup_fields):
    """У этой машины передний стабилизатор уже «Soft». Совет «softer» без
    оговорки отправит человека в гараж ни за чем."""
    m = move(advise("mid", "understeer", fields=setup_fields), "anti-roll")
    assert m["at_limit"] is True
    assert "nowhere left to go" in m["caution"]
    assert m["alt"] == "stiffer rear bar"


def test_a_numeric_lever_is_not_declared_stuck(setup_fields):
    """Число можно двигать, и упор виден только в гараже — объявлять его
    заранее значит выдумывать."""
    m = move(advise("mid", "understeer", fields=setup_fields), "pressure")
    assert not m.get("at_limit")


# ── перекрёстная проверка с Tyre Tool ───────────────────────────────────────

def test_the_pressure_advice_always_names_its_boundary(setup_fields):
    """«Ниже = больше сцепления» верно только в рабочем окне: за ним правило
    переворачивается. Сказать это надо всегда."""
    m = move(advise("mid", "understeer", fields=setup_fields), "pressure")
    assert "working window" in m["caution"]


def test_it_refuses_to_deflate_a_tyre_the_tyre_tool_calls_under_inflated(
        setup_fields):
    """Единственное место, где у нас есть измерение, а не ощущение, — Tyre
    Tool. Если он видит холодную середину протектора, «спусти ещё» сделает
    хуже."""
    tyres = {"corners": {"LF": {"crown": "low"}, "RF": {"crown": "low"},
                         "LR": {"crown": "even"}, "RR": {"crown": "even"}}}
    m = move(advise("mid", "understeer", fields=setup_fields, tyres=tyres),
             "pressure")
    assert "under-inflated" in m["caution"] and "worse" in m["caution"]


# ── анкета ──────────────────────────────────────────────────────────────────

def test_every_question_has_answers_and_the_two_needed_ones_are_marked():
    ids = {q["id"] for q in QUESTIONS}
    assert {"phase", "symptom"} <= ids
    for q in QUESTIONS:
        assert len(q["options"]) >= 2
        assert all(len(o) == 2 and o[0] and o[1] for o in q["options"])
    assert {q["id"] for q in QUESTIONS if q["required"]} == {"phase", "symptom"}


def test_every_answer_actually_changes_something(setup_fields):
    """Вопрос, ответ на который ничего не меняет, хуже отсутствия вопроса:
    человек отвечает и напрасно ждёт другого совета. Первая версия спрашивала
    про газ, и обе кнопки давали побайтово один список."""
    base = advise("entry", "understeer", brake="any", speed="any",
                  fields=setup_fields)
    for q in QUESTIONS:
        if q["required"]:
            continue
        changed = False
        for value, _ in q["options"]:
            r = advise("entry", "understeer", fields=setup_fields,
                       **{q["id"]: value})
            if r["moves"] != base["moves"] or r["skipped"] != base["skipped"]:
                changed = True
        assert changed, f"ответ на «{q['id']}» ни на что не влияет"


def test_without_a_setup_it_does_not_guess_the_kind_of_spring():
    """На машине из фикстуры спереди торсионы, сзади пружины. Не зная сетапа,
    назвать одно из двух — значит угадывать там, где можно сказать оба."""
    m = move(advise("mid", "oversteer"), "spring")
    assert m and m["lever"] == "Rear spring or torsion bar"


def test_with_a_setup_it_names_the_one_the_car_actually_has(setup_fields):
    m = move(advise("mid", "oversteer", fields=setup_fields), "spring")
    assert m["lever"] == "Rear spring" and "SpringRate" in m["field"]


def test_the_spring_explanation_matches_what_the_car_actually_has():
    """Сказать «не знаю, пружина или торсион» и тут же объяснить про торсион —
    значит противоречить себе в двух соседних строках."""
    m = move(advise("mid", "oversteer"), "spring")
    assert "torsion bar's stiffness" not in m["why"]
    assert m.get("caution") is None, "предупредили про клиренс наугад"


def test_a_torsion_bar_gets_its_own_explanation(setup_fields):
    """У этой машины спереди торсионы — про них и надо говорить."""
    m = move(advise("mid", "understeer", fields=setup_fields), "torsion")
    assert "fourth power" in m["why"]
    assert "ride height" in m["caution"]
