"""У поворотов должен быть ОДИН счёт, а не два.

Карта режет трассу по форме, разбор круга — по телеметрии (там, где машина
реально гружена вбок). Числа не обязаны совпадать, и пока они расходились,
«теряешь 0.3 с в седьмом» показывало на карте не тот поворот. Человек
поедет исправлять другое место — и это хуже, чем не сказать ничего.

Здесь проверяется связка: апекс сегмента получает номер поворота КАРТЫ,
через шов круга тоже, один номер уходит одному сегменту, а когда карты нет
или пара не нашлась — честный None вместо выдуманного номера.
"""
import json
import math
import pathlib

import pytest

from ire.metrics import corners as C
from ire.metrics import track_corners as tc

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _map():
    f = sorted((ROOT / "data" / "trackmaps").glob("official_v3_*.json"))[0]
    d = json.loads(f.read_text(encoding="utf-8"))
    return d.get("points") if isinstance(d, dict) else d


def test_an_apex_on_the_corner_gets_that_corner_number():
    pts = _map()
    cs = tc.find(pts)
    got = tc.match([c["pct"] for c in cs], cs)
    assert got == [c["n"] for c in cs]


def test_the_seam_of_the_lap_is_not_the_far_side_of_the_track():
    """0.999 и 0.001 — соседи. По прямой это «почти целый круг врозь»."""
    assert tc.match([0.999], [{"n": 1, "pct": 0.001}]) == [1]
    assert tc.match([0.001], [{"n": 9, "pct": 0.995}]) == [9]


def test_a_far_apex_gets_no_number_instead_of_the_nearest_one():
    """Соврать номером хуже, чем сказать «этот участок не отмечен»."""
    cs = [{"n": 1, "pct": 0.10}]
    assert tc.match([0.50], cs) == [None]


def test_one_number_goes_to_one_segment():
    """Иначе два соседних сегмента получают один номер, а средний — ничего."""
    cs = [{"n": 7, "pct": 0.300}]
    got = tc.match([0.2995, 0.3005], cs)
    # Какой из двух равноудалённых достанется — вопрос последних бит, и
    # закреплять это тестом значит проверять арифметику с плавающей точкой,
    # а не правило. Правило здесь одно: номер уходит РОВНО ОДНОМУ.
    assert sorted(got, key=lambda x: x is None) == [7, None]

    # А когда один явно ближе — он и выигрывает.
    assert tc.match([0.2990, 0.3001], cs) == [None, 7]


def test_without_a_map_nothing_is_invented():
    assert tc.match([0.2, 0.6], []) == [None, None]
    assert tc.match([0.2], None) == [None]


def test_a_broken_pct_does_not_crash_the_match():
    cs = tc.find(_map())
    assert tc.match([None, "x", cs[0]["pct"]], cs)[:2] == [None, None]


# --- связка в самом разборе ------------------------------------------------

def _lap(track="t", lap_time=100.0, shift=0.0):
    """Синтетический круг: скорость проваливается в тех же местах, что и
    повороты карты, — так апексы ложатся на них."""
    pts = _map()
    n = 1000
    cs = tc.find(pts)
    speed = [70.0] * n
    for c in cs:
        k = int(((c["pct"] + shift) % 1.0) * n)
        for j in range(-12, 13):
            speed[(k + j) % n] = 30.0 + abs(j) * 2.0
    return {"track": track, "car": "c", "lap_time": lap_time, "points": n,
            "channels": {"speed": speed, "throttle": [1.0] * n,
                         "brake": [0.0] * n, "lat": [0.0] * n}}


def test_the_analysis_labels_segments_with_the_map_numbers():
    mine, ref = _lap(lap_time=100.0), _lap(lap_time=100.0)
    r = C.analyse(mine, ref, _map())
    assert r["ok"], r.get("reason")
    turns = [s.get("turn") for s in r["segments"]]
    assert any(t is not None for t in turns), "ни один сегмент не связан с картой"
    named = [t for t in turns if t is not None]
    assert len(named) == len(set(named)), "один номер достался двум сегментам"


def test_without_a_map_the_segments_keep_their_own_numbers():
    mine, ref = _lap(), _lap()
    r = C.analyse(mine, ref)
    assert r["ok"]
    assert all(s.get("turn") is None for s in r["segments"])
    assert [s["index"] for s in r["segments"]] == list(
        range(1, len(r["segments"]) + 1))


def test_a_broken_map_does_not_break_the_numbers():
    """Карта — украшение разбора, а не его условие."""
    mine, ref = _lap(), _lap()
    r = C.analyse(mine, ref, [{"nonsense": 1}, {"nonsense": 2}])
    assert r["ok"]
    assert all(s.get("turn") is None for s in r["segments"])


def test_the_page_shows_the_map_number_when_there_is_one():
    html = (ROOT / "src" / "ire" / "dashboard" / "static" / "index.html").read_text(
        encoding="utf-8")
    assert "segName" in html and "segFull" in html
    # Без пары — номер сегмента, и это видно по знаку.
    assert "`#${s.index}`" in html
    assert "`T${s.turn}`" in html
