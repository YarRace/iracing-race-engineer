"""Повороты, найденные по форме трассы.

Это НЕ официальная нумерация iRacing — её взять негде. Поэтому проверяется
не «совпало с телевизором», а то, что можно проверить: что круг без
поворотов не даёт ни одного, что прямая не считается поворотом, что
шикана не слипается в один и что подписи не ложатся на полотно и друг на
друга.

Порог сверен с настоящей ездой: по четырём официальным контурам детектор
находит 12–15 поворотов, а в его собственном круге по Ле-Ману участков с
рулём выше 6° после склейки — 14. Два независимых способа, одно число.
"""
import json
import math
import pathlib

import pytest
from conftest import CACHED_MAPS, make_circuit, needs_cached_maps

from ire.metrics import track_corners as tc

ROOT = pathlib.Path(__file__).resolve().parents[1]


def circle(n=120, r=40):
    """Ровная окружность: поворот один и тот же везде, «поворотов» нет."""
    return [{"x": 50 + r * math.cos(2 * math.pi * i / n),
             "y": 50 + r * math.sin(2 * math.pi * i / n),
             "pct": i / n} for i in range(n)]


def straight_with_one_corner():
    """Прямая, поворот на 90°, снова прямая."""
    pts = [{"x": 10 + i, "y": 10, "pct": i / 100} for i in range(40)]
    pts += [{"x": 50, "y": 10 + i, "pct": (40 + i) / 100} for i in range(1, 41)]
    return pts


def test_a_straight_is_not_a_corner():
    pts = [{"x": i, "y": 50, "pct": i / 100} for i in range(100)]
    assert tc.find(pts) == []


def test_one_ninety_degree_turn_is_found_once():
    got = tc.find(straight_with_one_corner())
    assert len(got) == 1
    assert got[0]["n"] == 1
    assert abs(abs(got[0]["angle"]) - 90) < 5


def test_a_perfect_circle_has_no_distinct_corners():
    """Ровная дуга — не поворот: там нечего называть «поворотом 3»."""
    got = tc.find(circle())
    assert len(got) <= 1, f"нашёл {len(got)} — окружность разбита на куски"


def test_a_chicane_is_two_corners_not_one():
    """Влево-вправо — два поворота. Слипшись, они прочитались бы как один."""
    pts = [{"x": i, "y": 50, "pct": i / 200} for i in range(30)]
    pts += [{"x": 30 + i, "y": 50 - i, "pct": (30 + i) / 200} for i in range(1, 26)]
    pts += [{"x": 55 + i, "y": 25, "pct": (55 + i) / 200} for i in range(1, 31)]
    got = tc.find(pts)
    assert len(got) == 2
    assert got[0]["dir"] != got[1]["dir"], "повороты в разные стороны"


def test_they_are_numbered_in_driving_order():
    got = tc.find(straight_with_one_corner() * 1)
    assert [c["n"] for c in got] == list(range(1, len(got) + 1))


def test_a_higher_threshold_finds_fewer_corners():
    pts = circle(120, 40)
    pts = straight_with_one_corner()
    assert len(tc.find(pts, 15)) >= len(tc.find(pts, 80))


def test_too_few_points_is_not_a_crash():
    assert tc.find([]) == []
    assert tc.find([{"x": 1, "y": 1, "pct": 0}]) == []
    assert tc.find(None) == []


def test_broken_points_are_skipped_not_guessed():
    pts = straight_with_one_corner() + [{"x": None, "y": 5, "pct": 0.9}]
    assert len(tc.find(pts)) == 1


@needs_cached_maps
@pytest.mark.parametrize("f", CACHED_MAPS or [None])
def test_real_tracks_land_in_the_range_the_steering_agrees_with(f):
    """12–15 поворотов на официальных контурах.

    Столько же участков с настоящим рулём в его круге по Ле-Ману (14).
    Если детектор начнёт находить тридцать или три — порог поехал.
    """
    d = json.loads(f.read_text(encoding="utf-8"))
    pts = d.get("points") if isinstance(d, dict) else d
    n = len(tc.find(pts))
    assert 8 <= n <= 20, f"{f.name}: {n} поворотов — это уже не похоже на трассу"


def test_a_label_never_sits_on_the_track():
    """Подпись поверх линии — это ровно то место, где едут машины."""
    pts = circle(120, 40)
    corner = {"x": 90.0, "y": 50.0}
    x, y = tc.outward(pts, corner, reach=8.0)
    near = min(math.hypot(p["x"] - x, p["y"] - y) for p in pts)
    assert near > 4.0, f"подпись в {near:.1f} от полотна"


def test_two_close_corners_get_labels_that_do_not_overlap():
    pts = circle(160, 40)
    corners = [{"x": 90.0, "y": 50.0}, {"x": 89.0, "y": 53.0}]
    (x1, y1), (x2, y2) = tc.place(pts, corners, reach=7.0, apart=9.0)
    assert math.hypot(x1 - x2, y1 - y2) >= 9.0


def test_a_circuit_with_a_known_number_of_corners_is_counted_right():
    """Настоящие карты есть не у всех, а проверить счёт надо везде.

    Раньше проверка стояла только на кэше из `data/`, а папка в .gitignore:
    на чистой копии тестов не оставалось ВОВСЕ — параметров ноль, пропуск
    молчаливый, и ноль тестов выглядел как ноль проблем.
    """
    for waves in (5, 8, 11):
        pts = make_circuit(corners=waves)
        got = tc.find(pts)
        assert len(got) == waves * 2, f"{waves} волн -> {len(got)} поворотов"
        # Повороты чередуются: выступ наружу, выступ внутрь.
        dirs = [c["dir"] for c in got]
        assert all(a != b for a, b in zip(dirs, dirs[1:])), dirs
