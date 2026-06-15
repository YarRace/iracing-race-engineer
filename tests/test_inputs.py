from ire.metrics.inputs import input_metrics


def test_trail_braking_detected_when_brake_and_steer_overlap():
    frames = [{"brake": 0.4, "throttle": 0.0, "steer": 0.3} for _ in range(8)] + \
             [{"brake": 0.0, "throttle": 0.8, "steer": 0.1} for _ in range(2)]
    m = input_metrics(frames)
    assert m["trail_brake_pct"] == 80.0
    assert 0.0 <= m["throttle_smoothness"] <= 1.0
