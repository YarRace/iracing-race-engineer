"""Гоночная стратегия в реальном времени: топливо + шины + питстоп.

StrategyTracker накапливает поток live-кадров, считает расход топлива и износ
шин по кругам и выдаёт рекомендации: сколько долить на питстопе, хватит ли до
финиша, пора ли менять резину. Детерминирован, тестируется синтетикой.
"""
from __future__ import annotations

import math

NO_LIMIT = 32767  # SessionLapsRemain в «бесконечной» сессии (практика/тест)


def _min_wear(tire_wear):
    if not tire_wear:
        return None
    vals = [v for corner in tire_wear.values() for v in corner.values()]
    return min(vals) if vals else None


class StrategyTracker:
    def __init__(self, tank_capacity=89.0, reserve_laps=1.0, fuel_window=5,
                 tire_change_threshold=0.30):
        self.cap = tank_capacity
        self.reserve_laps = reserve_laps
        self.window = fuel_window
        self.tire_thr = tire_change_threshold
        self._last_lap = None
        self._lap_start_fuel = None
        self._lap_start_t = None
        self._lap_start_wear = None
        self._burns = []        # литры за круг
        self._lap_times = []    # секунды за круг
        self._wear_rates = []   # падение износа за круг
        self._fuel = None
        self._laps_remain = None
        self._time_remain = None
        self._wear = None

    def update(self, lap, t, fuel, laps_remain=None, time_remain=None, tire_wear=None):
        """Один live-кадр. На смене номера круга фиксирует расход/износ за круг."""
        self._fuel = fuel
        self._laps_remain = laps_remain
        self._time_remain = time_remain
        self._wear = tire_wear

        if self._last_lap is None:
            self._last_lap = lap
            self._lap_start_fuel = fuel
            self._lap_start_t = t
            self._lap_start_wear = _min_wear(tire_wear)
            return

        if lap != self._last_lap:
            burn = (self._lap_start_fuel - fuel) if self._lap_start_fuel is not None else 0
            lap_time = t - self._lap_start_t if self._lap_start_t is not None else 0
            if burn > 0:                       # отрицательный = дозаправка, игнор
                self._burns.append(burn)
            if lap_time > 0:
                self._lap_times.append(lap_time)
            cur_w = _min_wear(tire_wear)
            if cur_w is not None and self._lap_start_wear is not None:
                rate = self._lap_start_wear - cur_w
                if rate > 0:
                    self._wear_rates.append(rate)
            self._last_lap = lap
            self._lap_start_fuel = fuel
            self._lap_start_t = t
            self._lap_start_wear = cur_w

    def _avg(self, xs):
        w = xs[-self.window:]
        return sum(w) / len(w) if w else None

    def _laps_to_go(self, avg_lap_time):
        lr = self._laps_remain
        if lr is not None and 0 < lr < NO_LIMIT:
            return int(lr)
        tr = self._time_remain
        if tr is not None and 0 < tr < 1e6 and avg_lap_time:
            return int(math.ceil(tr / avg_lap_time))
        return None

    def snapshot(self):
        avg_burn = self._avg(self._burns)
        avg_lap = self._avg(self._lap_times)
        laps_to_go = self._laps_to_go(avg_lap)
        fuel = self._fuel

        out = {
            "fuel": round(fuel, 1) if fuel is not None else None,
            "tank": self.cap,
            "avg_burn": round(avg_burn, 2) if avg_burn else None,
            "last_burn": round(self._burns[-1], 2) if self._burns else None,
            "avg_lap_time": round(avg_lap, 2) if avg_lap else None,
            "laps_to_go": laps_to_go,
            "laps_on_fuel": None,
            "fuel_to_add": None,
            "pit_needed_for_fuel": None,
        }

        if avg_burn and fuel is not None:
            out["laps_on_fuel"] = round(fuel / avg_burn, 1)
            if laps_to_go is not None:
                fuel_to_finish = laps_to_go * avg_burn
                reserve = self.reserve_laps * avg_burn
                add = fuel_to_finish + reserve - fuel
                out["fuel_to_add"] = round(max(0.0, min(add, self.cap)), 1)
                out["pit_needed_for_fuel"] = fuel < fuel_to_finish

        # шины
        wear_rate = self._avg(self._wear_rates)
        tire_min = _min_wear(self._wear)
        out["tire_min"] = round(tire_min, 3) if tire_min is not None else None
        out["tire_wear_per_lap"] = round(wear_rate, 3) if wear_rate else None
        out["tire_laps_left"] = None
        out["change_tires"] = None
        if tire_min is not None:
            change = tire_min <= self.tire_thr
            if wear_rate:
                left = (tire_min - self.tire_thr) / wear_rate
                out["tire_laps_left"] = round(max(0.0, left), 1)
                if laps_to_go is not None and left < laps_to_go:
                    change = True
            out["change_tires"] = bool(change)
        return out
