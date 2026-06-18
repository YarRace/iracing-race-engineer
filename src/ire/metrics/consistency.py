def consistency_metrics(frames, min_lap=15.0, max_lap=1200.0):
    # время круга = разница session-time между сменами номера круга
    marks = []
    last_lap, last_t = None, None
    for f in frames:
        if f["lap"] != last_lap:
            if last_t is not None:
                marks.append(f["t"] - last_t)
            last_lap, last_t = f["lap"], f["t"]
    # отбрасываем «мусорные» интервалы: рестарт, пересечение линии, заезд в пит
    # дают доли секунды; настоящий круг — между min_lap и max_lap секунд
    laps = [round(x, 2) for x in marks if min_lap <= x <= max_lap]
    if not laps:
        return {"lap_count": 0, "best_lap": None, "spread": None, "mean": None}
    return {"lap_count": len(laps), "best_lap": min(laps),
            "spread": round(max(laps) - min(laps), 2),
            "mean": round(sum(laps) / len(laps), 2)}
