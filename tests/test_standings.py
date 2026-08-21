from ire.collector.standings import (build_standings, cars_in_class, fmt_gap,
                                     manufacturer_of, parse_license, predict_ir_changes,
                                     strength_of_field)


class _FakeIR:
    def __init__(self, d): self._d = d
    def __getitem__(self, k): return self._d.get(k)   # как pyirsdk: нет канала → None


def _ir(**over):
    """Практика: я (CarIdx 0) второй, соперник лидер, оба в GTP, пейс-кар лишний."""
    d = {
        "DriverInfo": {"DriverCarIdx": 0, "Drivers": [
            {"CarIdx": 0, "UserName": "Я Гонщик", "CarNumber": "64", "IRating": 2500,
             "LicString": "A 3.5", "CarScreenNameShort": "Cadillac", "CarClassShortName": "GTP",
             "CarClassColor": 0, "CarIsPaceCar": 0, "IsSpectator": 0},
            {"CarIdx": 1, "UserName": "Соперник", "CarNumber": "18", "IRating": 3100,
             "LicString": "B 4.2", "CarScreenNameShort": "BMW", "CarClassShortName": "GTP",
             "CarClassColor": 0, "CarIsPaceCar": 0, "IsSpectator": 0},
            {"CarIdx": 2, "UserName": "Пейс", "CarNumber": "0", "CarIsPaceCar": 1, "IsSpectator": 0},
        ]},
        "CarIdxPosition": [2, 1, 0, 0],
        "CarIdxF2Time": [8.9, 0.0, 0.0, 0.0],
        "CarIdxLastLapTime": [95.3, 94.1, -1.0, -1.0],
        "CarIdxBestLapTime": [94.8, 93.9, -1.0, -1.0],
        "CarIdxLap": [18, 18, -1, -1],
        "CarIdxLapCompleted": [18, 18, -1, -1],
        "CarIdxLapDistPct": [0.4, 0.5, -1, -1],
        "CarIdxTrackSurface": [3, 3, 3, 3],
        "CarIdxOnPitRoad": [False, False, False, False],
    }
    d.update(over)
    return _FakeIR(d)


def _me(rows):
    return [r for r in rows if r["is_player"]][0]


def test_standings_merges_drivers_and_sorts_by_position():
    rows = build_standings(_ir())
    assert len(rows) == 2                         # пейс-кар исключён
    assert rows[0]["pos"] == 1 and rows[0]["name"] == "Соперник"   # сортировка по позиции
    assert rows[1]["pos"] == 2 and rows[1]["number"] == "64"
    assert rows[0]["best"] == 93.9 and rows[1]["gap"] == 8.9
    assert rows[0]["irating"] == 3100


def test_license_letter_and_rating_with_iracing_color():
    rows = build_standings(_ir())
    assert rows[0]["lic"] == "B" and rows[0]["sr"] == 4.2
    assert rows[0]["lic_color"] == "#1f9e4a"      # B — зелёная
    assert rows[1]["lic"] == "A" and rows[1]["lic_color"] == "#3e7bfa"   # A — синяя


def test_parse_license_survives_junk():
    assert parse_license("A 4.99") == ("A", 4.99)
    assert parse_license("R 2.50") == ("R", 2.5)
    assert parse_license("") == (None, None)
    assert parse_license(None) == (None, None)
    assert parse_license("Rookie") == (None, None)


def test_gap_text_leader_and_seconds():
    rows = build_standings(_ir())
    assert rows[0]["gap_txt"] == "leader"
    assert rows[1]["gap_txt"] == "+8.9"


def test_fmt_gap_cascades_thousandths_seconds_minutes_laps():
    assert fmt_gap(0, leader=True) == "leader"
    assert fmt_gap(0.312) == "+0.312"             # ближний бой — тысячные
    assert fmt_gap(12.44) == "+12.4"
    assert fmt_gap(62.5) == "+1:02.5"             # за 60 сек начинаются минуты
    assert fmt_gap(198.5) == "+3:18.5"
    assert fmt_gap(751.5, laps_down=6) == "+6L"   # круг важнее «+751.5»
    assert fmt_gap(None) == "—"


