def _avg(xs): return sum(xs) / len(xs)

def tire_metrics(frames):
    out = {}
    corner_means = {}
    for c in ("LF", "RF", "LR", "RR"):
        tl = _avg([f["tires"][c]["tl"] for f in frames])
        tm = _avg([f["tires"][c]["tm"] for f in frames])
        tr = _avg([f["tires"][c]["tr"] for f in frames])
        spread = round(max(tl, tm, tr) - min(tl, tm, tr), 1)
        bias = "even"
        if tl - tr > 8: bias = "inner_hot" if c[0] == "L" else "outer_hot"
        elif tr - tl > 8: bias = "outer_hot" if c[0] == "L" else "inner_hot"
        out[c] = {"tl": round(tl, 1), "tm": round(tm, 1), "tr": round(tr, 1),
                  "spread": spread, "bias": bias}
        corner_means[c] = _avg([tl, tm, tr])
    front = _avg([corner_means["LF"], corner_means["RF"]])
    rear = _avg([corner_means["LR"], corner_means["RR"]])
    out["front_rear_balance"] = round(front - rear, 1)
    return out
