import math

from ire.collector.track_map import TrackMapBuilder, normalize_path, save_map, load_map


def test_normalize_path_fits_box():
    pts = [(0.0, 0.0, 0.0), (0.5, 1000.0, 0.0), (0.9, 1000.0, 500.0)]
    out = normalize_path(pts)
    assert all(0 <= p["x"] <= 100 and 0 <= p["y"] <= 100 for p in out)
    assert out[0]["pct"] <= out[-1]["pct"]              # отсортировано по pct


def test_builder_makes_shape_from_a_lap():
    b = TrackMapBuilder()
    n = 120
    omega = 2 * math.pi / (n * 0.1)                     # полный оборот за круг
    for i in range(n):
        b.update(pct=i / n, speed=50.0, yaw_rate=omega, t=i * 0.1)
    b.update(pct=0.01, speed=50.0, yaw_rate=omega, t=n * 0.1)   # wrap → финализ
    snap = b.snapshot()
    assert snap is not None
    pts = snap["points"]
    assert len(pts) >= 50
    assert all(0 <= p["x"] <= 100 and 0 <= p["y"] <= 100 for p in pts)
    assert pts[0]["pct"] < pts[-1]["pct"]


def test_builder_ignores_short_junk_lap():
    b = TrackMapBuilder()
    for i in range(5):                                  # слишком мало точек
        b.update(pct=i / 5, speed=50.0, yaw_rate=0.1, t=i * 0.1)
    b.update(pct=0.0, speed=50.0, yaw_rate=0.1, t=1.0)
    assert b.snapshot() is None


def test_save_and_load_map_roundtrip(tmp_path):
    import os
    os.environ["IRE_DB_PATH"] = str(tmp_path / "h.db")
    try:
        pts = [{"pct": 0.0, "x": 10.0, "y": 10.0}, {"pct": 0.5, "x": 90.0, "y": 50.0}]
        save_map("Watkins Glen Boot", pts)
        assert load_map("Watkins Glen Boot") == pts
        assert load_map("unknown track") is None
    finally:
        del os.environ["IRE_DB_PATH"]


# ── карта из настоящих координат ────────────────────────────────────────────

def test_map_from_coordinates_closes_on_itself():
    """Своя карта строится интегрированием скорости и рыскания и копит
    ошибку: к концу круга контур не сходится сам с собой. Координаты дают
    форму такой, какая трасса есть, — и начало обязано встретиться с концом.
    """
    import math
    from ire.collector import track_map as tm

    # окружность в градусах широты и долготы — модель кольцевой трассы
    shape = [(i / 400, 34.15 + 0.01 * math.cos(2 * math.pi * i / 400),
              -83.81 + 0.012 * math.sin(2 * math.pi * i / 400))
             for i in range(400)]
    path = tm.from_latlon(shape)
    assert path and len(path) == 240
    dx = path[0]["x"] - path[-1]["x"]
    dy = path[0]["y"] - path[-1]["y"]
    assert math.hypot(dx, dy) < 3.0, "контур не замкнулся"


def test_coordinates_are_scaled_into_the_box():
    from ire.collector import track_map as tm
    shape = [(i / 100, 34.0 + i * 0.0002, -83.0 + i * 0.0005) for i in range(100)]
    path = tm.from_latlon(shape)
    assert all(0 <= p["x"] <= 100 and 0 <= p["y"] <= 100 for p in path)
    assert all(0.0 <= p["pct"] <= 1.0 for p in path)


def test_empty_gps_points_are_dropped_not_drawn():
    """Пропуск в записи приходит нулями. Нарисовать (0,0) значит протянуть
    линию через Атлантику — карта складывается в точку."""
    from ire.collector import track_map as tm
    shape = [(i / 60, 34.0 + i * 0.001, -83.0 + i * 0.001) for i in range(60)]
    shape[30] = (0.5, 0.0, 0.0)
    path = tm.from_latlon(shape)
    assert path
    xs = [p["x"] for p in path]
    assert max(xs) - min(xs) > 10, "карта схлопнулась из-за нулевой точки"


def test_too_few_points_is_no_map_rather_than_a_wrong_one():
    from ire.collector import track_map as tm
    assert tm.from_latlon([]) is None
    assert tm.from_latlon([(0.1, 34.0, -83.0), (0.2, 34.1, -83.1)]) is None


def test_garage61_map_failure_is_silent():
    """Сеть может отвалиться. Ронять живой цикл из-за карты нельзя."""
    from ire.collector import track_map as tm
    assert tm.from_garage61("несуществующая трасса", "нет такой машины") is None