def test_laps_down_in_race_beats_seconds():
    rows = build_standings(_ir(**{
        "SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionType": "Race"}]},
        "SessionNum": 0,
        "CarIdxLapCompleted": [16, 18, -1, -1],   # я на 2 круга позади лидера
    }))
    assert _me(rows)["laps_down"] == 2 and _me(rows)["gap_txt"] == "+2L"


def test_no_laps_down_outside_race():
    # в практике все катают разное число кругов — «+2L» там был бы бессмыслицей
    rows = build_standings(_ir(**{"CarIdxLapCompleted": [16, 18, -1, -1]}))
    assert _me(rows)["laps_down"] == 0 and _me(rows)["gap_txt"] == "+8.9"


def test_out_flag_when_car_left_the_world():
    rows = build_standings(_ir(**{"CarIdxTrackSurface": [-1, 3, 3, 3]}))
    assert _me(rows)["out"] is True
    assert build_standings(_ir())[0]["out"] is False


def test_cars_in_class_skips_other_classes_and_retired():
    rows = [
        {"is_player": True, "car_class": "GTP", "out": False},
        {"is_player": False, "car_class": "GTP", "out": False},
        {"is_player": False, "car_class": "GTP", "out": True},    # сошёл — не считаем
        {"is_player": False, "car_class": "GT3", "out": False},   # чужой класс
    ]
    assert cars_in_class(rows) == 2


def test_strength_of_field_uses_iracing_formula():
    assert strength_of_field([2000, 2000, 2000]) == 2000          # равные → ровно этот рейтинг
    field = [4000, 1000, 1000, 1000]                              # слабые тянут вниз сильнее,
    assert strength_of_field(field) < sum(field) / len(field)     # чем среднее арифметическое
    assert strength_of_field([]) is None


def test_manufacturer_from_car_path_and_name():
    assert manufacturer_of("porsche992rgt3") == "porsche"
    assert manufacturer_of("cadillacvseriesrgtp") == "cadillac"
    assert manufacturer_of("chevroletvettez06rgt3") == "chevrolet"
    assert manufacturer_of("mercedesamgevogt3") == "mercedes"     # алиас amg→mercedes
    assert manufacturer_of("corvettec8gt3") == "chevrolet"        # алиас corvette→chevrolet
    assert manufacturer_of(None, "Ford GT GT3") == "ford"         # Ford (была дыра)
    assert manufacturer_of(None, "BMW M4 GT3") == "bmw"           # из имени, если нет CarPath
    assert manufacturer_of("spaceshipxyz") is None


def test_predict_ir_gain_sign_and_none_outside_race():
    # слабый лидирует → плюс; сильный последний → минус (внутри своего класса)
    rows = [{"irating": 1000, "car_class": "GTP", "pos": 1},
            {"irating": 2000, "car_class": "GTP", "pos": 2},
            {"irating": 3000, "car_class": "GTP", "pos": 3}]
    predict_ir_changes(rows, True)
    weak = [r for r in rows if r["irating"] == 1000][0]
    strong = [r for r in rows if r["irating"] == 3000][0]
    assert weak["ir_gain"] > 0 and strong["ir_gain"] < 0
    assert all(isinstance(r["ir_gain"], int) for r in rows)
    # вне гонки прогноза нет
    r2 = [{"irating": 2000, "car_class": "GTP", "pos": 1}]
    predict_ir_changes(r2, False)
    assert r2[0]["ir_gain"] is None


def test_predict_ir_gain_per_class_independent():
    # два класса считаются отдельно; одиночка в классе → 0
    rows = [{"irating": 2000, "car_class": "GTP", "pos": 1},
            {"irating": 2200, "car_class": "GT3", "pos": 2},
            {"irating": 1800, "car_class": "GT3", "pos": 3}]
    predict_ir_changes(rows, True)
    assert rows[0]["ir_gain"] == 0                                # один в классе GTP
    assert isinstance(rows[1]["ir_gain"], int)


def test_build_standings_adds_manufacturer_and_ir_gain_field():
    rows = build_standings(_ir())                                 # практика (не гонка)
    assert rows[0]["manufacturer"] == "bmw"                       # соперник — BMW
    assert all("ir_gain" in r for r in rows)
    assert rows[0]["ir_gain"] is None                             # вне гонки — None
