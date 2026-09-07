"""Страница Get it: ссылка на скачивание появляется, только когда есть что.

Кнопка над несуществующим файлом хуже четырёх честных команд — по ней
человек уходит с 404 и не возвращается. Поэтому здесь проверяется ровно
граница: когда ссылка есть и когда её нет.
"""
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from ire.dashboard import site                                   # noqa: E402
import fetch_release                                             # noqa: E402

REL = {
    "tag": "v0.1.1",
    "url": "https://github.com/YarRace/iracing-race-engineer/releases/v0.1.1",
    "published": "2026-09-07",
    "assets": [
        {"name": "RaceEngineer.zip", "size": 188 * 1048576, "url": "https://x/1"},
        {"name": "RaceEngineerLauncher.zip", "size": 41 * 1048576, "url": "https://x/2"},
        {"name": "RaceEngineerOverlay.zip", "size": 96 * 1048576, "url": "https://x/3"},
    ],
}


def _page(rel):
    return site.page_download(site.load_catalog(), [], rel)


def test_without_a_release_the_page_says_so_and_offers_the_commands():
    html = _page(None)
    assert "There is no download link here on" in html
    assert 'class="dl"' not in html
    assert "pre class=" in html, "четыре команды должны остаться"


def test_with_a_release_every_archive_gets_a_link():
    html = _page(REL)
    for a in REL["assets"]:
        assert a["url"] in html, a["name"]
        assert a["name"] in html
    assert "There is no download link here on" not in html
    assert "v0.1.1" in html


def test_the_launcher_comes_first():
    """Три архива без порядка — это выбор вслепую. Начинают с лаунчера."""
    html = _page(REL)
    assert html.index("Start here") < html.index("The overlay")
    assert html.index("The overlay") < html.index("The engineer")


def test_the_size_is_shown_in_megabytes():
    html = _page(REL)
    assert "188 MB" in html and "41 MB" in html


def test_the_commands_survive_next_to_the_download():
    """Сборка из исходников остаётся: не у всех есть желание качать 300 МБ."""
    html = _page(REL)
    assert "Or run it from source" in html
    assert "git clone" in html
    assert "{steps}" not in html, "шаблон не подставился"


@pytest.mark.parametrize("rel", [
    {},
    {"tag": "v1", "assets": []},
    {"tag": "v1"},
])
def test_a_release_without_files_is_not_a_download(rel, tmp_path):
    (tmp_path / "release.json").write_text(json.dumps(rel), encoding="utf-8")
    assert site.load_release(tmp_path) is None


def test_a_missing_or_broken_file_is_not_a_download(tmp_path):
    assert site.load_release(tmp_path) is None
    (tmp_path / "release.json").write_text("{не json", encoding="utf-8")
    assert site.load_release(tmp_path) is None


def _api(monkeypatch, payload):
    class _R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(fetch_release.urllib.request, "urlopen",
                        lambda *a, **k: _R(json.dumps(payload).encode()))


def test_a_draft_release_never_reaches_the_page(monkeypatch):
    """Черновик видит только владелец — ссылка на него это 404 для всех."""
    _api(monkeypatch, [{"tag_name": "v9", "draft": True, "assets": [
        {"name": "RaceEngineer.zip", "size": 1, "browser_download_url": "u"}]}])
    assert fetch_release.fetch("a/b") is None


def test_a_prerelease_never_reaches_the_page(monkeypatch):
    _api(monkeypatch, [{"tag_name": "v9", "prerelease": True, "assets": [
        {"name": "RaceEngineer.zip", "size": 1, "browser_download_url": "u"}]}])
    assert fetch_release.fetch("a/b") is None


def test_only_our_archives_are_listed(monkeypatch):
    """GitHub прикладывает к релизу исходники сам — их на странице не ждут."""
    _api(monkeypatch, [{"tag_name": "v1", "published_at": "2026-09-07T00:00:00Z",
                        "html_url": "h", "assets": [
        {"name": "Source code.tar.gz", "size": 9, "browser_download_url": "s"},
        {"name": "RaceEngineer.zip", "size": 1, "browser_download_url": "u"}]}])
    rel = fetch_release.fetch("a/b")
    assert [a["name"] for a in rel["assets"]] == ["RaceEngineer.zip"]
    assert rel["published"] == "2026-09-07"


def test_no_network_leaves_the_page_alone(monkeypatch, tmp_path, capsys):
    """Нет интернета на машине сборки — не повод стереть рабочую страницу."""
    keep = tmp_path / "release.json"
    keep.write_text(json.dumps(REL), encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["fetch_release.py", "--repo", "a/b", "--out", str(keep)])

    def boom(*a, **k):
        raise OSError("сети нет")

    monkeypatch.setattr(fetch_release.urllib.request, "urlopen", boom)
    assert fetch_release.main() == 2, "должно быть предупреждение, а не поломка"
    assert json.loads(keep.read_text(encoding="utf-8"))["tag"] == "v0.1.1"


def test_a_withdrawn_release_removes_the_link(monkeypatch, tmp_path):
    """Релиз сняли — страница обязана перестать его обещать."""
    stale = tmp_path / "release.json"
    stale.write_text(json.dumps(REL), encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["fetch_release.py", "--repo", "a/b", "--out", str(stale)])
    _api(monkeypatch, [])
    assert fetch_release.main() == 0
    assert not stale.exists()
    assert site.load_release(tmp_path) is None
