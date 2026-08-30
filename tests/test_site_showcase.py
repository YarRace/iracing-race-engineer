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
