"""Разделы списка виджетов и «другой вид тех же данных».

Сорок семь виджетов одним столбцом — это прокрутка на каждый чих и вечный
вопрос «Standings и H. standings — разве не одно и то же?». Данные одни,
форма разная; список об этом молчал, и разница читалась как дубль.

Ничего не удалено НАМЕРЕННО: и вертикальная таблица, и горизонтальная
лента нужны разным людям, а выбор формы — это не мусор. Убрана путаница,
а не возможности.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from overlay import widgets as W

KEYS = {c.KEY for c in W.WIDGETS}


def test_every_widget_lands_in_a_section():
    """Новый виджет без раздела молча уедет в конец списка — так и было."""
    lost = [c.KEY for c in W.WIDGETS if not getattr(c, "TOPIC", None)]
    assert not lost, f"без раздела: {', '.join(lost)}"


def test_the_sections_are_the_declared_ones():
    known = {k for k, _ in W.TOPICS}
    used = {getattr(c, "TOPIC", None) for c in W.WIDGETS}
    assert used <= known, f"раздел не объявлен в TOPICS: {used - known}"


def test_no_widget_is_listed_in_two_sections():
    seen = {}
    for topic, keys in W.TOPIC_OF.items():
        for k in keys:
            assert k not in seen, f"{k} стоит и в {seen[k]}, и в {topic}"
            seen[k] = topic


def test_the_sections_do_not_name_widgets_that_do_not_exist():
    """Опечатка в ключе оставила бы виджет без раздела и молча."""
    named = {k for keys in W.TOPIC_OF.values() for k in keys}
    assert named <= KEYS, f"таких виджетов нет: {sorted(named - KEYS)}"


def test_no_section_is_left_empty():
    for key, title in W.TOPICS:
        assert any(getattr(c, "TOPIC", None) == key for c in W.WIDGETS), \
            f"раздел «{title}» пуст"


@pytest.mark.parametrize("a,b", [("standings", "hstandings"),
                                 ("laptimegraph", "laptimespread")])
def test_the_pairs_he_called_duplicates_are_named_as_alternatives(a, b):
    """Именно эти две пары он и назвал дублями."""
    by = {c.KEY: c for c in W.WIDGETS}
    assert by[b].TITLE in (by[a].ALT or ()), f"{a} не знает про {b}"
    assert by[a].TITLE in (by[b].ALT or ()), "связь обязана быть двусторонней"


def test_alternatives_sit_in_the_same_section():
    """Разведённые по разделам, они снова окажутся далеко друг от друга."""
    by = {c.TITLE: c for c in W.WIDGETS}
    for c in W.WIDGETS:
        for title in getattr(c, "ALT", ()) or ():
            assert by[title].TOPIC == c.TOPIC, f"{c.TITLE} и {title} в разных разделах"


def test_the_delta_family_is_fully_connected():
    """Трое показывают одну дельту. Каждый обязан знать про двух других."""
    by = {c.KEY: c for c in W.WIDGETS}
    for k in ("delta", "deltabar", "deltatrace"):
        assert len(by[k].ALT or ()) == 2, f"{k}: {by[k].ALT}"


def test_nothing_was_quietly_removed():
    """Прибрать список — не то же самое, что выбросить виджеты."""
    for k in ("standings", "hstandings", "laptimegraph", "laptimespread",
              "delta", "deltabar", "deltatrace"):
        assert k in KEYS, f"{k} исчез — это уже не уборка"
