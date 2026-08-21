"""Устойчивость привязки машин к карте (TrackMapWidget._on_track).

Баг был: клипало по pts[0]/pts[-1] и линейный поиск на несортированных точках —
машины сваливались в одну точку / порядок ломался, игрока не видно. Проверяем,
что теперь на шве старт/финиш и в середине круга позиции корректны и различаются.
"""
from overlay.widgets import TrackMapWidget


def _pts(seq):
    return [{"pct": p, "x": x, "y": y} for p, x, y in seq]


def test_seam_not_clamped_to_start():
    # квадрат по кругу; шов между pct 0.9 и 0.1
    s = _pts([(0.1, 0, 0), (0.4, 100, 0), (0.6, 100, 100), (0.9, 0, 100)])
    p0 = TrackMapWidget._on_track(0.0, s)          # доля 0.0 — в шве старт/финиш
    assert p0 != (0.0, 0.0)                        # НЕ свалилось в первую точку
    assert abs(p0[1] - 50.0) < 1e-6               # ровно между (0,100) и (0,0)


def test_order_preserved_distinct_positions():
    s = _pts([(0.1, 0, 0), (0.4, 100, 0), (0.6, 100, 100), (0.9, 0, 100)])
    a = TrackMapWidget._on_track(0.25, s)
    b = TrackMapWidget._on_track(0.55, s)
    c = TrackMapWidget._on_track(0.85, s)
    assert a != b != c and a != c                 # разные доли круга → разные точки


def test_midsegment_interpolation():
    s = _pts([(0.0, 0, 0), (0.5, 100, 0), (0.99, 100, 100)])
    x, y = TrackMapWidget._on_track(0.25, s)       # середина сегмента (0,0)->(100,0)
    assert abs(x - 50.0) < 1e-6 and abs(y - 0.0) < 1e-6


def test_pct_wraps_and_empty_safe():
    s = _pts([(0.2, 10, 10), (0.8, 90, 90)])
    assert TrackMapWidget._on_track(1.25, s) == TrackMapWidget._on_track(0.25, s)  # pct по модулю
    assert TrackMapWidget._on_track(0.5, []) == (50.0, 50.0)                       # пустая карта — не падаем
