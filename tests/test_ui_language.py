"""Интерфейс — только английский. Тест ловит русскую строку, написанную сразу.

Решение принято 17.07.2026 и держится ради продажи: оба конкурента
англоязычные, а переключателя RU/EN у нас нет и не планируется. Правило
сформулировано узко: русскими остаются комментарии и докстринги — их читает
автор. Всё, что попадает на экран пользователю, — на английском.

Проверять это глазами бесполезно. Русская подпись выглядит правильной ровно
до момента, когда её увидит покупатель; за один вечер в панель уехало сто пять
таких строк, и заметил их не человек, а обход AST. Поэтому обход и остаётся
в тестах.
"""
import ast
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CYRILLIC = re.compile("[А-Яа-яЁё]")

# Файлы, чьи строковые литералы уезжают на экран целиком.
UI_FILES = ["overlay/panel.py", "overlay/preview.py", "overlay/widgets.py",
            "overlay/base.py", "src/ire/dashboard/site.py"]


def ui_strings(path):
    """Строковые литералы файла без докстрингов.

    Докстринги вырезаны намеренно: они объясняют код автору и остаются
    русскими. Всё остальное — подписи, подсказки, заголовки — на экране.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docs.add(d)
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and n.value not in docs]


@pytest.mark.parametrize("rel", UI_FILES)
def test_no_cyrillic_in_ui_strings(rel):
    hits = [(ln, v) for ln, v in ui_strings(ROOT / rel) if CYRILLIC.search(v)]
    assert not hits, f"{rel}: русский текст на экране — {hits[:3]}"


def test_every_widget_has_an_english_blurb():
    """Подпись виджета на сайте — отдельное поле, а не первая строка докстринга.

    Пока сайт читал докстринг, витрина показывала русский текст, хотя сам
    сайт был английским: два разных назначения жили в одном месте.
    """
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from overlay.widgets import WIDGETS

    for cls in WIDGETS:
        blurb = cls.__dict__.get("BLURB")
        assert blurb, f"{cls.KEY}: нет своего BLURB"
        assert not CYRILLIC.search(blurb), f"{cls.KEY}: BLURB по-русски"
        assert blurb[0].isupper() and blurb.endswith("."), \
            f"{cls.KEY}: подпись — предложение с большой буквы и точкой"
        assert len(blurb) <= 80, f"{cls.KEY}: подпись длиннее строки таблицы"


def test_changelog_entries_are_english():
    """Записи чейнджлога рендерятся прямо на страницу /news."""
    for f in sorted((ROOT / "docs" / "news").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        assert not CYRILLIC.search(text), f"{f.name}: запись по-русски"
