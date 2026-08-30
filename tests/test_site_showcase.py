"""Витрина виджетов на сайте: список слева, выбранный справа.

Переключение сделано на радиокнопках и соседних селекторах CSS, без скриптов.
Ровно здесь легко ошибиться: «~» связывает только элементы с ОБЩИМ родителем,
и пока инпуты лежали внутри списка, правило не срабатывало — сцена оставалась
пустой, хотя разметка выглядела правильной. Тесты фиксируют структуру.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire.dashboard import site                                      # noqa: E402


SHOTS = [
    {"key": "inputs", "title": "Inputs", "group": "solo",
     "file": "inputs.png", "doc": "Скорость и педали."},
    {"key": "fuel", "title": "Fuel & pit", "group": "solo",
     "file": "fuel.png", "doc": "Топливо и пит-стопы."},
]


def test_radio_inputs_are_siblings_of_the_stage():
    """Инпуты обязаны быть прямыми детьми .show, а не лежать внутри списка.

    Иначе «#sN:checked ~ .show-stage» не находит сцену и витрина мертва.
    """
    html = site.showcase(SHOTS)
    show = html[html.index('<div class="show">'):]
    inputs_at = show.index('<input type="radio"')
    list_at = show.index('<div class="show-list">')
    assert inputs_at < list_at, "инпуты должны идти ДО списка, на одном уровне с ним"


def test_every_shot_gets_a_rule_and_a_figure():
    html = site.showcase(SHOTS)
    for i, w in enumerate(SHOTS):
        assert f'id="s{i}"' in html
        assert f'<figure id="f{i}">' in html
        assert f"#s{i}:checked~.show-stage #f{i}{{display:block}}" in html
        assert f'/w/{w["file"]}' in html


def test_first_item_is_preselected():
    """Иначе при загрузке страницы сцена пустая и витрина выглядит сломанной."""
    html = site.showcase(SHOTS)
    assert 'id="s0" checked' in html.replace('id="s0"checked', 'id="s0" checked')
    assert 'id="s1" checked' not in html


def test_selected_item_is_highlighted_in_the_list():
    html = site.showcase(SHOTS)
    assert '#s0:checked~.show-list label[for="s0"]' in html


def test_showcase_is_silent_without_shots():
    """Снимки собирать ради страницы «о проекте» никто не обязан —
    без них сайт должен остаться рабочим."""
    assert site.showcase([]) == ""


def test_titles_are_escaped():
    html = site.showcase([{"key": "x", "title": "<script>", "group": "solo",
                           "file": "x.png", "doc": "a & b"}])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a &amp; b" in html


def test_about_page_survives_without_shots():
    """Проверяем РАЗМЕТКУ, а не стили: правила .show-stage лежат в общем
    шаблоне и присутствуют всегда, даже когда витрины на странице нет."""
    cat = site.load_catalog()
    html = site.page_about(cat, [])
    assert "<h1>" in html
    assert '<div class="show">' not in html
    assert "<figure id=" not in html


def test_catalog_row_explains_what_the_widget_does():
    """Название и ключ не отвечают на вопрос «что оно показывает».

    Описание берётся из BLURB виджета — отдельного английского поля, а не
    из докстринга: докстринги русские, а сайт английский.
    """
    cat = {"widgets": [{"key": "fuel", "title": "Fuel & pit", "group": "solo",
                        "group_title": "Solo", "width": 230, "height": 220,
                        "endpoints": ["strategy"],
                        "desc": "Fuel left, burn rate and what the next stop needs."}],
           "cards": [], "counts": {"widgets": 1, "cards": 0}}
    html = site.page_catalog(cat, [])
    assert "Fuel left, burn rate and what the next stop needs." in html
    assert 'class="sub"' in html


def test_catalog_survives_a_widget_without_a_description():
    """Старый catalog.json без поля desc не должен ронять страницу."""
    cat = {"widgets": [{"key": "fuel", "title": "Fuel & pit", "group": "solo",
                        "group_title": "Solo", "width": 230, "height": 220,
                        "endpoints": []}],
           "cards": [], "counts": {"widgets": 1, "cards": 0}}
    assert "Fuel &amp; pit" in site.page_catalog(cat, [])


# ── галерея панели настроек ─────────────────────────────────────────────────

PANELS = [
    {"file": "panel.png", "key": "fuel", "caption": "Pick an overlay."},
    {"file": "panel-map.png", "key": "trackmap", "caption": "The real widget."},
]


def test_gallery_inputs_are_siblings_of_the_stage():
    """Та же ловушка, что и в витрине: «~» связывает только элементы
    с ОБЩИМ родителем. Инпуты внутри вкладок — и галерея мертва."""
    html = site.panel_gallery(PANELS)
    block = html[html.index('<div class="gal">'):]
    assert block.index('<input type="radio"') < block.index('<div class="gal-tabs">')


def test_gallery_wires_every_shot():
    html = site.panel_gallery(PANELS)
    for i, s in enumerate(PANELS):
        assert f'id="pn{i}"' in html
        assert f'<figure id="pnf{i}">' in html
        assert f"#pn{i}:checked~.gal-stage #pnf{i}{{display:block}}" in html
        assert f'/panel/{s["file"]}' in html
    assert 'id="pn0" checked' in html


def test_two_galleries_on_one_page_do_not_collide():
    """Панель и дашборд стоят на /about рядом. Общие id — и клик по вкладке
    одной галереи переключал бы вторую."""
    dash = [{"file": "dashboard-solo.png", "caption": "The solo tab."}]
    html = site.panel_gallery(PANELS) + site.dashboard_gallery(dash)
    assert 'name="pn"' in html and 'name="db"' in html
    assert 'id="pn0"' in html and 'id="db0"' in html
    assert html.count('id="pn0"') == 1 and html.count('id="db0"') == 1


def test_galleries_are_silent_without_shots():
    """Снимки собирать необязательно — сайт должен остаться рабочим."""
    assert site.panel_gallery([]) == ""
    assert site.dashboard_gallery([]) == ""
    assert '<div class="gal">' not in site.page_about(site.load_catalog(), [], [], [])


def test_gallery_captions_are_escaped():
    html = site.panel_gallery([{"file": "x.png", "caption": "a <b> & c"}])
    assert "<b>" not in html
    assert "a &lt;b&gt; &amp; c" in html


# ── страница «как это взять» ────────────────────────────────────────────────

def test_download_page_lists_the_real_commands():
    """Инструкция, которая не работает, хуже отсутствующей."""
    html = site.page_download(site.load_catalog(), [])
    for cmd in ("git clone", "python -m venv .venv", "pip install -r requirements.txt",
                "python run.py", "python overlay_app.py"):
        assert cmd in html, cmd
    assert r".venv\Scripts\activate" in html


def test_download_page_does_not_promise_an_installer():
    """Кнопки «Download» поверх пустоты быть не должно: установщика нет."""
    html = site.page_download(site.load_catalog(), [])
    assert "no packaged installer yet" in html
    assert ".exe" not in html and ".msi" not in html


def test_download_page_survives_an_unbuilt_catalog():
    empty = {"widgets": [], "cards": [], "counts": {}}
    html = site.page_download(empty, [])
    assert "<h1>Get it running" in html
    assert "0 overlays" in html
