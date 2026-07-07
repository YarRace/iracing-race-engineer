from ire.collector.live_state import (parse_temp, make_get, is_on_track,
                                       strategy_inputs, fuel_capacity, damage_status,
                                       session_identity, infer_car_class,
                                       tire_wear_by_corner, session_info)
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


def test_damage_status_detects_repair_time():
    intact = _FakeIR({"PitRepairLeft": 0.0, "PitOptRepairLeft": 0.0,
                      "FastRepairAvailable": 1, "FastRepairUsed": 0,
                      "PlayerCarMyIncidentCount": 0, "PlayerCarTeamIncidentCount": 0}, {})
    d = damage_status(intact)
    assert d["damaged"] is False and d["repair_sec"] == 0.0
    assert d["fast_repair_available"] == 1 and d["incidents"] == 0

    hit = _FakeIR({"PitRepairLeft": 12.5, "PitOptRepairLeft": 3.0,
                   "FastRepairAvailable": 0, "FastRepairUsed": 1,
                   "PlayerCarMyIncidentCount": 4, "PlayerCarTeamIncidentCount": 9}, {})
    d2 = damage_status(hit)
    assert d2["damaged"] is True and d2["repair_sec"] == 12.5 and d2["opt_repair_sec"] == 3.0
    assert d2["incidents"] == 4 and d2["team_incidents"] == 9


def test_session_identity_reads_track_car_session():
    weekend = {"TrackName": "watkinsglen 2021 fullcourse",
               "TrackDisplayName": "Watkins Glen", "TrackConfigName": "Boot",
               "EventType": "Test"}
    scalars = {
        "DriverInfo": {"DriverCarIdx": 0,
                       "Drivers": [{"CarScreenName": "Cadillac V-Series.R",
                                    "CarPath": "cadillacvseriesrgtp"}]},
        "SessionInfo": {"Sessions": [{"SessionType": "Race"}]},
        "SessionNum": 0,
    }
    idn = session_identity(_FakeIR(scalars, weekend))
    assert idn["track"] == "watkinsglen 2021 fullcourse"
    assert idn["track_display"] == "Watkins Glen"
    assert idn["config"] == "Boot"
    assert idn["car"] == "Cadillac V-Series.R"
    assert idn["car_path"] == "cadillacvseriesrgtp"
    assert idn["car_class"] == "GTP"            # выведен из пути (CarClassShortName пуст)
    assert idn["session_type"] == "Race"        # из SessionInfo — приоритетнее EventType


def test_tire_wear_by_corner_min_of_points():
    scalars = {}
    for t in channels.TIRE_WEAR.values():
        for ch in t:
            scalars[ch] = 1.0
    scalars[channels.TIRE_WEAR["LF"][1]] = 0.8      # средняя точка LF — худшая
    w = tire_wear_by_corner(_FakeIR(scalars, {}))
    assert w["LF"] == 0.8
    assert w["RR"] == 1.0


def test_session_info_reads_laps_and_time():
    weekend = {"TrackName": "wg", "TrackDisplayName": "Watkins Glen",
               "TrackConfigName": "Boot", "EventType": "Race"}
    scalars = {
        "DriverInfo": {"DriverCarIdx": 0, "Drivers": [{"CarScreenName": "Cad",
                       "CarPath": "cadillacvseriesrgtp"}]},
        "SessionInfo": {"Sessions": [{"SessionType": "Race", "SessionLaps": 25}]},
        "SessionNum": 0, "SessionLapsRemain": 12, "SessionTimeRemain": 1080.0,
        "SessionTimeOfDay": 50000.0,
    }
    info = session_info(_FakeIR(scalars, weekend))
    assert info["session_type"] == "Race" and info["track_display"] == "Watkins Glen"
    assert info["laps_remain"] == 12 and info["laps_total"] == 25
    assert info["time_remain"] == 1080.0 and info["time_of_day"] == 50000.0


def test_infer_car_class():
    assert infer_car_class("GTP", "x", "y") == "GTP"                 # из SDK, как есть
    assert infer_car_class(None, "cadillacvseriesrgtp", "Cadillac V-Series.R") == "GTP"
    assert infer_car_class(None, "bmwm4gt3", "BMW M4 GT3") == "GT3"
    assert infer_car_class(None, "mercedesamggt4", "Mercedes AMG GT4") == "GT4"
    assert infer_car_class(None, "oreca07lmp2", "Oreca 07 LMP2") == "LMP"
    assert infer_car_class(None, "formularenault35", "Formula Renault") == "Formula"
    assert infer_car_class(None, "unknowncar", "Mystery") is None
