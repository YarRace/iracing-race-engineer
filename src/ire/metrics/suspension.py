def suspension_metrics(frames, min_defl=0.002):
    out = {}
    for c in ("LF", "RF", "LR", "RR"):
        vals = [f["shock_defl"][c] for f in frames]
        bottom = sum(v <= min_defl for v in vals)
        out[c] = {"min": round(min(vals), 4), "max": round(max(vals), 4),
                  "range": round(max(vals) - min(vals), 4),
                  "bottoming_pct": round(100.0 * bottom / len(vals), 1)}
    return out
