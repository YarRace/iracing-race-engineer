"""Одно приложение вместо двух: инженер в фоне, страницы в одном окне.

Главная проверяемая вещь — не вёрстка, а поведение галочки. Раньше она
выбрасывала виджет на экран немедленно, и собрать раскладку спокойно было
нельзя: половина экрана занята ещё до того, как выбрал остальное. Теперь
галочка означает «входит в раскладку», а показывает всё кнопка внизу.
"""
import os
import pathlib
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                        # noqa: E402

from overlay.config import Config                                 # noqa: E402
from overlay.panel import ControlPanel                            # noqa: E402
from overlay.store import Store                                   # noqa: E402
from overlay.widgets import WIDGETS                               # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def panel(app, tmp_path):
    p = ControlPanel(Store(), Config(str(tmp_path / "cfg.json")), WIDGETS)
    p.show()
    yield p
    p.close()


# ── галочка ≠ показать ──────────────────────────────────────────────────────

def test_ticking_a_widget_does_not_put_it_on_screen(panel):
    """У Kapps галочка сразу выбрасывает виджет на экран. Так собрать
    раскладку нельзя: настраиваешь второй, а первый уже мешает."""
    cls = panel._cls_by_key["fuel"]
    panel.toggle(cls, True)
    assert panel.config.is_enabled("fuel"), "в раскладку не попал"
    assert not panel.widgets["fuel"].isVisible(), "выскочил до нажатия Start"


def test_start_shows_everything_that_was_picked(panel):
    for key in ("fuel", "delta", "standings"):
        panel.toggle(panel._cls_by_key[key], True)
    panel.set_overlays_running(True)
    assert all(panel.widgets[k].isVisible() for k in ("fuel", "delta", "standings"))


def test_stop_hides_them_all_but_keeps_the_layout(panel):
    """«Убрать с экрана» и «забыть, что я выбрал» — разные желания."""
    panel.toggle(panel._cls_by_key["fuel"], True)
    panel.set_overlays_running(True)
    panel.set_overlays_running(False)
    assert not panel.widgets["fuel"].isVisible()
    assert panel.config.is_enabled("fuel"), "раскладку стёрли вместе с показом"


def test_a_widget_ticked_while_running_appears_at_once(panel):
    """Когда всё уже показано, ждать второго нажатия неоткуда."""
    panel.set_overlays_running(True)
    panel.toggle(panel._cls_by_key["weather"], True)
    assert panel.widgets["weather"].isVisible()


def test_running_state_survives_a_restart_of_the_panel(app, tmp_path):
    """Флаг лежит в конфиге, а не в памяти окна: панель пересобирается
    при загрузке раскладки, и состояние не должно теряться."""
    cfg = Config(str(tmp_path / "cfg.json"))
    cfg.set_overlays_running(True)
    assert Config(str(tmp_path / "cfg.json")).overlays_running() is True


# ── само приложение ─────────────────────────────────────────────────────────

def test_the_app_opens_with_overlays_hidden(app, tmp_path, monkeypatch):
    """Открыл приложение — поверх игры пусто, чем бы ни кончился прошлый раз.
    Иначе окно открывается, а на экране уже что-то висит."""
    import ire.paths as P
    monkeypatch.setattr(P, "data_dir", lambda: tmp_path)
    cfg = Config(str(tmp_path / "overlay_config.json"))
    cfg.set_overlays_running(True)                # «прошлый раз» закончился так

    import app as A
    monkeypatch.setattr(A.Engineer, "start", lambda self: None)   # сим не поднимаем
    w = A.App()
    try:
        assert w.config.overlays_running() is False
        assert w.go.isChecked() is False
    finally:
        w.close()


