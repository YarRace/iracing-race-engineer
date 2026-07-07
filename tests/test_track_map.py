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
