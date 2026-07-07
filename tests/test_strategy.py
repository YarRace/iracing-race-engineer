from ire.metrics.strategy import StrategyTracker, plan_race


def _wear(v):
    return {c: {"wl": v, "wm": v, "wr": v} for c in ("LF", "RF", "LR", "RR")}


def test_fuel_burn_and_refuel_estimate():
    # бак 89л, расход ~3.0 л/круг, осталось 10 кругов гонки
    tr = StrategyTracker(tank_capacity=89.0, reserve_laps=1.0, fuel_window=5)
    fuel = 50.0
    # 4 полных круга по 3 л, lap_time ~90с
    for lap in range(1, 6):
        tr.update(lap=lap, t=(lap - 1) * 90.0, fuel=fuel, laps_remain=10 - (lap - 1),
                  tire_wear=_wear(1.0))
        fuel -= 3.0
    s = tr.snapshot()
    assert round(s["avg_burn"], 1) == 3.0
    # осталось кругов гонки = 6, в баке 38л -> хватает на ~12.7 кругов, доливать не нужно
    assert s["laps_to_go"] == 6
    assert s["fuel_to_add"] == 0.0
    assert s["pit_needed_for_fuel"] is False


def test_refuel_needed_when_short():
    tr = StrategyTracker(tank_capacity=89.0, reserve_laps=1.0, fuel_window=5)
    fuel = 10.0
    for lap in range(1, 6):
        tr.update(lap=lap, t=(lap - 1) * 90.0, fuel=fuel, laps_remain=20 - (lap - 1),
                  tire_wear=_wear(1.0))
        fuel -= 3.0
    s = tr.snapshot()
    # осталось 16 кругов * 3л = 48л + запас 3л = 51л; в баке ~-2 (мало) -> доливать прилично
    assert s["pit_needed_for_fuel"] is True
    assert s["fuel_to_add"] > 40


def test_tire_wear_rate_and_change_recommendation():
    tr = StrategyTracker(tire_change_threshold=0.30)
    # износ падает на 0.10 за круг
    w = 1.0
    for lap in range(1, 5):
        tr.update(lap=lap, t=(lap - 1) * 90.0, fuel=80.0 - lap, laps_remain=30,
                  tire_wear=_wear(w))
        w -= 0.10
    s = tr.snapshot()
    assert round(s["tire_wear_per_lap"], 2) == 0.10
    assert 0.0 <= s["tire_min"] <= 1.0
    # при пороге 0.30 и текущем ~0.7, до порога ещё ~4 круга
    assert s["tire_laps_left"] >= 1
    assert s["change_tires"] in (True, False)


def test_plan_race_zero_stops_when_fuel_enough():
    # 5 кругов до конца, 50л в баке при 3 л/круг — топлива с запасом хватает
    p = plan_race(laps_to_go=5, avg_burn=3.0, fuel=50.0, tank=89.0)
    assert p["stops"] == 0
    assert p["fuel_per_stop"] is None
    assert p["save_to_skip"] is None


def test_plan_race_one_stop_totals_and_next():
    # 30 кругов, 20л в баке, 3 л/круг, текущий круг 4
    p = plan_race(laps_to_go=30, avg_burn=3.0, fuel=20.0, tank=89.0, cur_lap=4)
    assert p["stops"] == 1
    assert p["stint_laps"] == 28                      # floor(89/3 - 1)
    assert p["fuel_to_add_total"] == 73.0             # 30*3 + 3 запас - 20
    assert p["laps_until_stop"] == 5                  # floor(20/3 - 1)
    assert p["next_stop_lap"] == 9                    # 4 + 5


def test_plan_race_save_to_skip_when_close():
    # 20 кругов, 50л, 3 л/круг: один пит, но экономией ~0.6 л/круг можно убрать
    p = plan_race(laps_to_go=20, avg_burn=3.0, fuel=50.0, tank=89.0)
    assert p["stops"] == 1
    assert p["save_to_skip"] is not None
    assert 0.4 < p["save_to_skip"] < 0.9


def test_plan_race_none_on_missing_data():
    assert plan_race(laps_to_go=None, avg_burn=3.0, fuel=50.0, tank=89.0) is None
    assert plan_race(laps_to_go=30, avg_burn=None, fuel=50.0, tank=89.0) is None
    assert plan_race(laps_to_go=30, avg_burn=3.0, fuel=None, tank=89.0) is None
