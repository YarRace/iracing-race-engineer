"""Сколько стоит один кадр живого цикла — и не подорожал ли он.

Никто этого ни разу не мерил. Замер на ПОЛНОМ поле (60 машин, как на Сарте
в 24 часа) показал 0.5 мс на кадр — три процента одного ядра при 60 кадрах
в секунду. То есть чинить нечего, и теперь это можно сказать числом, а не
на ощупь.

Смысл теста не в том, чтобы стеречь доли миллисекунды: машина, на которой
он бежит, каждый раз другая. Смысл — поймать смену ПОРЯДКА: случайный
проход по полю внутри прохода по полю превращает 0.5 мс в 30, и заметить
это по ощущениям невозможно, пока не сядешь в гонку с полным пелотоном.

Здесь же живёт подставной SDK на 60 машин. Остальные тесты работают на
шести, и всё, что дорожает от числа машин, на них незаметно.
"""
import time

import pytest

from ire.collector import live_state, race_state, standings

CARS = 60

# Десятикратный запас к измеренным 0.5 мс. Ловит O(n²), не ловит шум.
BUDGET_MS = 5.0


class FakeIR:
    """Тот же набор ключей и та же форма данных, что у настоящего SDK."""

    def __init__(self, n=CARS, delta=0.2):
        self.n = n
        self._delta = delta
        self.drivers = [{
            "CarIdx": i, "UserName": f"Driver {i}", "CarNumber": str(10 + i),
            "IRating": 3000 + i, "LicString": "A 3.42",
            "CarScreenNameShort": "Ferrari 499P", "CarScreenName": "Ferrari 499P",
            "CarPath": "ferrari499p", "CarClassShortName": "GTP",
            "CarClassColor": 0xF1C40F, "CarIsPaceCar": 0, "IsSpectator": 0,
        } for i in range(n)]
        self.arrays = {
            "CarIdxLapDistPct": [i / n for i in range(n)],
            "CarIdxPosition": list(range(1, n + 1)),
            "CarIdxClassPosition": list(range(1, n + 1)),
            "CarIdxOnPitRoad": [False] * n,
            "CarIdxTrackSurface": [3] * n,
            "CarIdxF2Time": [i * 1.3 for i in range(n)],
            "CarIdxLastLapTime": [92.0 + i * 0.1 for i in range(n)],
            "CarIdxBestLapTime": [91.0 + i * 0.1 for i in range(n)],
            "CarIdxLap": [8] * n,
            "CarIdxEstTime": [i * 1.2 for i in range(n)],
        }

    def __getitem__(self, k):
        if k in self.arrays:
            return self.arrays[k]
        if k == "DriverInfo":
            return {"Drivers": self.drivers, "DriverCarIdx": 3}
        if k == "WeekendInfo":
            return {"TrackName": "lemans", "TrackDisplayName": "Le Mans",
                    "TrackConfigName": "full", "EventType": "Race"}
        if k == "SessionInfo":
            return {"Sessions": [{"SessionType": "Race", "SessionLaps": 30}]}
        if k == "SessionNum":
            return 0
        return {"Speed": 70.0, "RPM": 6600, "Gear": 5, "Throttle": 0.8,
                "Brake": 0.0, "SteeringWheelAngle": 0.1, "Lap": 8,
                "LapDistPct": 0.42, "FuelLevel": 55.0, "SessionTime": 900.0,
                "SessionTimeRemain": 2700.0, "SessionLapsRemain": 22,
                "TrackTempCrew": 31.5, "AirTemp": 22.4, "YawRate": 0.1,
                "LapBestLapTime": 91.4, "LapLastLapTime": 92.4,
                "LapDeltaToBestLap": self._delta, "LapDeltaToOptimalLap": 0.1,
                "LapCurrentLapTime": 45.0, "ShiftIndicatorPct": 0.8,
                "PlayerCarSLShiftRPM": 7400, "PlayerCarSLBlinkRPM": 7600,
                "BrakeABSactive": False, "EngineWarnings": 0, "WindVel": 3.2,
                "WindDir": 1.1, "RelativeHumidity": 0.41, "Skies": 1,
                "TrackWetness": 1, "PlayerCarPosition": 4, "CamCarIdx": 5,
                "PlayerCarClassPosition": 4, "SessionFlags": 0x4,
                "PlayerCarMyIncidentCount": 2, "OilTemp": 104.0,
                "WaterTemp": 91.0, "dcBrakeBias": 54.5,
                "IsOnTrack": True, "SessionState": 4}.get(k)


def _ms(fn, reps=60):
    fn()                                    # прогрев
    t = []
    for _ in range(reps):
        a = time.perf_counter()
        fn()
        t.append((time.perf_counter() - a) * 1000.0)
    return sorted(t)[len(t) // 2]           # медиана: пик мерит не нас


@pytest.fixture(scope="module")
def ir():
    return FakeIR()


def test_a_full_field_frame_fits_the_budget(ir):
    parts = {
        "session_identity": lambda: live_state.session_identity(ir),
        "live_frame": lambda: live_state.live_frame(ir),
        "tire_wear": lambda: live_state.tire_wear_by_corner(ir),
        "standings": lambda: standings.build_standings(ir),
        "relative": lambda: race_state.build_relative(ir),
        "race_extras": lambda: race_state.race_extras(ir),
    }
    each = {name: _ms(fn) for name, fn in parts.items()}
    total = sum(each.values())
    assert total < BUDGET_MS, (
        f"кадр подорожал до {total:.2f} мс при {CARS} машинах: "
        + ", ".join(f"{k} {v:.2f}" for k, v in sorted(
            each.items(), key=lambda kv: -kv[1])))


def test_the_cost_grows_with_the_field_not_with_its_square(ir):
    """Проход по полю внутри прохода по полю — единственная поломка,
    которая незаметна на шести машинах и убивает гонку на шестидесяти."""
    small = _ms(lambda: standings.build_standings(FakeIR(10)))
    big = _ms(lambda: standings.build_standings(FakeIR(60)))
    # Шестикратное поле при линейном росте даёт ~6x. Порог 20x оставляет
    # запас на шум мелких замеров и всё равно ловит квадрат (36x).
    assert big < small * 20, f"10 машин {small:.3f} мс, 60 машин {big:.3f} мс"


def test_a_missing_delta_does_not_break_the_race_state():
    """SDK отдаёт None, когда канала нет в текущем наборе телеметрии.

    `best + None` роняло весь сбор гоночного состояния — а он один на
    позицию, разрывы, флаги и таблицу. Один такой обрыв уже стоил
    замерших виджетов на всю сессию.
    """
    out = race_state.race_extras(FakeIR(6, delta=None))
    assert out["predicted"] is None
    assert out["position"] == 4, "остальное обязано доехать"
