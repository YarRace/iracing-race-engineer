def input_metrics(frames):
    n = len(frames)
    trail = sum(f["brake"] > 0.1 and abs(f["steer"]) > 0.15 for f in frames)
    # плавность газа: 1 - средний модуль приращения (0..1, выше = плавнее)
    deltas = [abs(frames[i]["throttle"] - frames[i-1]["throttle"]) for i in range(1, n)]
    smooth = 1.0 - (sum(deltas) / len(deltas) if deltas else 0.0)
    return {"trail_brake_pct": round(100.0 * trail / n, 1),
            "throttle_smoothness": round(max(0.0, min(1.0, smooth)), 3)}
