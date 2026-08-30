"""Демо-поток телеметрии: правдоподобный заезд без запущенного симулятора.

Зачем. Настраивать оверлей на пустых данных бесполезно — виджет показывает
прочерки, и не видно ни цветов, ни ширины колонок, ни того, влезает ли текст.
Раньше, чтобы что-то настроить, приходилось запускать iRacing и выезжать на
трассу. Теперь предпросмотр наполняется сам.

Тот же поток годится для витрины на сайте: 42 виджета рендерятся в картинки
из этих данных, без сима и без ручной работы.

Данные СИНТЕТИЧЕСКИЕ и подписаны как таковые — имена пилотов выдуманные,
трасса условная. Это не запись чужого заезда: своих кругов у нас на диске
всего один, а чужие круги Garage 61 отдаёт по лицензии, которая не
подразумевает выкладывание их на витрину.

Модель круга простая: скорость по синусоиде с прямой и парой поворотов,
газ и тормоз выводятся из неё же, топливо убывает, резина изнашивается.
Задача — не симулировать физику, а дать виджетам правдоподобные диапазоны.
"""
from __future__ import annotations

import math
import time

LAP_TIME = 92.0                      # секунд на круг — как GTP на средней трассе
TANK = 89.0
BURN_PER_LAP = 3.1

DRIVERS = [
    ("Marek Ostrowski", 3410), ("Yuto Shibata", 3320), ("Iaroslav Chizhov", 3287),
    ("Alida Vieira", 3190), ("Tom Selby", 3105), ("Nils Bergqvist", 2980),
]
ME = 2                               # индекс игрока в списке выше


def _shape(u):
    """Профиль круга по доле дистанции u (0..1): прямая, шпилька, две дуги.

    Возвращает долю скорости 0..1. Первый вариант имел слишком широкий синус
    в основе, из-за чего пятая часть круга упиралась в нижний предел и машина
    «парковалась» на минимальной скорости — на графике это выглядело как
    остановка. Теперь основание поднято, а повороты вычитаются из него, и
    ограничитель не срабатывает вовсе.
    """
    v = 0.63 + 0.27 * math.sin(2 * math.pi * (u - 0.08))
    v -= 0.30 * math.exp(-((u - 0.34) ** 2) / 0.0015)      # шпилька
    v -= 0.17 * math.exp(-((u - 0.72) ** 2) / 0.0035)      # средний поворот
    v -= 0.12 * math.exp(-((u - 0.88) ** 2) / 0.0025)      # связка перед стартом
    return max(0.12, min(1.0, v))


