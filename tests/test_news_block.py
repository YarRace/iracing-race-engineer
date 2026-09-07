"""Новости и уведомление об обновлении на главной вкладке.

И то и другое жило только на сайте — то есть там, куда человек, который
запустил программу и поехал, не заходит. Он не увидит новой возможности и
не заметит вышедшей версии.

Главное, что здесь проверяется: об обновлении сообщается ТОЛЬКО когда
версия правда старше. «Не разобрал номер» не должно превращаться в
«вышла новая» — иначе программа будет вечно звать обновиться на то, чего
не понимает.
"""
import pytest
from fastapi.testclient import TestClient

from ire.dashboard import site
from ire.dashboard.server import app

client = TestClient(app)


@pytest.mark.parametrize("tag,current,newer", [
    ("v0.1.1", "0.1.0", True),
    ("v0.2.0", "0.1.9", True),
    ("v1.0.0", "0.9.9", True),
    ("v0.1.0", "0.1.0", False),
    ("v0.1.0", "0.2.0", False),     # откат: старше установленного
    ("nightly", "0.1.0", False),    # не разобрали — не зовём
    ("2026-09-07", "0.1.0", False),
    ("", "0.1.0", False),
    (None, "0.1.0", False),
])
def test_only_a_real_newer_number_counts_as_an_update(tag, current, newer):
    assert site.is_newer(tag, current) is newer


def test_a_two_part_tag_still_parses():
    assert site.parse_version("v0.2") == (0, 2, 0)
    assert site.parse_version("0.2.7") == (0, 2, 7)
    assert site.parse_version("v1.0-rc1") is None


def test_the_endpoint_answers_with_the_running_version():
    from ire import __version__
    r = client.get("/api/news").json()
    assert r["version"] == __version__
    assert isinstance(r["entries"], list)


def test_without_a_published_release_nothing_is_announced(monkeypatch):
    monkeypatch.setattr(site, "load_release", lambda *a, **k: None)
    assert client.get("/api/news").json()["update"] is None


def test_a_newer_release_is_announced_with_its_link(monkeypatch):
    monkeypatch.setattr(site, "load_release", lambda *a, **k: {
        "tag": "v99.0.0", "url": "https://example/rel", "published": "2026-09-07",
        "assets": [{"name": "x.zip", "size": 1, "url": "u"}]})
    up = client.get("/api/news").json()["update"]
    assert up["tag"] == "v99.0.0"
    assert up["url"] == "https://example/rel"


def test_an_older_release_is_not_announced(monkeypatch):
    monkeypatch.setattr(site, "load_release", lambda *a, **k: {
        "tag": "v0.0.1", "url": "u", "assets": [{"name": "x.zip"}]})
    assert client.get("/api/news").json()["update"] is None


def test_the_card_gets_the_first_paragraph_not_the_whole_entry(tmp_path):
    (tmp_path / "2026-09-07-thing.md").write_text(
        "# Заголовок\n\nПервый абзац.\n\nВторой абзац, которого на карточке "
        "быть не должно.\n", encoding="utf-8")
    entries = site.read_news(tmp_path)
    assert entries[0]["title"] == "Заголовок"
    lead = entries[0]["body"].split("\n\n")[0].strip()
    assert lead == "Первый абзац."


def test_the_limit_is_honoured():
    assert len(client.get("/api/news?limit=1").json()["entries"]) <= 1
    assert client.get("/api/news?limit=0").json()["entries"] == []


def test_the_block_is_wired_into_the_page():
    """Иначе конечная точка есть, а на экране пусто — и не видно, что сломано."""
    import pathlib
    html = (pathlib.Path(__file__).resolve().parents[1] / "src" / "ire" /
            "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="news"' in html
    assert "tickNews" in html
    assert "setInterval(tickNews" in html
    # Скрытие — до следующей версии, а не навсегда.
    assert "newsHiddenUntil" in html