def test_the_app_has_one_window_with_pages(app, tmp_path, monkeypatch):
    """Ради этого всё и затевалось: одно окно вместо двух процессов."""
    import ire.paths as P
    monkeypatch.setattr(P, "data_dir", lambda: tmp_path)
    import app as A
    monkeypatch.setattr(A.Engineer, "start", lambda self: None)
    w = A.App()
    try:
        assert w.pages.count() == 4
        assert [b.text() for b in w.tabs] == ["Home", "Overlays", "Dashboard", "News"]
        for i in range(4):
            w.show_page(i)                        # каждая страница строится без падения
            assert w.pages.currentIndex() == i
        assert w.panel.parent() is not None, "панель осталась отдельным окном"
    finally:
        w.close()


def test_a_dead_engineer_is_shown_not_swallowed(app, tmp_path, monkeypatch):
    """Инженер упал — окно обязано это сказать. Пустые виджеты без
    объяснения читаются как «программа сломана»."""
    import ire.paths as P
    monkeypatch.setattr(P, "data_dir", lambda: tmp_path)
    import app as A
    monkeypatch.setattr(A.Engineer, "start", lambda self: None)
    w = A.App()
    try:
        w.engineer.error = "RuntimeError: порт занят"
        w._tick_slow()
        assert "engineer stopped" in w.status.text()
        w.home.refresh()
        assert "порт занят" in w.home.sub.text()
    finally:
        w.close()


def test_closing_while_the_news_are_loading_does_not_crash(app, tmp_path, monkeypatch):
    """Восемь лент ходят по сети секунды. Если за это время закрыть окно,
    сигнал уходит в удалённый объект — RuntimeError и падение на выходе.
    """
    import threading

    import ire.paths as P
    monkeypatch.setattr(P, "data_dir", lambda: tmp_path)
    import app as A
    monkeypatch.setattr(A.Engineer, "start", lambda self: None)

    started = threading.Event()
    release = threading.Event()

    def slow_load(*a, **k):
        started.set()
        release.wait(5)
        return [{"title": "Norris extends McLaren deal", "summary": "",
                 "section": "F1", "source": "T", "link": ""}]

    import ire.collector.racenews as N
    monkeypatch.setattr(N, "load", slow_load)

    w = A.App()
    w.show_page(3)                        # запускаем загрузку
    assert started.wait(3), "загрузка не стартовала"
    w.close()
    w.news.deleteLater()
    app.processEvents()
    release.set()                         # поток отдаёт результат уже в никуда
    for _ in range(20):
        app.processEvents()
    # Дошли сюда — значит поток не уронил приложение.


# ── галерея оверлеев картинками ─────────────────────────────────────────────

def test_gallery_is_built_lazily_not_on_startup(panel):
    """Сорок пять картинок с диска на открытии окна — лишняя секунда
    на пустом месте: обычно человеку хватает списка."""
    assert panel._gallery_built is False
    assert panel.views.currentIndex() == 0


def test_switching_to_the_gallery_shows_a_card_per_widget(panel):
    panel.view_btn.setChecked(True)
    assert panel._gallery_built and panel.views.currentIndex() == 1
    grid = panel._gallery.widget().layout()
    assert grid.count() == len(WIDGETS), "карточек не столько, сколько виджетов"
    assert panel.view_btn.text() == "list"


def test_the_gallery_checkbox_and_the_list_stay_in_sync(panel):
    """У виджета теперь две галочки — в списке и на карточке. Разъедутся —
    и человек будет видеть разное в двух местах одного окна."""
    panel.view_btn.setChecked(True)
    panel._boxes["fuel"].setChecked(True)

    grid = panel._gallery.widget().layout()
    boxes = [w for i in range(grid.count())
             for w in grid.itemAt(i).widget().findChildren(type(panel._boxes["fuel"]))]
    assert any(b.isChecked() for b in boxes), "галочка на карточке не отразилась"


def test_a_missing_snapshot_does_not_break_the_gallery(panel, monkeypatch, tmp_path):
    """Снимки собирать необязательно. Галерея без картинок хуже, чем
    с картинками, но лучше, чем пустая колонка."""
    import ire.paths as P
    monkeypatch.setattr(P, "res_root", lambda: tmp_path)     # снимков там нет
    panel._gallery_built = False
    panel._build_gallery()
    grid = panel._gallery.widget().layout()
    assert grid.count() == len(WIDGETS)
