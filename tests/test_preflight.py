"""Проверка окружения перед стартом.

На Python 3.11 проект падает `SyntaxError` где-то в середине импорта, и по
такому сообщению человек делает вывод, что сломана программа, а не что у
него не та версия. Проверка должна сказать это словами.

Сама проверка обязана работать на ЛЮБОМ Python — иначе она упадёт ровно
тем способом, от которого защищает. Отсюда тест на её независимость.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire import preflight                                        # noqa: E402


def test_clean_environment_has_no_problems():
    assert preflight.check(exit_on_fail=False) == []


def test_missing_package_is_named_with_its_pip_name():
    """Имя импорта и имя в pip совпадают не всегда: uvicorn[standard],
    pyirsdk. Сказать «поставь irsdk» — отправить человека не туда."""
    got = preflight.check(extra=[("no_such_module_here", "the-pip-name")],
                          exit_on_fail=False)
    assert len(got) == 1
    assert "no_such_module_here" in got[0]
    assert "pip install the-pip-name" in got[0]


def test_old_python_is_reported_in_words(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 11, 9, "final", 0))
    got = preflight.check(exit_on_fail=False)
    assert got and "3.12" in got[0] and "too old" in got[0]


def test_it_exits_instead_of_continuing(monkeypatch, capsys):
    """Продолжать со сломанным окружением незачем: следующая же строка
    упадёт непонятной ошибкой, и сообщение потеряется в трассировке."""
    import pytest
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
    with pytest.raises(SystemExit) as e:
        preflight.check()
    assert e.value.code == 1
    assert "cannot start" in capsys.readouterr().out


def test_preflight_itself_runs_on_any_python():
    """Модуль не должен пользоваться ничем новее 3.6 и ничем внешним —
    иначе он упадёт раньше, чем успеет объяснить, что не так.
    """
    src = (ROOT / "src" / "ire" / "preflight.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        # f-строки появились в 3.6, но ':=', match и прочее — позже; проще
        # запретить всё, что мы сами сюда не звали
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in getattr(node, "names", [])]
            mod = getattr(node, "module", None)
            allowed = {"sys"}
            assert set(names) <= allowed and (mod is None or mod in allowed), \
                f"внешний импорт в preflight: {mod or names}"
        assert not isinstance(node, ast.NamedExpr), "':=' не понимает 3.7"
        assert not isinstance(node, ast.Match), "match не понимает 3.9"


def test_frozen_build_skips_the_package_check(monkeypatch):
    """В .exe зависимости внутри: если чего-то нет, приложение не стартовало
    бы вовсе, а лишняя проверка только тормозит запуск."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert preflight.check(extra=[("no_such_module_here", "x")],
                           exit_on_fail=False) == []
