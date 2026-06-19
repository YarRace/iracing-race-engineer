from ire.collector.standings import build_standings


class _FakeIR:
    def __init__(self, d): self._d = d
    def __getitem__(self, k): return self._d[k]


def test_standings_merges_drivers_and_sorts_by_position():
    ir = _FakeIR({
        "DriverInfo": {"Drivers": [
            {"CarIdx": 0, "UserName": "Я Гонщик", "CarNumber": "64", "IRating": 2500,
             "LicString": "A 3.5", "CarScreenNameShort": "Cadillac", "CarClassColor": 0,
             "CarIsPaceCar": 0, "IsSpectator": 0},
            {"CarIdx": 1, "UserName": "Соперник", "CarNumber": "18", "IRating": 3100,
             "LicString": "A 4.2", "CarScreenNameShort": "BMW", "CarClassColor": 0,
             "CarIsPaceCar": 0, "IsSpectator": 0},
            {"CarIdx": 2, "UserName": "Пейс", "CarNumber": "0", "CarIsPaceCar": 1, "IsSpectator": 0},
        ]},
        "CarIdxPosition": [2, 1, 0, 0],
        "CarIdxF2Time": [8.9, 0.0, 0.0, 0.0],
        "CarIdxLastLapTime": [95.3, 94.1, -1.0, -1.0],
        "CarIdxBestLapTime": [94.8, 93.9, -1.0, -1.0],
        "CarIdxLap": [18, 18, -1, -1],
        "CarIdxOnPitRoad": [False, False, False, False],
    })
    rows = build_standings(ir)
    assert len(rows) == 2                         # пейс-кар исключён
    assert rows[0]["pos"] == 1 and rows[0]["name"] == "Соперник"   # сортировка по позиции
    assert rows[1]["pos"] == 2 and rows[1]["number"] == "64"
    assert rows[0]["best"] == 93.9 and rows[1]["gap"] == 8.9
    assert rows[0]["irating"] == 3100
