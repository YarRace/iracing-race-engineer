"""Номера поворотов на карте дашборда — те же, что в оверлее.

Детектор ОДИН и живёт в Python: переписать его на JS значит завести
вторую версию, которая через месяц начнёт находить другое. Поэтому
повороты приезжают вместе с картой, а страница их только рисует.
"""
import pathlib

import pytest
from conftest import make_circuit
from fastapi.testclient import TestClient

import ire.dashboard.server as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
client = TestClient(S.app)


def _map():
    """Своя трасса: data/trackmaps в .gitignore, на чистой копии её нет."""
    return make_circuit(corners=8)


@pytest.fixture(autouse=True)
def _clean():
    before = S.STATE.get("trackmap")
    S._CORNERS_CACHE.clear()
    yield
    S.STATE["trackmap"] = before
    S._CORNERS_CACHE.clear()


def test_an_empty_map_answers_without_corners():
    """До первого круга карты нет — и выдумывать повороты не из чего."""
    S.STATE["trackmap"] = {}
    assert "corners" not in client.get("/api/trackmap").json()


def test_a_real_map_comes_with_numbered_turns():
    S.STATE["trackmap"] = {"points": _map(), "track": "T", "source": "official"}
    corners = client.get("/api/trackmap").json()["corners"]
    assert len(corners) == 16, "восемь волн — шестнадцать поворотов"
    assert [c["n"] for c in corners] == list(range(1, len(corners) + 1))
    for c in corners:
        assert 0.0 <= c["pct"] <= 1.0
        # lx/ly — куда положить подпись, а не сам поворот.
        assert "lx" in c and "ly" in c


def test_the_labels_are_placed_away_from_the_track():
    import math

    pts = _map()
    S.STATE["trackmap"] = {"points": pts, "track": "T", "source": "official"}
    for c in client.get("/api/trackmap").json()["corners"]:
        near = min(math.hypot(p["x"] - c["lx"], p["y"] - c["ly"]) for p in pts)
        assert near > 2.0, f"подпись {c['n']} лежит на полотне"


def test_the_answer_is_cached_between_calls():
    """Страница спрашивает карту раз в три секунды, а карта за сессию не меняется."""
    S.STATE["trackmap"] = {"points": _map(), "track": "T", "source": "official"}
    client.get("/api/trackmap")
    assert len(S._CORNERS_CACHE) == 1
    client.get("/api/trackmap")
    assert len(S._CORNERS_CACHE) == 1, "пересчитывает на каждый запрос"


def test_a_new_track_replaces_the_cached_one():
    pts = _map()
    S.STATE["trackmap"] = {"points": pts, "track": "A", "source": "official"}
    client.get("/api/trackmap")
    S.STATE["trackmap"] = {"points": pts, "track": "B", "source": "official"}
    client.get("/api/trackmap")
    assert len(S._CORNERS_CACHE) == 1, "старая трасса осталась в памяти"


def test_the_page_draws_them_and_says_what_they_are():
    html = (ROOT / "src" / "ire" / "dashboard" / "static" / "index.html").read_text(
        encoding="utf-8")
    assert "_trackCorners" in html
    # Честность прямо на карточке: это не нумерация iRacing.
    assert "not iRacing numbering" in html
    # Выключается, и выбор переживает перезагрузку страницы.
    assert "turnsOn" in html and "showTurns" in html
    # Поле вокруг карты: подписи выходят за контур и обрезались бы.
    assert 'viewBox="-8 -8 116 116"' in html
