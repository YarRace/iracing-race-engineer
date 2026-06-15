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
