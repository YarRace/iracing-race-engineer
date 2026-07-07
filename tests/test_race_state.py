from ire.collector.race_state import (decode_flags, decode_warnings, _relative,
                                       _standing_gaps, build_relative)


def test_decode_flags_picks_active():
    assert decode_flags(0) == []
    # зелёный (0x4) + синий (0x20)
    keys = [f["key"] for f in decode_flags(0x4 | 0x20)]
    assert "green" in keys and "blue" in keys
    # клетчатый
    assert any(f["key"] == "checkered" for f in decode_flags(0x1))


def test_decode_warnings_picks_active():
    assert decode_warnings(0) == []
    # перегрев воды (0x1) + отсечка (0x20)
    keys = [w["key"] for w in decode_warnings(0x1 | 0x20)]
    assert "water" in keys and "rev_limiter" in keys
    # пит-лимитер
    assert any(w["key"] == "pit_limiter" for w in decode_warnings(0x10))


class _FakeIR:
    def __init__(self, d): self._d = d
    def __getitem__(self, k): return self._d[k]


def test_relative_picks_nearest_on_track_skips_pit():
    # я — idx 0 на 0.50 круга, круг 100с. Машины: idx1 впереди 0.05(=5с),
    # idx3 в боксе (пропустить), idx4 впереди ближе 0.02(=2с), idx2 сзади 0.05(=5с)
    ir = _FakeIR({
        "DriverInfo": {"DriverCarIdx": 0},
        "CarIdxLapDistPct": [0.50, 0.55, 0.45, 0.60, 0.52, -1.0],
        "CarIdxOnPitRoad": [False, False, False, True, False, False],
        "CarIdxTrackSurface": [3, 3, 3, 1, 3, -1],
        "LapBestLapTime": 100.0, "LapLastLapTime": 0.0,
    })
    ahead, behind = _relative(ir)
    assert ahead == 2.0      # ближайшая впереди — idx4 (0.02*100)
    assert behind == 5.0     # сзади — idx2 (0.05*100)


def test_standing_gaps_by_position():
    # я P6 (idx0), F2 100с. P5 (idx1) F2 92с → впереди 8с; P7 (idx2) F2 105с → сзади 5с
    ir = _FakeIR({
        "DriverInfo": {"DriverCarIdx": 0},
        "CarIdxPosition": [6, 5, 7, 0, 0, 0],
        "CarIdxF2Time": [100.0, 92.0, 105.0, 0.0, 0.0, 0.0],
    })
    ahead, behind = _standing_gaps(ir)
    assert ahead == 8.0
    assert behind == 5.0


def test_build_relative_orders_by_track_position():
    # я idx0 на 0.50; idx1 впереди (+0.05=5с), idx2 сзади (−0.05), idx3 не в мире (искл.)
    ir = _FakeIR({
        "DriverInfo": {"DriverCarIdx": 0, "Drivers": [
            {"CarIdx": 0, "UserName": "Me", "CarClassShortName": "GTP", "IRating": 3000},
            {"CarIdx": 1, "UserName": "Ahead", "CarClassShortName": "GTP", "IRating": 4000},
            {"CarIdx": 2, "UserName": "Behind", "CarClassShortName": "GTP", "IRating": 2000},
            {"CarIdx": 3, "UserName": "Garage", "CarClassShortName": "GTP", "IRating": 2500},
        ]},
        "CarIdxLapDistPct": [0.50, 0.55, 0.45, 0.60],
        "CarIdxOnPitRoad": [False, False, False, False],
        "CarIdxTrackSurface": [3, 3, 3, -1],
        "CarIdxPosition": [2, 1, 3, 4],
        "LapBestLapTime": 100.0, "LapLastLapTime": 0.0,
    })
    rel = build_relative(ir)
    cars = rel["cars"]
    assert all(c["idx"] != 3 for c in cars)              # вне мира исключён
    assert [c["idx"] for c in cars] == [2, 0, 1]         # сзади → я → впереди
    ahead = next(c for c in cars if c["idx"] == 1)
    assert ahead["gap"] == 5.0 and ahead["name"] == "Ahead"
    assert rel["player_pct"] == 0.5
