from ire.collector.live_state import parse_temp, make_get, is_on_track, strategy_inputs, fuel_capacity
from config import channels


def test_parse_temp_handles_string_and_number():
    assert parse_temp("39.82 C") == 39.82
    assert parse_temp(25.0) == 25.0
    assert parse_temp(None) is None


class _FakeIR:
    """Имитация pyirsdk: WeekendInfo как dict, скаляры по ключу."""
    def __init__(self, scalars, weekend):
        self._s = scalars
        self._s["WeekendInfo"] = weekend
    def __getitem__(self, k):
        return self._s[k]


def test_make_get_reads_temps_from_weekendinfo():
    ir = _FakeIR(
        {"Speed": 60.0},
        {channels.WEEKEND_TRACK_TEMP: "39.82 C", channels.WEEKEND_AIR_TEMP: "25.57 C"},
    )
    get = make_get(ir)
    assert get("Speed") == 60.0
    assert get(channels.WEEKEND_TRACK_TEMP) == 39.82
    assert get(channels.WEEKEND_AIR_TEMP) == 25.57


def test_is_on_track_excludes_pitlane():
    on = _FakeIR({"IsOnTrack": True, "OnPitRoad": False}, {})
    pit = _FakeIR({"IsOnTrack": True, "OnPitRoad": True}, {})
    garage = _FakeIR({"IsOnTrack": False, "OnPitRoad": False}, {})
    assert is_on_track(on) is True
    assert is_on_track(pit) is False
    assert is_on_track(garage) is False


def test_strategy_inputs_reads_fuel_and_wear():
    scalars = {"Lap": 5, "SessionTime": 450.0, "FuelLevel": 40.0,
               "SessionLapsRemain": 12, "SessionTimeRemain": 1080.0}
    for t in channels.TIRE_WEAR.values():
        for ch in t:
            scalars[ch] = 0.8
    ir = _FakeIR(scalars, {})
    si = strategy_inputs(ir)
    assert si["lap"] == 5 and si["fuel"] == 40.0 and si["laps_remain"] == 12
    assert si["tire_wear"]["LF"]["wm"] == 0.8


def test_fuel_capacity_from_driverinfo():
    ir = _FakeIR({"DriverInfo": {"DriverCarFuelMaxLtr": 89.0}}, {})
    assert fuel_capacity(ir) == 89.0
    assert fuel_capacity(_FakeIR({"DriverInfo": {}}, {})) == 89.0
