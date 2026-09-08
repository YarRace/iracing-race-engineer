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

# Три сектора на круг: доли 0 / 0.36 / 0.71 — как на обычной трассе.
_S_START = (0.0, 0.36, 0.71)
_S_REF = (33.1, 32.2, 26.7)          # лучший круг демо-сессии, сумма ≈ 92.0
_S_BEST = (32.9, 32.2, 26.7)         # первый сектор когда-то вышел лучше


def _demo_sectors(u, el):
    """Живые сектора для витрины: пройденные с дельтой, текущий с временем."""
    now = max(i for i, s in enumerate(_S_START) if u >= s)
    cur, delta, record = [], [], []
    for i in range(3):
        if i < now:
            # Немного гуляющая дельта, чтобы было видно и зелёное, и красное.
            d = round(0.28 * math.sin(el / 7.0 + i * 2.1) - 0.06, 2)
            cur.append(round(_S_REF[i] + d, 2))
            delta.append(d)
            record.append(cur[i] <= _S_BEST[i])
        else:
            cur.append(None)
            delta.append(None)
            record.append(False)
    elapsed = round((u - _S_START[now]) * LAP_TIME, 2)
    return {"count": 3, "now": now, "elapsed": elapsed,
            "cur": cur, "ref": list(_S_REF), "best": list(_S_BEST),
            "delta": delta, "record": record, "have_ref": True}

TANK = 89.0
BURN_PER_LAP = 3.1

