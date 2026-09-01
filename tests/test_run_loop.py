"""Живой цикл `run.py` без симулятора: подменяем irsdk и крутим кадры.

Зачем такой тест вообще нужен. `run.py` — единственный кусок программы, где
всё сходится вместе, и проверить его до сих пор было нечем: сим на машине с
тестами не запущен и не будет. Из-за этого там годами могла жить ошибка,
которая видна только на пит-волле, — и она там жила.
"""
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


class FakeIR:
    """Подставной pyirsdk: отдаёт ровно те каналы, что просит цикл."""

    def __init__(self, on_track=False):
        self.is_initialized = True
        self.is_connected = True
        self._t = 0.0
        self._lap = 1
        self._on_track = on_track
        self.frozen = {}

    # Цикл ходит и как ir[...], и как ir.freeze_var_buffer_latest()
    def freeze_var_buffer_latest(self):
        self._t += 1.0
        self._lap += 1

    def unfreeze_var_buffer_latest(self):
        pass

    def shutdown(self):
        pass

    def __getitem__(self, key):
        return self._value(key)

    def get(self, key, default=None):
        v = self._value(key)
        return default if v is None else v

    def _value(self, key):
        table = {
            "SessionTime": self._t,
            "SessionNum": 0,
            "LapDistPct": (self._t % 10) / 10.0,
            "Lap": self._lap,
            "LapCompleted": self._lap - 1,
            "LapLastLapTime": 92.0,
            "LapBestLapTime": 91.0,
            "IsOnTrack": self._on_track,
            "IsOnTrackCar": self._on_track,
            "PlayerCarIdx": 0,
            "FuelLevel": 50.0,
            "Speed": 60.0,
        }
        if key in table:
            return table[key]
        if key in ("WeekendInfo", "DriverInfo", "SessionInfo", "SplitTimeInfo",
                   "CarSetup", "CameraInfo", "RadioInfo", "QualifyResultsInfo"):
            return {}
        return 0


def test_the_frame_used_by_the_lap_log_exists_on_every_iteration():
    """Главная проверка. Лог кругов брал температуру и топливо из `f`, а `f`
    связывается только в ветке «за рулём я». Пока первую смену ведёт напарник,
    этого имени не существует: на первом завершённом круге выходил NameError,
    его глотал общий except — и вместе с логом замирали race, standings,
    relative и session, а круги переставали попадать в историю.

    Проверяем по исходнику, а не запуском цикла: цикл бесконечный и лезет в
    сеть и в базу. Зато условие точное — имя, которое читает лог кругов,
    обязано связываться ВНЕ ветки «за рулём».
    """
    src = (ROOT / "run.py").read_text(encoding="utf-8").splitlines()

    log_line = next(i for i, ln in enumerate(src) if '"track_temp":' in ln)
    name = src[log_line].split(":")[1].strip().split(".")[0]
    assert name != "f", (
        "лог кругов снова читает `f` — его нет, пока за рулём напарник")

    # Где это имя связывается и внутри ли ветки «за рулём».
    bound = [i for i, ln in enumerate(src)
             if ln.strip().startswith(name + " = ")]
    assert bound, f"имя {name} нигде не связывается"

    running = next(i for i, ln in enumerate(src) if 'state == "running"' in ln)
    assert any(i < running for i in bound), (
        f"{name} связывается только внутри ветки «за рулём» — "
        "на пит-волле лог кругов снова упадёт")


def test_the_stale_frame_is_not_reused_across_a_driver_change():
    """Заглушка `f = {}` закрыла бы падение и оставила вторую половину беды:
    после смены пилота имя хранит кадр прошлой смены, и первый круг новой
    трассы унёс бы температуру предыдущей."""
    src = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "live = live_frame(ir)" in src, "кадр больше не строится каждый кадр"
    assert 'STATE["live"] = live' in src


@pytest.mark.parametrize("on_track", [False, True])
def test_a_frame_is_built_whoever_is_driving(on_track):
    """То же самое, но по существу: live_frame отдаёт температуру и топливо
    независимо от того, кто за рулём."""
    from ire.collector.live_state import live_frame

    ir = FakeIR(on_track=on_track)
    frame = live_frame(ir)
    assert isinstance(frame, dict)
    assert "fuel" in frame, "в кадре нет топлива — лог кругов запишет пустоту"
