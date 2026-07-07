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


def plan_race(laps_to_go, avg_burn, fuel, tank, reserve_laps=1.0, cur_lap=None):
    """Планировщик гонки (как «Aero's plan»): по остатку кругов, среднему расходу
    и баку считает СКОЛЬКО пит-стопов нужно, когда первый, сколько лить и на
    сколько экономить топливо, чтобы убрать один пит. Чистая функция.

    Возвращает None, если данных недостаточно (нет лимита кругов/расхода/топлива).
    """
    if not laps_to_go or not avg_burn or fuel is None or not tank:
        return None
    if laps_to_go <= 0 or avg_burn <= 0:
        return None
    usable_now = fuel / avg_burn - reserve_laps            # кругов на текущем баке (с запасом)
    usable_tank = tank / avg_burn - reserve_laps           # кругов на полном баке
    if usable_tank <= 0:
        return None
    fuel_to_finish = laps_to_go * avg_burn
    needed_total = fuel_to_finish + reserve_laps * avg_burn
    stops = 0 if usable_now >= laps_to_go else \
        int(math.ceil((laps_to_go - usable_now) / usable_tank))
    add_total = max(0.0, needed_total - fuel)
    per_stop = min(add_total / stops, tank) if stops else None
    laps_until_stop = max(0, int(math.floor(usable_now))) if stops else None
    next_stop_lap = (cur_lap + laps_until_stop) if (cur_lap and laps_until_stop is not None) else None

    plan = {
        "laps_to_go": int(laps_to_go),
        "stops": stops,
        "stint_laps": int(math.floor(usable_tank)),
        "fuel_to_add_total": round(add_total, 1),
        "fuel_per_stop": round(per_stop, 1) if per_stop is not None else None,
        "laps_until_stop": laps_until_stop,
        "next_stop_lap": next_stop_lap,
        "save_to_skip": None,
    }
    # на сколько экономить топливо, чтобы убрать ОДИН пит — показываем только если
    # это реалистично (экономия до ~25% расхода), иначе смысла нет.
    if stops >= 1:
        avail = fuel + (stops - 1) * tank                  # топливо при stops-1 остановках
        b_target = avail / (laps_to_go + reserve_laps)      # целевой расход л/круг
        save = avg_burn - b_target
        if 0 < save <= avg_burn * 0.25:
            plan["save_to_skip"] = round(save, 2)
    return plan


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
        if lap is None or t is None or fuel is None:
            return                              # неполный кадр — пропускаем
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

        # план гонки: пит-стопы/топливо на всю дистанцию (Фаза 3)
        out["plan"] = plan_race(laps_to_go, avg_burn, fuel, self.cap,
                                 self.reserve_laps, self._last_lap)
        return out