DRIVERS = [
    ("Marek Ostrowski", 3410), ("Yuto Shibata", 3320), ("Yaroslav Chizhov", 3287),
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

        if ep == "corners":
            # Разбор круга для предпросмотра. Числа выдуманы, но форма — та же,
            # что отдаёт /api/corners: настраивать виджет по прочеркам нельзя.
            return {
                "ok": True, "track": "Demo Circuit", "car": "Demo GTP",
                "lap_time": LAP_TIME + 0.62, "ref_time": LAP_TIME,
                "delta": 0.62, "points": 1000,
                "segments": [
                    {"index": 1, "start": 0, "end": 210, "apex": 120,
                     "loss": 0.31, "phase": "braking",
                     "text": "You braked earlier than the reference."},
                    {"index": 2, "start": 210, "end": 430, "apex": 300,
                     "loss": 0.0, "phase": "none",
                     "text": "Matched the reference through here."},
                    {"index": 3, "start": 430, "end": 700, "apex": 560,
                     "loss": 0.19, "phase": "apex",
                     "text": "Your minimum speed was 6 km/h lower."},
                    {"index": 4, "start": 700, "end": 1000, "apex": 850,
                     "loss": 0.12, "phase": "exit",
                     "text": "You got back to full throttle later."},
                ],
            }

        if ep == "live":
            return {
                "speed": speed, "gear": max(1, min(7, int(1 + v * 6))),
                "rpm": rpm, "shift_rpm": 7400,
                # круг и топливо приходят из SDK в том же кадре: без них
                # карточка приборов показывает прочерки посреди живых цифр
                "lap": lap, "fuel": round(55.2 - (lap - 1) * 3.1 - u * 3.1, 1),
                "throttle": throttle, "brake": brake, "steer": steer, "clutch": 0.0,
                "lat_accel": steer * 28.0, "long_accel": dv * 300.0,
                "yaw_rate": steer * 1.1,
                "track_temp": 31.5 + math.sin(el / 90) * 1.6,
                "air_temp": 22.4, "oil_temp": 104.0, "water_temp": 91.0,
                "brake_bias": 54.5, "on_track": True,
                # tl/tm/tr — стороны в координатах МАШИНЫ, поэтому у правых
                # колёс градиент зеркальный. Раньше он был одинаковым, и
                # витрина показывала невозможную машину: слева греется
                # внутренняя кромка, справа — внешняя. Отрицательный развал
                # стоит на обеих сторонах и греет внутреннюю у всех четырёх.
                #
                # Перекос РАЗНЫЙ по колёсам, и это не украшательство: когда
                # он одинаковый, Tyre Tool пишет «too much camber» на всех
                # четырёх сразу, и инструмент выглядит так, будто ругается
                # всегда. Ради этого он и нужен — отличать колесо, где
                # развал работает, от колеса, где его перебор.
                "tires": {c: dict(zip(("tl", "tm", "tr"),
                                      (out, mid, inn) if c[0] == "L"
                                      else (inn, mid, out)))
                          for i, c in enumerate(("LF", "RF", "LR", "RR"))
                          for skew in [(3.0, 4.0, 3.5, 8.0)[i]]
                          for base in [80 + i * 3 + v * 14]
                          for out, mid, inn in [(base - skew / 2,
                                                 base + 1.0,
                                                 base + skew / 2)]},
                "shock_defl": {},
            }

        if ep == "race":
            return {
                "lap": lap, "position": 3, "class_position": 3,
                "gap_ahead": 1.1 + 0.5 * math.sin(el / 12),
                "gap_behind": 0.9 + 0.4 * math.cos(el / 9),
                "last_lap_time": LAP_TIME + 0.4, "best_lap_time": LAP_TIME - 0.6,
                "predicted": LAP_TIME + delta, "delta_best": delta,
                # blink_rpm — верх шкалы оборотов. Без него дашборд не рисует
                # ни полосу RPM, ни карточку шифта: он делит на этот предел.
                "rpm": rpm, "shift_rpm": 7400, "blink_rpm": 7800, "on_pit": False,
                "car_left_right": 2 if 0.3 < u < 0.36 else 1,
                "flags": [{"key": "green", "label": "green"}],
                "warnings": [],
                "energy_pct": 0.35 + 0.4 * (1 - u), "deploy_pct": 0.68,
                "wind_vel": 3.2, "wind_dir": 1.9, "humidity": 0.41,
                "track_wetness": 1, "incidents": 2, "laps_total": 30,
                "lap_log": [{"lap": lap - i,
                             "time": LAP_TIME + (i % 4) * 0.3 - 0.4,
                             "track_temp": 31.5 + (i % 3) * 0.7,
                             "fuel": round(fuel + i * BURN_PER_LAP, 1)}
                            for i in range(1, 9)],
                # Сектора живут по ходу круга: пройденные стоят на месте,
                # текущий тикает. Без этого виджет секторов в галерее
                # показывал бы «нет секторов» и читался как сломанный.
                "sectors": _demo_sectors(u, el),
            }

        if ep == "tyres":
            # Берём ТЕ ЖЕ температуры, что показывает виджет Tire temps.
            #
            # Раньше здесь стояли числа, снятые с настоящей сессии на Road
            # America (60 °C), а живая телеметрия демо давала 90–105 °C. В
            # одном шкафу с товаром стояли две разные машины: виджет
            # температур показывал одно, Tyre Tool — другое, и вердикт «too
            # much camber» относился к колёсам, которых на соседней карточке
            # нет. Числа из настоящего заезда честнее по происхождению, но
            # витрина должна описывать ОДНУ сессию.
            from ire.metrics.tire import edges, tire_metrics
            from ire.metrics.tyres import report as _tyre_report

            live_t = self.get("live")["tires"]
            t = tire_metrics([{"tires": live_t}])
            return _tyre_report(t, {
                "TiresAero.LeftFront.StartingPressure": "152 kPa",
                "TiresAero.RightFront.StartingPressure": "152 kPa",
                "TiresAero.LeftRear.StartingPressure": "148 kPa",
                "TiresAero.RightRear.StartingPressure": "148 kPa"})

        if ep == "standings":
            # Поля добираются ТЕМ ЖЕ кодом, что и в бою: `_add_gaps` считает
            # `gap_txt`, `parse_license` разбирает лицензию на букву и число.
            # Раньше их просто не было, и витрина показывала таблицу с двумя
            # пустыми колонками — SR и GAP. Угадывать структуру ответа тут
            # уже пробовали, ниже об этом стоит отдельная запись.
            from ire.collector.standings import LICENSE_COLORS, _add_gaps, parse_license

            rows = []
            for i, (name, ir) in enumerate(DRIVERS):
                lic = ["A 3.42", "A 4.10", "B 3.28", "A 2.95", "B 4.51",
                       "C 3.07"][i % 6]
                letter, sr = parse_license(lic)
                rows.append({
                    "pos": i + 1, "name": name, "is_player": i == ME,
                    "number": 10 + i,
                    "best": LAP_TIME - 1.0 + i * 0.35,
                    "last": LAP_TIME - 0.4 + i * 0.4,
                    # Разрыв ДО ЛИДЕРА, как его отдаёт сим, а не до меня:
                    # у боевого сборщика это `f2[idx]` и он всегда ≥ 0.
                    # С отрицательными числами `_add_gaps` печатал «—» у
                    # тех, кто впереди меня, — две пустые строки в колонке.
                    "gap": i * 1.3,
                    "lap": 8,
                    "car": "Ferrari 499P", "car_path": "ferrari499p",
                    "car_class": "GTP",
                    "manufacturer": "ferrari", "class_color": 0xF1C40F,
                    "irating": ir, "license": lic, "lic": letter, "sr": sr,
                    "lic_color": LICENSE_COLORS.get(letter, "#9099a6"),
                    "on_pit": False, "out": False,
                })
            _add_gaps(rows, True)
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
            # Остаток протектора — доля от нового, то есть НЕ БОЛЬШЕ единицы.
            # Раньше внешняя зона получала `wear + 0.05` и на первых кругах
            # выходила 1.05: карточка честно печатала «105%», а протектора
            # больше, чем у новой шины, не бывает. Ошибка была видна ровно
            # там, где на неё смотрят, и ровно поэтому её никто не искал.
            def zones(i):
                mid = min(1.0, wear - i * 0.02)
                return {"l": round(min(1.0, mid + 0.05), 3),
                        "m": round(mid, 3),
                        "r": round(max(0.0, mid - 0.06), 3),
                        "min": round(max(0.0, mid - 0.06), 3)}

            return {c: zones(i)
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
