"""Разбор круга по поворотам.

Вкладка «Time lost» резала круг на три сектора iRacing. Три на круг — это
слишком крупно: «потерял 0.4 в первом секторе» не говорит, в каком повороте
и что было не так.

Проверяем на СИНТЕТИЧЕСКИХ кругах, а не на записанных: чтобы утверждать
«потеря именно в третьем повороте», надо самому положить её туда. На живом
круге правильный ответ неизвестен, и тест превращается в «не упало».
"""
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire.metrics import corners                                  # noqa: E402

N = 400


def make_lap(apex_speeds=(30.0, 45.0, 25.0), top=80.0, points=N,
             brake_shift=0, throttle_shift=0, apex_scale=1.0):
    """Круг с заданными поворотами: разгон — торможение — апекс — разгон.

    apex_scale < 1 делает апексы медленнее (потеря в середине поворота),
    brake_shift сдвигает точку торможения (раньше = отрицательный),
    throttle_shift — момент возврата на газ.
    """
    k = len(apex_speeds)
    seg = points // k
    speed, throttle, brake, lat = [], [], [], []
    for i in range(points):
        s = min(i // seg, k - 1)
        u = (i - s * seg) / seg                       # 0..1 внутри сегмента
        apex = apex_speeds[s] * apex_scale
        # колокол наоборот: быстро в начале и конце, медленно в середине
        shape = 1.0 - math.exp(-((u - 0.5) ** 2) / 0.02)
        v = apex + (top - apex) * shape
        speed.append(v)
        lat.append((top - v) * 0.8)                   # грузим вбок в повороте
        pos = (i - s * seg)
        b_from = seg * 0.28 + brake_shift
        t_from = seg * 0.62 + throttle_shift
        brake.append(1.0 if b_from <= pos < seg * 0.48 else 0.0)
        throttle.append(1.0 if pos >= t_from or pos < b_from else 0.0)

    lap_time = sum(1.0 / max(v, 1.0) for v in speed) * 10.0
    return {
        "track": "test", "track_display": "Test", "car": "Test GT3",
        "lap_time": lap_time, "points": points,
        "channels": {"speed": speed, "throttle": throttle, "brake": brake,
                     "steer": [0.0] * points, "gear": [4] * points,
                     "lat_accel": lat, "long_accel": [0.0] * points,
                     "yaw_rate": [0.0] * points},
    }


# ── нарезка ─────────────────────────────────────────────────────────────────

def test_segments_tile_the_whole_lap():
    """Дырки между сегментами — это потерянное время, которое нигде не видно,
    а нахлёст — время, посчитанное дважды. Сумма перестаёт сходиться, и
    таблица выглядит сломанной."""
    segs = corners.segments(make_lap()["channels"], N)
    assert segs[0]["start"] == 0
    assert segs[-1]["end"] == N
    for a, b in zip(segs, segs[1:]):
        assert a["end"] == b["start"], "сегменты не стыкуются"


def test_one_segment_per_corner():
    for k in (2, 3, 5):
        lap = make_lap(apex_speeds=tuple(25.0 + 7 * i for i in range(k)))
        assert len(corners.segments(lap["channels"], N)) == k


def test_apex_is_the_slowest_point_of_its_segment():
    lap = make_lap()
    v = lap["channels"]["speed"]
    for s in corners.segments(lap["channels"], N):
        inside = v[s["start"]:s["end"]]
        assert abs(v[s["apex"]] - min(inside)) < 1e-6


def test_detection_does_not_wobble_with_the_threshold():
    """Первая версия искала повороты по |lat_accel|, и сдвиг порога с 0.25
    на 0.28 менял разбивку Road Atlanta с пяти сегментов на шесть. Разбор,
    который скачет от настроечного числа, доверия не вызывает."""
    lap = make_lap()
    counts = set()
    original = corners.MIN_PROMINENCE
    try:
        for prom in (0.04, 0.06, 0.08, 0.12):
            corners.MIN_PROMINENCE = prom
            counts.add(len(corners.segments(lap["channels"], N)))
    finally:
        corners.MIN_PROMINENCE = original
    assert len(counts) == 1, f"разбивка гуляет: {counts}"


def test_a_lap_behind_the_safety_car_has_no_corners():
    """Ровная скорость — размах меньше порога, поворотов нет. Раньше такой
    круг дал бы сотню «поворотов» из шума."""
    flat = {"speed": [30.0] * N, "lat_accel": [0.0] * N}
    assert corners.find_corners(flat, N) == []


# ── сравнение ───────────────────────────────────────────────────────────────

def test_a_lap_against_itself_is_all_zeros():
    lap = make_lap()
    r = corners.analyse(lap, lap)
    assert r["ok"]
    assert abs(r["delta"]) < 1e-9
    assert abs(r["trace"][-1]) < 1e-6
    for s in r["segments"]:
        assert abs(s["loss"]) < 0.01
        assert s["phase"] == "none"


def test_segment_losses_add_up_to_the_lap_delta():
    """Если сумма по таблице не сходится с разницей в шапке, не верят всей
    таблице — даже когда каждая строка по отдельности верна."""
    ref = make_lap()
    slow = make_lap(apex_scale=0.9)
    r = corners.analyse(slow, ref)
    assert r["delta"] > 0
    assert abs(sum(s["loss"] for s in r["segments"]) - r["delta"]) < 0.02


def test_the_loss_lands_in_the_corner_where_it_was_made():
    """Смысл всего разбора: сказать НОМЕР поворота, а не «где-то в секторе»."""
    ref = make_lap(apex_speeds=(30.0, 45.0, 25.0))
    slow = make_lap(apex_speeds=(30.0, 45.0, 18.0))      # медленнее ТОЛЬКО в 3-м
    r = corners.analyse(slow, ref)
    worst = max(r["segments"], key=lambda s: s["loss"])
    assert worst["index"] == 3
    assert worst["loss"] > sum(s["loss"] for s in r["segments"][:2])


def test_being_quicker_is_reported_as_a_gain_not_a_loss():
    ref = make_lap(apex_scale=0.9)
    fast = make_lap()
    r = corners.analyse(fast, ref)
    assert r["delta"] < 0
    assert any(s["phase"] == "gain" for s in r["segments"])


# ── вердикт ─────────────────────────────────────────────────────────────────

def test_lower_apex_speed_is_called_out_as_the_apex():
    ref = make_lap(apex_speeds=(30.0, 30.0, 30.0))
    slow = make_lap(apex_speeds=(30.0, 22.0, 30.0))
    r = corners.analyse(slow, ref)
    seg = r["segments"][1]
    assert seg["phase"] == "apex"
    assert "minimum speed" in seg["text"]
    assert "km/h" in seg["text"]


def test_verdict_never_promises_a_racing_line():
    """Lat/Lon в кадре круга не пишутся. Обещать сравнение траекторий —
    выдумывать то, чего в данных нет."""
    ref = make_lap()
    slow = make_lap(apex_scale=0.92)
    r = corners.analyse(slow, ref)
    for s in r["segments"]:
        low = s["text"].lower()
        assert "line" not in low and "racing line" not in low


# ── защита от бессмысленных сравнений ───────────────────────────────────────

def test_two_different_tracks_are_refused():
    """Сравнить Спа с Монцей нельзя, а молча выдать числа — хуже отказа."""
    a, b = make_lap(), make_lap()
    b["track"] = "monza full"
    r = corners.analyse(a, b)
    assert not r["ok"] and "different tracks" in r["reason"]


def test_a_lap_without_telemetry_is_refused():
    lap = make_lap()
    assert not corners.analyse(lap, {"track": "test", "channels": {}})["ok"]
    assert not corners.analyse({}, lap)["ok"]


def test_zero_speed_does_not_divide_by_zero():
    """Кадры на пит-лейне и на старте дают ноль скорости."""
    lap = make_lap()
    lap["channels"]["speed"][10:20] = [0.0] * 10
    r = corners.analyse(lap, make_lap())
    assert r["ok"]
    assert all(math.isfinite(v) for v in r["trace"])


# ── выбор эталона ───────────────────────────────────────────────────────────

def test_reference_is_the_best_lap_on_the_same_track_and_car():
    """На той же МАШИНЕ обязательно: круг GTP не эталон для GT3, разница
    в двадцать секунд превратит разбор в шум."""
    me = {"track": "spa", "car": "GT3", "lap_time": 140.0, "path": "me"}
    pool = [
        {"track": "spa", "car": "GT3", "lap_time": 138.0, "path": "good"},
        {"track": "spa", "car": "GT3", "lap_time": 139.0, "path": "ok"},
        {"track": "spa", "car": "GTP", "lap_time": 130.0, "path": "wrong car"},
        {"track": "monza", "car": "GT3", "lap_time": 100.0, "path": "wrong track"},
        me,
    ]
    assert corners.pick_reference(pool, me)["path"] == "good"


def test_no_reference_when_there_is_nothing_to_compare_with():
    me = {"track": "spa", "car": "GT3", "lap_time": 140.0, "path": "me"}
    assert corners.pick_reference([me], me) is None
    assert corners.pick_reference([], me) is None


# ── на живом круге ──────────────────────────────────────────────────────────

def test_it_survives_a_real_recorded_lap():
    """Синтетика проверяет логику, живой круг — что она переживает
    настоящий шум телеметрии."""
    from ire.storage import laps
    files = sorted(laps.default_root().rglob("*.json.gz"))
    if not files:
        pytest.skip("сохранённых кругов нет")
    lap = laps.load_lap(files[-1])
    segs = corners.segments(lap["channels"], lap["points"])
    assert 2 <= len(segs) <= 25, f"неправдоподобное число поворотов: {len(segs)}"
    r = corners.analyse(lap, lap)
    assert r["ok"] and abs(r["trace"][-1]) < 1e-6
