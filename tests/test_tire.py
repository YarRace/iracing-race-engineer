from ire.metrics.tire import tire_metrics

def _frame(temps):
    return {"tires": {c: {"tl": t[0], "tm": t[1], "tr": t[2]} for c, t in temps.items()}}

def test_inner_hotter_means_too_much_camber():
    # LF: внутренняя кромка (tl) горячее внешней → избыток развала спереди
    frames = [_frame({"LF": (110, 95, 80), "RF": (80, 95, 110),
                      "LR": (90, 90, 90), "RR": (90, 90, 90)})]
    m = tire_metrics(frames)
    assert m["LF"]["spread"] == 30           # 110 - 80
    assert m["LF"]["bias"] == "inner_hot"
    assert m["front_rear_balance"] > 0       # перед горячее зада
