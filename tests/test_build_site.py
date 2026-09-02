"""Статическая витрина: та же страница, но без запущенной программы.

Главное, что здесь проверяется, — что НЕ ОСТАЛОСЬ серверных адресов. Забытый
`/w/fuel.png` на GitHub Pages превращается в битую картинку, а заметить это
можно только открыв сайт глазами: тесты вёрстки такого не ловят, а человек
увидит витрину с дырами вместо виджетов.
"""
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tools import build_site as BS                                 # noqa: E402


def test_server_paths_are_rewritten_to_relative_ones():
    html = ('<link rel="stylesheet" href="/tokens.css">'
            '<img src="/w/fuel.png"><img src="/panel/panel.png">'
            '<img src="/dash/dashboard-solo.png"><img src="/hero.png">')
    out = BS.to_static(html)
    assert BS.leftover_absolute(out) == []
    assert 'src="widgets/fuel.png"' in out
    assert 'src="panel/panel.png"' in out
    assert 'src="dashboard/dashboard-solo.png"' in out


def test_the_navigation_stops_pointing_at_pages_that_do_not_exist():
    """На статическом сайте «Dashboard» вело бы в никуда: дашборд — это живая
    программа, а не страница. Ссылка на исходники честнее битой."""
    out = BS.to_static('<a href="/">Dashboard</a><a href="/about">About</a>')
    assert 'href="index.html"' in out
    assert "github.com" in out and ">Source</a>" in out


def test_links_into_the_changelog_keep_their_anchor():
    """Блок «что нового» ссылается на запись по якорю. Потерять якорь значит
    высадить человека в начало длинной страницы."""
    out = BS.to_static('<a href="/news#2026-09-01-tyre-tool">Tyre Tool</a>')
    assert 'href="changelog.html#2026-09-01-tyre-tool"' in out


def test_a_forgotten_server_path_is_reported_rather_than_shipped():
    """Ради этого проверка и написана: новый снимок с новым маршрутом молча
    уедет на сайт битой картинкой."""
    assert BS.leftover_absolute('<img src="/brand/new.png">') == ["/brand/new.png"]
    assert BS.leftover_absolute('<a href="https://x/y">x</a><a href="#z">z</a>') == []


def test_the_whole_site_builds_without_leftovers(tmp_path):
    written, problems = BS.build(tmp_path, check=True)
    assert not problems, problems
    assert {f for f, _ in written} == {"index.html", "widgets.html",
                                       "get.html", "changelog.html"}


def test_every_page_actually_gets_written(tmp_path):
    BS.build(tmp_path, check=False)
    for _, fname in BS.PAGES:
        assert (tmp_path / fname).exists(), fname
    assert (tmp_path / "tokens.css").exists(), "страницы выйдут без стилей"
    # Без .nojekyll GitHub Pages прогоняет папку через Jekyll — правило
    # молчаливое, и отключать его надо явно.
    assert (tmp_path / ".nojekyll").exists()


def test_the_built_page_only_points_at_files_that_exist():
    """Проверяем СОБРАННЫЙ сайт в docs/, а не выдуманный: там лежат настоящие
    снимки, и ссылка на несуществующий файл — это дыра на витрине."""
    index = ROOT / "docs" / "index.html"
    if not index.exists():
        pytest.skip("сайт не собран — python tools/build_site.py")
    html = index.read_text(encoding="utf-8")
    missing = [src for src in set(re.findall(r'src="([^"]+)"', html))
               if not src.startswith(("http", "data:"))
               and not (ROOT / "docs" / src).exists()]
    assert not missing, missing


def test_the_showcase_says_which_starter_set_a_widget_belongs_to():
    """Сорок семь незнакомых картинок — это не выбор. Человеку нужно знать,
    когда виджет включают, а не только как он выглядит."""
    idx = ROOT / "docs" / "widgets" / "index.json"
    if not idx.exists():
        pytest.skip("снимки не собраны")
    data = json.loads(idx.read_text(encoding="utf-8"))
    assert all("sets" in w for w in data), "наборы не записаны в опись"
    assert any(w["sets"] for w in data), "ни один виджет не попал в наборы"


def test_the_front_page_shows_what_changed_lately():
    """Полный журнал живёт отдельной страницей, куда никто не заходит."""
    from ire.dashboard import site

    html = site.page_about(site.load_catalog(), site.load_shots())
    assert "What changed lately" in html
    if site.read_news():
        assert 'class="changes"' in html


