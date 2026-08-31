"""Командный план стинтов на эндуранс.

Здесь всё — арифметика, и она обязана сходиться: план, в котором сумма
кругов не равна дистанции гонки, а времена стинтов не стыкуются с пит-стопами,
хуже отсутствующего. По нему ставят будильник на три часа ночи.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire.metrics import stint_plan as sp                          # noqa: E402

# Ferrari 499P на Спа: круг 2:15, расход 3.4 л, бак 68 л → 20 кругов на стинт
LAP = 135.0
BURN = 3.4
TANK = 68.0
HOUR = 3600.0


def make(hours=24, drivers=("Yaroslav", "Semion"), **kw):
    return sp.plan(hours * HOUR, list(drivers), LAP, BURN, TANK, **kw)


# ── длина стинта ────────────────────────────────────────────────────────────

def test_stint_length_comes_from_the_tank():
    assert sp.stint_laps(TANK, BURN) == 20            # 68 / 3.4
    assert sp.stint_laps(50.0, 3.4) == 14             # дробный круг не считается


def test_a_series_rule_can_shorten_the_stint():
    """В некоторых сериях стинт ограничен по времени, а не по топливу."""
    assert sp.stint_laps(TANK, BURN, max_minutes=20, lap_time=LAP) == 8
    # правило мягче бака — побеждает бак
    assert sp.stint_laps(TANK, BURN, max_minutes=120, lap_time=LAP) == 20


def test_no_fuel_data_means_no_plan():
    assert sp.stint_laps(0, BURN) == 0
    assert sp.stint_laps(TANK, 0) == 0
    assert not make(hours=6, drivers=()).get("ok")


# ── сам план ────────────────────────────────────────────────────────────────

def test_the_plan_covers_the_race_and_no_more():
    """Лишний круг в плане — это лишняя заправка под финиш, тридцать секунд
    в мусор. Недостача — сход с трассы за круг до клетчатого."""
    r = make(hours=24)
    total = int(24 * HOUR // LAP)
    assert sum(s["laps"] for s in r["stints"]) == total
    assert r["summary"]["laps"] == total


def test_the_last_stint_is_trimmed_not_rounded_up():
    r = sp.plan(25 * LAP, ["A"], LAP, BURN, TANK)      # 25 кругов, стинт 20
    assert [s["laps"] for s in r["stints"]] == [20, 5]
    assert r["stints"][-1]["pit_after"] is None        # после финиша не заезжают


def test_times_line_up_with_the_pit_stops():
    """Стык стинтов — самое лёгкое место ошибиться на длину пит-стопа."""
    r = make(hours=6, pit_seconds=70.0)
    for a, b in zip(r["stints"], r["stints"][1:]):
        assert abs(b["start"] - (a["end"] + 70.0)) < 1e-6
    assert all(s["seconds"] == s["laps"] * LAP for s in r["stints"])


def test_drivers_take_turns():
    r = make(hours=6, drivers=("A", "B", "C"))
    assert [s["driver"] for s in r["stints"][:4]] == ["A", "B", "C", "A"]


def test_fuel_per_stint_is_what_will_actually_be_burned():
    r = make(hours=3)
    for s in r["stints"]:
        assert abs(s["fuel"] - s["laps"] * BURN) < 0.05
        assert s["fuel"] <= TANK + 0.05, "в бак столько не влезет"


def test_a_race_shorter_than_a_lap_is_refused():
    assert not sp.plan(60.0, ["A"], LAP, BURN, TANK)["ok"]


def test_a_broken_lap_time_is_refused_instead_of_producing_nonsense():
    """Ноль или мусор в темпе давал бы деление на ноль или план на миллион
    стинтов — лучше честный отказ."""
    for bad in (0, None, "быстро", 5.0):
        assert not sp.plan(HOUR, ["A"], bad, BURN, TANK)["ok"]


# ── сводка ──────────────────────────────────────────────────────────────────

def test_summary_counts_what_the_team_actually_asks():
    r = make(hours=24, drivers=("A", "B"))
    s = r["summary"]
    assert s["stints"] == len(r["stints"])
    assert s["pit_stops"] == len(r["stints"]) - 1     # после последнего не едут
    assert s["longest"]["seconds"] >= max(x["seconds"] for x in r["stints"]) - 1e-6
    assert {d["driver"] for d in s["drivers"]} == {"A", "B"}
    assert abs(sum(d["share"] for d in s["drivers"]) - 100.0) < 0.2


def test_equal_rotation_is_called_balanced():
    assert make(hours=12, drivers=("A", "B"))["summary"]["balanced"]


def test_back_to_back_stints_are_counted():
    """Два стинта подряд одному пилоту — полтора часа за рулём без перерыва.
    Не запрещаем, но молчать об этом нельзя."""
    r = make(hours=6, drivers=("A",))
    assert r["summary"]["back_to_back"] == len(r["stints"]) - 1
    assert make(hours=6, drivers=("A", "B"))["summary"]["back_to_back"] == 0


# ── часы ────────────────────────────────────────────────────────────────────

def test_clock_times_are_added_for_each_driver_timezone():
    """«Стинт 14 через 9 часов 40 минут» будильником не ставится,
    а «03:41 по твоему времени» — ставится."""
    r = make(hours=6, drivers=("Yaroslav", "Semion"))
    with_clock = sp.with_clock(r["stints"], "2026-09-05T10:00:00",
                               {"Yaroslav": 7, "Semion": 0})
    first = with_clock[0]
    assert first["clock_start"].endswith("10:00")
    assert first["local_start"].endswith("17:00")     # +7 часов
    assert with_clock[1]["local_start"] == with_clock[1]["clock_start"]


def test_a_broken_start_time_leaves_the_plan_usable():
    """Время старта вводит человек — в него прилетит что угодно. План без
    часов хуже, чем с часами, но лучше, чем ошибка на весь экран."""
    r = make(hours=3)
    assert sp.with_clock(r["stints"], "завтра утром") == r["stints"]
    assert sp.with_clock(r["stints"], None) == r["stints"]


def test_clock_crosses_midnight_correctly():
    r = sp.plan(20 * HOUR, ["A"], LAP, BURN, TANK)
    got = sp.with_clock(r["stints"], "2026-09-05T22:00:00")
    assert got[0]["clock_start"].startswith("05 Sep")
    assert got[-1]["clock_end"].startswith("06 Sep"), "план не перешёл через полночь"


# ── из живых данных ─────────────────────────────────────────────────────────

def test_plan_is_built_from_how_you_actually_drive():
    """Расход берётся из гонки, а не из характеристик машины: он зависит
    от того, как сегодня едут."""
    r = sp.from_live({"avg_lap_time": LAP, "avg_burn": BURN, "tank": TANK},
                     {"time_remain": 4 * HOUR}, ["A", "B"],
                     start="2026-09-05T10:00:00", offsets={"A": 3})
    assert r["ok"]
    assert r["stints"][0]["local_start"].endswith("13:00")
    assert sum(s["laps"] for s in r["stints"]) == int(4 * HOUR // LAP)


def test_no_live_data_yet_is_a_clean_refusal():
    """До первых кругов расхода нет. Показать план из нулей — соврать."""
    assert not sp.from_live({}, {"time_remain": HOUR}, ["A"])["ok"]
    assert not sp.from_live({"avg_lap_time": LAP, "avg_burn": BURN,
                             "tank": TANK}, {}, ["A"])["ok"]
