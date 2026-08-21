"""Хранилище телеметрии кругов: нарезка, ресемпл, запись и чтение."""
import math

import pytest

from ire.storage import laps

IDENT = {
    "track": "monza full", "track_display": "Monza", "config": None,
    "car": "Porsche 963 GTP", "car_path": "porsche963", "car_class": "GTP",
    "session_type": "Practice",
}


def _frame(lap, pct, t, **kw):
    """Кадр телеметрии: минимум того, что кладёт live_frame."""
    f = {"lap": lap, "lap_dist_pct": pct, "t": t,
         "speed": 50.0, "throttle": 1.0, "brake": 0.0, "steer": 0.0,
         "gear": 4, "lat_accel": 0.0, "long_accel": 0.0, "yaw_rate": 0.0,
         "fuel": 60.0, "track_temp": 31.0, "air_temp": 24.0,
         "tires": {"lf": {"tl": 80, "tm": 82, "tr": 84}}}
    f.update(kw)
    return f


def _lap_frames(lap, n=200, t0=0.0, speed=lambda p: 50.0):
    """Полный круг из n кадров: доля дистанции равномерно растёт от 0 до 1."""
    return [_frame(lap, i / n, t0 + i * 0.05, speed=speed(i / n)) for i in range(n)]


# ── нарезка на круги ────────────────────────────────────────────────────────

def test_split_drops_incomplete_first_and_last_laps():
    # заезд с боксов: первый круг начался с середины, последний оборвался
    frames = ([_frame(1, p / 10, p * 0.05) for p in range(5, 10)]
              + _lap_frames(2, t0=1.0) + _lap_frames(3, t0=2.0)
              + [_frame(4, p / 10, 30 + p * 0.05) for p in range(0, 4)])
    got = laps.split_laps(frames)
    # круги 1 и 4 неполные — их выбрасываем, иначе они портят сравнение
    assert [num for num, _ in got] == [2, 3]


def test_split_returns_empty_when_no_complete_lap():
    assert laps.split_laps([_frame(1, 0.5, 0.0), _frame(1, 0.6, 0.1)]) == []


def test_lap_time_from_frames():
    frames = _lap_frames(2, n=100, t0=10.0)          # 100 кадров по 0.05 c
    (num, fr), = laps.split_laps(frames)
    assert num == 2
    assert laps.lap_time(fr) == pytest.approx(100 * 0.05, abs=0.06)


# ── ресемпл на сетку дистанции ──────────────────────────────────────────────

def test_resample_gives_fixed_grid():
    fr = _lap_frames(2, n=137)                       # произвольное число кадров
    r = laps.resample(fr, points=100)
    assert len(r["speed"]) == 100
    assert set(laps.CHANNELS) <= set(r)


def test_resample_interpolates_between_frames():
    # скорость линейно растёт 0 -> 100 вдоль круга
    fr = _lap_frames(2, n=101, speed=lambda p: p * 100)
    r = laps.resample(fr, points=101)
    assert r["speed"][0] == pytest.approx(0.0, abs=1.0)
    assert r["speed"][50] == pytest.approx(50.0, abs=1.5)
    assert r["speed"][-1] == pytest.approx(100.0, abs=1.5)


def test_resample_survives_jitter_in_distance():
    # SDK иногда отдаёт долю дистанции с дрожанием назад — сортировка обязана
    # это пережить, иначе интерполяция даст пилу
    fr = _lap_frames(2, n=60)
    fr[30]["lap_dist_pct"] = fr[29]["lap_dist_pct"] - 0.001
    r = laps.resample(fr, points=50)
    assert len(r["speed"]) == 50
    assert all(math.isfinite(v) for v in r["speed"])


def test_resample_of_empty_is_empty():
    assert laps.resample([], points=10) == {}


# ── запись и чтение ─────────────────────────────────────────────────────────

def test_save_and_load_round_trip(tmp_path):
    fr = _lap_frames(2, n=120, speed=lambda p: 40 + p * 60)
    path = laps.save_lap(tmp_path, IDENT, 2, 93.5, fr)
    assert path is not None and path.exists()

    got = laps.load_lap(path)
    assert got["lap_time"] == 93.5
    assert got["track"] == "monza full" and got["car"] == "Porsche 963 GTP"
    assert len(got["channels"]["speed"]) == laps.POINTS
    # условия круга нужны, чтобы потом не сравнивать полный бак с пустым
    assert got["fuel_start"] == pytest.approx(60.0)
    assert got["track_temp"] == pytest.approx(31.0)
    assert got["session_type"] == "Practice"


def test_invalid_lap_is_not_written(tmp_path):
    fr = _lap_frames(2, n=120)
    # круг за 3 секунды — это заезд в боксы, а не круг
    assert laps.save_lap(tmp_path, IDENT, 2, 3.0, fr) is None
    assert list(tmp_path.rglob("*.json.gz")) == []


def test_list_laps_filters_by_track_and_car(tmp_path):
    fr = _lap_frames(2, n=80)
    laps.save_lap(tmp_path, IDENT, 2, 93.5, fr)
    laps.save_lap(tmp_path, {**IDENT, "car": "Ferrari 499P"}, 3, 121.9, fr)
    laps.save_lap(tmp_path, {**IDENT, "track": "spa 2024 up"}, 4, 121.0, fr)

    assert len(laps.list_laps(tmp_path)) == 3
    only = laps.list_laps(tmp_path, track="monza full", car="Porsche 963 GTP")
    assert len(only) == 1 and only[0]["lap_time"] == 93.5
    # список отсортирован от быстрого к медленному — эталон берётся сверху
    times = [m["lap_time"] for m in laps.list_laps(tmp_path, track="monza full")]
    assert times == sorted(times)


def test_list_laps_ignores_broken_files(tmp_path):
    laps.save_lap(tmp_path, IDENT, 2, 93.5, _lap_frames(2, n=80))
    (tmp_path / "monza full").mkdir(exist_ok=True)
    (tmp_path / "monza full" / "broken.json.gz").write_bytes(b"not gzip at all")
    # битый файл не должен ронять весь список
    assert len(laps.list_laps(tmp_path)) == 1
