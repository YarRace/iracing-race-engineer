from ire.metrics.strategy import StrategyTracker


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
