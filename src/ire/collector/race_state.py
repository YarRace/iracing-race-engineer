"""Гоночные «помощники»: тайминг, флаги трассы, предупреждения, погода, gap.

Читает живой ir и декодирует битовые маски iRacing (SessionFlags, EngineWarnings)
в человекочитаемые списки. Чистые декодеры тестируются без сима.
"""
from config import channels

# Битовые маски флагов трассы iRacing (главные для гонщика).
_SESSION_FLAGS = [
    (0x00000004, "green", "зелёный"),
    (0x00000008, "yellow", "жёлтый"),
    (0x00000100, "yellow_waving", "жёлтый машет"),
    (0x00004000, "caution", "полный жёлтый"),
    (0x00008000, "caution_waving", "полный жёлтый"),
    (0x00000020, "blue", "синий — пропусти"),
    (0x00000002, "white", "белый — последний круг"),
    (0x00000001, "checkered", "клетчатый — финиш"),
    (0x00000010, "red", "красный — стоп"),
    (0x00010000, "black", "чёрный флаг"),
    (0x00100000, "repair", "ремонт (meatball)"),
    (0x00020000, "disqualify", "дисквалификация"),
]
# Битовые маски предупреждений двигателя.
_ENGINE_WARNINGS = [
    (0x01, "water", "перегрев ОЖ"),
    (0x02, "fuel_press", "давление топлива"),
    (0x04, "oil_press", "давление масла"),
    (0x08, "stalled", "двигатель заглох"),
    (0x10, "pit_limiter", "пит-лимитер"),
    (0x20, "rev_limiter", "отсечка оборотов"),
    (0x40, "oil_temp", "перегрев масла"),
]


def decode_flags(bits):
    bits = int(bits or 0)
    return [{"key": k, "label": lbl} for mask, k, lbl in _SESSION_FLAGS if bits & mask]


def decode_warnings(bits):
    bits = int(bits or 0)
    return [{"key": k, "label": lbl} for mask, k, lbl in _ENGINE_WARNINGS if bits & mask]


def _gaps(ir, my_pos):
    """Разрыв (сек) до соперника впереди и сзади по позиции. Грубо, по CarIdxEstTime."""
    try:
        di = ir["DriverInfo"] or {}
        my_idx = di.get(channels.DRIVER_CAR_IDX)
        pos = ir[channels.RACE_ARRAYS["pos"]]
        est = ir[channels.RACE_ARRAYS["est_time"]]
        if my_idx is None or not pos or not my_pos:
            return None, None
        my_est = est[my_idx]
        ahead = behind = None
        for i, p in enumerate(pos):
            if p == 0 or i == my_idx:
                continue
            if p == my_pos - 1:
                ahead = round(abs(est[i] - my_est), 1)
            elif p == my_pos + 1:
                behind = round(abs(est[i] - my_est), 1)
        return ahead, behind
    except Exception:
        return None, None


def sector_starts(ir):
    """Доли круга, где начинаются сектора, из ir['SplitTimeInfo']. [] если нет."""
    try:
        info = ir["SplitTimeInfo"] or {}
        secs = info.get("Sectors") or []
        starts = sorted(float(s["SectorStartPct"]) for s in secs)
        return starts if len(starts) >= 2 else []
    except Exception:
        return []


class SectorTimer:
    """Засекает время по секторам круга, отслеживая LapDistPct."""
    def __init__(self, starts):
        self.starts = sorted(starts)              # напр. [0.0, 0.33, 0.66]
        self._cur = None
        self._entry_t = None
        self._times = {}

    def _sector_of(self, pct):
        idx = 0
        for i, s in enumerate(self.starts):
            if pct >= s:
                idx = i
        return idx

    def update(self, lap_dist_pct, t):
        if not self.starts or lap_dist_pct is None:
            return
        idx = self._sector_of(lap_dist_pct)
        if self._cur is None:
            self._cur, self._entry_t = idx, t
            return
        if idx != self._cur:                      # сменился сектор → зафиксировать прошлый
            dt = t - self._entry_t
            if 0 < dt < 600:
                self._times[self._cur] = round(dt, 2)
            self._cur, self._entry_t = idx, t

    def lap_sectors(self):
        return [self._times.get(i) for i in range(len(self.starts))]

    def reset(self):
        self._cur = None
        self._entry_t = None
        self._times = {}


def race_extras(ir):
    """Снимок гоночной телеметрии для дашборда."""
    R = channels.RACE_SCALAR
    g = {k: ir[v] for k, v in R.items()}
    ahead, behind = _gaps(ir, g.get("position"))
    best = g["best_lap_time"]
    delta = g["delta_best"]
    predicted = round(best + delta, 2) if best and best > 0 else None  # прогноз круга
    return {
        "position": g["position"], "class_position": g["class_position"],
        "cur_lap_time": g["cur_lap_time"], "last_lap_time": g["last_lap_time"],
        "best_lap_time": g["best_lap_time"], "delta_best": g["delta_best"],
        "predicted": predicted,
        "rpm": g["rpm"], "shift_pct": g["shift_pct"],
        "shift_rpm": g["shift_rpm"], "blink_rpm": g["blink_rpm"],
        "abs_active": bool(g["abs_active"]),
        "flags": decode_flags(g["session_flags"]),
        "warnings": decode_warnings(g["engine_warnings"]),
        "wind_vel": g["wind_vel"], "wind_dir": g["wind_dir"], "humidity": g["humidity"],
        "skies": g["skies"], "track_wetness": g["track_wetness"],
        "energy_pct": g["energy_pct"], "deploy_pct": g["deploy_pct"],
        "gap_ahead": ahead, "gap_behind": behind,
        "lap": g["lap"], "on_pit": bool(g["on_pit"]),
    }