def test_an_old_index_without_sets_says_nothing_rather_than_something_false(tmp_path):
    """Опись, собранная прошлой версией, поля sets не имеет. «Не входит ни в
    один набор» было бы утверждением о том, чего мы не знаем, — а человек
    прочтёт его как факт и не станет искать виджет в наборах."""
    import json as _json

    from ire.dashboard import site

    (tmp_path / "index.json").write_text(_json.dumps(
        [{"key": "fuel", "title": "Fuel", "group": "solo", "size": [220, 170],
          "file": "fuel.png", "doc": "Fuel left and burn"}]), encoding="utf-8")
    html = site.page_about(site.load_catalog(), site.load_shots(tmp_path))
    assert "not in any starter set" not in html
    assert "220×170" in html, "остальные сведения потеряли вместе с наборами"


def test_a_widget_genuinely_in_no_set_is_still_told_so(tmp_path):
    import json as _json

    from ire.dashboard import site

    (tmp_path / "index.json").write_text(_json.dumps(
        [{"key": "fuel", "title": "Fuel", "group": "solo", "size": [220, 170],
          "file": "fuel.png", "doc": "Fuel", "sets": []}]), encoding="utf-8")
    html = site.page_about(site.load_catalog(), site.load_shots(tmp_path))
    assert "not in any starter set" in html


def test_the_widget_table_header_lines_up_with_its_columns():
    """В строке шесть ячеек (картинка, имя, группа, ключ, размер, данные), а
    в шапке было пять: каждый заголовок стоял на столбец левее своих данных,
    и «Name» подписывал картинки."""
    from ire.dashboard import site

    cat = site.load_catalog()
    if not cat.get("widgets"):
        pytest.skip("каталог не собран")
    html = site.page_catalog(cat, site.load_shots())
    # Каждую таблицу проверяем ОТДЕЛЬНО: на странице их две, и сравнить шапку
    # одной со строкой другой — это тест, который зелен по недоразумению.
    tables = re.findall(r"<table>(.*?)</table>", html, re.S)
    assert len(tables) >= 2, "таблиц на странице меньше, чем ожидалось"
    for i, t in enumerate(tables):
        head = re.search(r"<tr>((?:<th>.*?</th>)+)</tr>", t, re.S)
        row = re.search(r"<tr>((?:<td.*?</td>)+)</tr>", t, re.S)
        if not (head and row):
            continue
        assert head.group(1).count("<th>") == row.group(1).count("<td"), (
            f"таблица {i}: шапка на {head.group(1).count('<th>')} ячеек, "
            f"строка на {row.group(1).count('<td')}")


def test_a_changelog_entry_can_be_linked_to():
    """Блок «что изменилось» на главной ссылается якорем. Без id на записи
    браузер высаживает человека в начало длинной страницы."""
    from ire.dashboard import site

    news = site.read_news()
    if not news:
        pytest.skip("журнал пуст")
    html = site.page_news(news)
    for p in news[:3]:
        assert f'id="{p["slug"]}"' in html, p["slug"]


def test_the_static_site_does_not_offer_an_rss_file_it_does_not_have():
    """Фид собирает живой сервер. Ссылка на файл, которого не будет, — это
    404 в одно нажатие."""
    out = BS.to_static('<p>The changelog. <a href="/news/rss.xml">RSS</a></p>')
    assert "rss.xml" not in out
    assert BS.leftover_absolute(out) == []


def test_the_page_carries_a_card_for_messengers():
    """Кидаешь ссылку в Discord — мессенджер заходит на страницу и ищет
    именно эти метки. Не находит — показывает голый адрес."""
    from ire.dashboard import site

    html = site.page_about(site.load_catalog(), site.load_shots())
    for tag in ('property="og:title"', 'property="og:image"',
                'property="og:description"', 'name="twitter:card"'):
        assert tag in html, tag


def test_the_preview_image_is_an_absolute_address():
    """Мессенджер тянет картинку со своей стороны, и относительный путь ему
    не с чем сложить — карточка выйдет без обложки."""
    from ire.dashboard import site

    html = site.page_about(site.load_catalog(), site.load_shots())
    m = re.search(r'property="og:image" content="([^"]+)"', html)
    assert m and m.group(1).startswith("https://"), m and m.group(1)


def test_the_preview_image_actually_exists():
    """Ссылка на картинку, которой нет, — карточка без обложки и вопрос «а
    где?». Проверяем ФАЙЛ, а не только тег."""
    from ire.dashboard import site

    html = site.page_about(site.load_catalog(), site.load_shots())
    url = re.search(r'property="og:image" content="([^"]+)"', html).group(1)
    name = url.rsplit("/", 1)[-1]
    assert (ROOT / "docs" / name).exists(), name