class DemoFeed:
    """Подставляется вместо Store: тот же get(), но данные считаются на лету."""

    ok = True

    def __init__(self, t0=None):
        self._t0 = t0 if t0 is not None else time.monotonic()
        self._active = set()

    # ---------- совместимость со Store ----------
    def set_active(self, endpoints):
        self._active = set(endpoints)

    def start(self):
        return

    def stop(self):
        return

    # ---------- сама выдумка ----------
    def _clock(self):
        el = time.monotonic() - self._t0
        lap = int(el // LAP_TIME) + 8                       # начинаем с восьмого круга
        u = (el % LAP_TIME) / LAP_TIME                      # доля дистанции
        return el, lap, u

    def get(self, ep):
        el, lap, u = self._clock()
        v = _shape(u)
        speed = 18.0 + v * 62.0                            # м/с: 65…290 км/ч
        rpm = 3200 + v * 4200
        # газ и тормоз выводим из изменения скорости, а не задаём отдельно —
        # иначе они разъезжаются с картинкой и виджет ввода выглядит фальшиво
        dv = _shape(min(1.0, u + 0.01)) - v
        # Множители подобраны замером, а не на глаз: производная профиля лежит
        # в пределах ±0.07, поэтому при 26 педали залипали в крайних значениях
        # весь круг и виджет ввода выглядел фальшиво.
        throttle = max(0.0, min(1.0, 0.35 + dv * 9.0))
        brake = max(0.0, min(1.0, -dv * 13.3))
        steer = 0.55 * math.sin(2 * math.pi * u * 3.0) * (1.0 - v * 0.6)

        burned = (lap - 8 + u) * BURN_PER_LAP
        fuel = max(2.0, TANK * 0.62 - burned % 40)
        wear = max(0.28, 1.0 - ((lap - 8 + u) * 0.011))
        delta = 0.35 * math.sin(2 * math.pi * (u * 2.1 + 0.3)) - 0.12

        if ep == "live":
            return {
                "speed": speed, "gear": max(1, min(7, int(1 + v * 6))),
                "rpm": rpm, "shift_rpm": 7400,
                "throttle": throttle, "brake": brake, "steer": steer, "clutch": 0.0,
                "lat_accel": steer * 28.0, "long_accel": dv * 300.0,
                "yaw_rate": steer * 1.1,
                "track_temp": 31.5 + math.sin(el / 90) * 1.6,
                "air_temp": 22.4, "oil_temp": 104.0, "water_temp": 91.0,
                "brake_bias": 54.5, "on_track": True,
                "tires": {c: {"tl": 78 + i * 3 + v * 14, "tm": 82 + i * 3 + v * 14,
                              "tr": 86 + i * 3 + v * 14}
                          for i, c in enumerate(("LF", "RF", "LR", "RR"))},
                "shock_defl": {},
            }

        if ep == "race":
            return {
                "lap": lap, "position": 3, "class_position": 3,
                "gap_ahead": 1.1 + 0.5 * math.sin(el / 12),
                "gap_behind": 0.9 + 0.4 * math.cos(el / 9),
                "last_lap_time": LAP_TIME + 0.4, "best_lap_time": LAP_TIME - 0.6,
                "predicted": LAP_TIME + delta, "delta_best": delta,
                "rpm": rpm, "shift_rpm": 7400, "on_pit": False,
                "car_left_right": 2 if 0.3 < u < 0.36 else 1,
                "flags": [{"key": "green", "label": "green"}],
                "warnings": [],
                "energy_pct": 0.35 + 0.4 * (1 - u), "deploy_pct": 0.68,
                "wind_vel": 3.2, "wind_dir": 1.9, "humidity": 0.41,
                "track_wetness": 1, "incidents": 2, "laps_total": 30,
                "lap_log": [{"lap": lap - i, "time": LAP_TIME + (i % 4) * 0.3 - 0.4}
                            for i in range(1, 9)],
            }

        if ep == "standings":
            rows = []
            for i, (name, ir) in enumerate(DRIVERS):
                rows.append({
                    "pos": i + 1, "name": name, "is_player": i == ME,
                    "best": LAP_TIME - 1.0 + i * 0.35,
                    "last": LAP_TIME - 0.4 + i * 0.4,
                    "gap": (i - ME) * 1.3,
                    "car": "Ferrari 499P", "car_path": "ferrari499p",
                    "manufacturer": "ferrari", "class_color": 0xF1C40F,
                    "irating": ir, "lic_color": "#00c000", "license": "A 3.2",
                })
            return rows

        if ep == "relative":
            # Формат — как у боевого сборщика: список cars с разрывом от нас.
            # Первый вариант отдавал ahead/behind, и виджет честно писал
            # «no data»: я угадал структуру вместо того, чтобы прочитать её.
            cars = []
            for i, (name, ir) in enumerate(DRIVERS):
                cars.append({
                    "name": name, "number": 10 + i, "is_player": i == ME,
                    "gap": round((i - ME) * 1.15 + 0.2 * math.sin(el / 7 + i), 2),
                    # разводим по кругу заметно: при 3% все шесть машин слипались
                    # в одну точку на карте трассы
                    "lap_pct": (u + (ME - i) * 0.11) % 1.0,
                    "class_color": 0xF1C40F, "manufacturer": "ferrari",
                    "irating": ir, "on_pit": False,
                })
            return {"cars": cars}

        if ep == "strategy":
            return {
                "fuel": round(fuel, 1), "tank": TANK, "avg_burn": BURN_PER_LAP,
                "last_burn": BURN_PER_LAP + 0.06, "min_burn": BURN_PER_LAP - 0.3,
                "max_burn": BURN_PER_LAP + 0.35, "avg_lap_time": LAP_TIME,
                "laps_to_go": max(1, 30 - (lap - 8)),
                "laps_on_fuel": round(fuel / BURN_PER_LAP, 1),
                "fuel_to_add": 18.4, "pit_needed_for_fuel": True,
                "tire_min": round(wear, 3), "tire_wear_per_lap": 0.011,
                "tire_laps_left": round(max(0.0, (wear - 0.3) / 0.011), 1),
                "change_tires": wear < 0.35,
                "plan": {"stops": 1, "first_stop_lap": lap + 6, "add_each": 34.0},
            }

        if ep == "wear":
            return {c: {"l": round(wear + 0.05 - i * 0.02, 3),
                        "m": round(wear - i * 0.02, 3),
                        "r": round(wear - 0.06 - i * 0.02, 3),
                        "min": round(wear - 0.06 - i * 0.02, 3)}
                    for i, c in enumerate(("LF", "RF", "LR", "RR"))}

        if ep == "session":
            return {"session_type": "Race", "laps_total": 30,
                    "laps_remain": max(0, 30 - (lap - 8)),
                    "time_remain": max(0.0, 30 * LAP_TIME - el),
                    "record": LAP_TIME - 1.2, "sof": 2840,
                    "time_of_day": "15:42"}

        if ep == "damage":
            return {"incidents": 2, "team_incidents": 6, "team": []}

        if ep == "result":
            return {"symptoms": {
                "inputs": {"trail_brake_pct": 27.0, "throttle_smoothness": 0.79},
                "tire": {"front_rear_balance": 3.8},
                "balance": {"entry": {"tendency": "understeer"},
                            "mid": {"tendency": "neutral"},
                            "exit": {"tendency": "oversteer"}}}}

        if ep == "trackmap":
            pts = []
            for i in range(160):
                a = 2 * math.pi * i / 160
                r = 34 + 12 * math.sin(3 * a) + 5 * math.cos(5 * a)
                pts.append({"x": 50 + r * math.cos(a), "y": 50 + r * math.sin(a) * 0.72,
                            "pct": i / 160})
            return {"points": pts, "official": False, "source": "demo",
                    "track": "Demo Circuit", "config": ""}

        return {}
