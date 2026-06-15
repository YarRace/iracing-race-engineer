from ire.metrics.suspension import suspension_metrics

def test_detects_bottoming_when_defl_near_max():
    frames = [{"shock_defl": {"LF": 0.001, "RF": 0.001, "LR": 0.001, "RR": 0.001}} for _ in range(10)]
    m = suspension_metrics(frames, min_defl=0.002)
    assert m["LF"]["bottoming_pct"] == 100.0
