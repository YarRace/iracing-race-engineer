from ire.metrics.balance import balance_metrics

def _f(speed, steer, yaw, phase_throttle, brake=0.0):
    return {"speed": speed, "steer": steer, "yaw_rate": yaw,
            "throttle": phase_throttle, "brake": brake, "lat_accel": 8.0}

def test_low_yaw_for_steering_is_understeer():
    # большой угол руля, но машина почти не поворачивает → недостаток
    frames = [_f(50, 0.5, 0.05, 0.0, brake=0.5) for _ in range(50)]
    m = balance_metrics(frames)
    assert m["entry"]["tendency"] == "understeer"
