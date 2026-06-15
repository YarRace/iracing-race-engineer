from ire.metrics.consistency import consistency_metrics

def test_lap_time_variance_from_lap_changes():
    m = consistency_metrics([
        {"lap": 1, "t": 0.0}, {"lap": 2, "t": 90.0}, {"lap": 3, "t": 180.5}, {"lap": 4, "t": 272.5}
    ])
    assert m["lap_count"] == 3
    assert m["best_lap"] == 90.0
    assert m["spread"] == round(92.0 - 90.0, 2)
