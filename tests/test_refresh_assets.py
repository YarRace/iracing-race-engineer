"""Сборка картинок: что валит прогон, а что всего лишь предупреждение.

Три вещи проверяются здесь, и каждая уже ломалась вживую.

1. Ненайденный браузер и не снявшийся снимок — это СРЕДА, а не ошибка кода.
   Из-за одной картинки падала сборка релиза целиком.
2. Текст ошибки должен доходить целиком. Обрезанный хвост в 400 символов
   стоил лишнего круга «поправил, запушил, подождал».
3. Ошибка должна попадать в аннотацию GitHub. Журнал прогона закрыт даже
   на открытом репозитории (403), аннотации — открыты; это единственный
   способ увидеть причину снаружи.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import refresh_assets as ra  # noqa: E402


class _Run:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def _fake(codes, calls=None):
    """Подменить запуск скриптов: имя файла -> результат."""
    def run(cmd, **kw):
        name = pathlib.Path(cmd[-1]).name
        if calls is not None:
            calls.append(name)
        return codes.get(name, _Run(0))
    return run


def test_a_missing_browser_is_a_warning_not_a_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["refresh_assets.py"])
    monkeypatch.setattr(ra.subprocess, "run",
                        _fake({"render_dashboard.py": _Run(2)}))
    assert ra.main() == 0
    out = capsys.readouterr().out
    assert "ПРОП" in out and "render_dashboard.py" in out


def test_a_real_break_still_fails(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["refresh_assets.py"])
    monkeypatch.setattr(ra.subprocess, "run",
                        _fake({"build_catalog.py": _Run(1, err="ImportError")}))
    assert ra.main() == 1
    assert "СБОЙ" in capsys.readouterr().out


def test_the_whole_error_is_printed_not_the_last_400_chars(monkeypatch, capsys):
    long = "строка ошибки, которая повторяется много раз. " * 40
    monkeypatch.setattr(sys, "argv", ["refresh_assets.py"])
    monkeypatch.setattr(ra.subprocess, "run",
                        _fake({"render_widgets.py": _Run(1, err=long)}))
    ra.main()
    out = capsys.readouterr().out
    assert long.strip() in out, "хвост обрезан — причину не прочитать"


def test_fast_skips_the_slow_shots(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["refresh_assets.py", "--fast"])
    monkeypatch.setattr(ra.subprocess, "run", _fake({}, calls))
    ra.main()
    assert "render_dashboard.py" not in calls
    assert "build_catalog.py" in calls


def test_outside_ci_nothing_is_annotated(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    ra._annotate("x.py", "упало")
    assert capsys.readouterr().out == ""


def test_the_annotation_survives_newlines_and_percent(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    ra._annotate("render_panel.py", """Traceback (most recent call last):
  ValueError: сжатие 100% не поддерживается""")
    out = capsys.readouterr().out.strip()
    assert out.startswith("::error title=render_panel.py::")
    # Один перевод строки оборвал бы аннотацию на слове Traceback — а нужен
    # как раз хвост с исключением. И «100%» без экранирования GitHub читает
    # как начало своей команды.
    assert len(out.splitlines()) == 1
    assert "%0A" in out and "100%25" in out
    assert "ValueError" in out


def test_a_dashboard_shot_that_did_not_render_is_only_a_warning():
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "tools" / "render_dashboard.py").read_text(encoding="utf-8")
    assert "return 2 if failed else 0" in src, (
        "снимок дашборда снова роняет сборку: браузера на машине может и не "
        "быть, это не повод не собрать релиз")


@pytest.mark.parametrize("script", ["render_panel.py", "render_widgets.py"])
def test_a_widget_that_threw_still_fails_the_build(script):
    # Эти двое рисуют через Qt, без внешнего браузера. Исключение оттуда —
    # сломанный виджет, и прощать его нельзя: витрина молча недосчитается
    # картинки, а опись уедет в git уже без неё.
    src = (pathlib.Path(__file__).resolve().parents[1] / "tools" / script).read_text(
        encoding="utf-8")
    assert "return 1" in src, f"{script} стал прощать поломку виджета"
