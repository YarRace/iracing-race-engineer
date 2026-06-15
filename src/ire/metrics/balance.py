import math

def _phase(f):
    if f["brake"] > 0.2: return "entry"
    if f["throttle"] > 0.2: return "exit"
    return "mid"

def _tendency(samples):
    # ожидаемый yaw ~ steer*speed*k (упрощённо, k подбирается калибровкой); сравниваем со средним фактическим
    if not samples: return "n/a"
    exp = sum(abs(s["steer"]) * s["speed"] for s in samples) / len(samples)
    act = sum(abs(s["yaw_rate"]) for s in samples) / len(samples)
    if exp == 0: return "neutral"
    ratio = act / (exp * 0.04)  # 0.04 — стартовый калибровочный коэффициент, уточняется на фикстуре
    if ratio < 0.85: return "understeer"
    if ratio > 1.15: return "oversteer"
    return "neutral"

def balance_metrics(frames):
    turning = [f for f in frames if abs(f["steer"]) > 0.1]
    out = {}
    for ph in ("entry", "mid", "exit"):
        s = [f for f in turning if _phase(f) == ph]
        out[ph] = {"tendency": _tendency(s), "samples": len(s)}
    return out
