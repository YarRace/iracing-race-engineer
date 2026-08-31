from ire.collector.irsdk_reader import normalize_frame

def test_normalize_maps_raw_to_contract():
    raw = {
        "SessionTime": 12.5, "Lap": 3, "LapDistPct": 0.42,
        "Speed": 60.0, "Throttle": 0.9, "Brake": 0.0,
        "SteeringWheelAngle": 0.1, "LatAccel": 8.0, "LongAccel": -2.0,
        "YawRate": 0.3, "Gear": 4, "FuelLevel": 50.0,
        "TrackSurfaceTemp": 40.0, "TrackAirTemp": 25.0,
    }
    tires = {"LF": (80, 85, 90), "RF": (80, 85, 90), "LR": (82, 86, 91), "RR": (82, 86, 91)}
    shocks = {"LF": 0.01, "RF": 0.012, "LR": 0.02, "RR": 0.021}
    for c, (l, m, r) in tires.items():
        from config.channels import TIRE_TEMP
        raw[TIRE_TEMP[c][0]] = l; raw[TIRE_TEMP[c][1]] = m; raw[TIRE_TEMP[c][2]] = r
    for c, v in shocks.items():
        from config.channels import SHOCK_DEFL
        raw[SHOCK_DEFL[c]] = v

    f = normalize_frame(lambda k: raw[k])
    assert f["speed"] == 60.0
    assert f["lap"] == 3
    assert f["tires"]["LR"]["tm"] == 86
    assert f["shock_defl"]["RR"] == 0.021
    assert f["track_temp"] == 40.0


def test_missing_coordinates_do_not_break_the_frame():
    """Координаты машины могут не публиковаться сессией. Кадр читается
    шестьдесят раз в секунду — падать из-за отсутствующего канала нельзя.
    """
    from config.channels import SHOCK_DEFL, TIRE_TEMP
    raw = {
        "SessionTime": 1.0, "Lap": 1, "LapDistPct": 0.1, "Speed": 50.0,
        "Throttle": 1.0, "Brake": 0.0, "SteeringWheelAngle": 0.0,
        "LatAccel": 0.0, "LongAccel": 0.0, "YawRate": 0.0, "Gear": 3,
        "FuelLevel": 40.0, "TrackSurfaceTemp": 30.0, "TrackAirTemp": 20.0,
    }
    for c, t in TIRE_TEMP.items():
        for name in t:
            raw[name] = 80.0
    for c, v in SHOCK_DEFL.items():
        raw[v] = 0.01

    f = normalize_frame(lambda k: raw[k])          # словарь бросит KeyError на Lat
    assert f["lat"] is None and f["lon"] is None
    assert f["speed"] == 50.0                      # остальное на месте


def test_coordinates_are_passed_through_when_present():
    from config.channels import SHOCK_DEFL, TIRE_TEMP
    raw = {
        "SessionTime": 1.0, "Lap": 1, "LapDistPct": 0.1, "Speed": 50.0,
        "Throttle": 1.0, "Brake": 0.0, "SteeringWheelAngle": 0.0,
        "LatAccel": 0.0, "LongAccel": 0.0, "YawRate": 0.0, "Gear": 3,
        "FuelLevel": 40.0, "TrackSurfaceTemp": 30.0, "TrackAirTemp": 20.0,
        "Lat": 34.15, "Lon": -83.81,
    }
    for c, t in TIRE_TEMP.items():
        for name in t:
            raw[name] = 80.0
    for c, v in SHOCK_DEFL.items():
        raw[v] = 0.01
    f = normalize_frame(lambda k: raw[k])
    assert f["lat"] == 34.15 and f["lon"] == -83.81
