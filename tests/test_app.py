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


# ── готовые наборы ──────────────────────────────────────────────────────────

def test_every_starter_set_names_real_widgets():
    """Опечатка в ключе — и набор молча включит на один виджет меньше."""
    from overlay.panel import STARTERS
    keys = {c.KEY for c in WIDGETS}
    for name, ks in STARTERS:
        missing = [k for k in ks if k not in keys]
        assert not missing, f"{name}: нет таких виджетов — {missing}"
        assert len(set(ks)) == len(ks), f"{name}: повторы в наборе"


def test_a_starter_set_replaces_the_choice_rather_than_adding_to_it(panel):
    """Иначе поверх своей раскладки ляжет чужой набор, и на экране окажется
    всё сразу — чего никто не просил."""
    from overlay.panel import STARTERS
    panel._boxes["weatherradar"].setChecked(True)      # что-то своё, не из набора
    panel._apply_starter(1)                            # Sprint race

    name, keys = STARTERS[0]
    on = {k for k in panel._boxes if panel.config.is_enabled(k)}
    assert on == set(keys), "набор не заменил прежний выбор"
    assert not panel.config.is_enabled("weatherradar")


def test_picking_the_header_line_does_nothing(panel):
    panel._boxes["fuel"].setChecked(True)
    panel._apply_starter(0)                            # «— starter set —»
    assert panel.config.is_enabled("fuel"), "заголовок выпадашки стёр раскладку"


def test_the_starter_sets_cover_the_three_ways_people_drive():
    """Спринт, эндуранс и практика — три разных экрана. Один набор на всех
    означал бы, что он не подходит никому."""
    from overlay.panel import STARTERS
    names = [n for n, _ in STARTERS]
    assert len(names) == len(set(names)) == 3
    sets = [set(k) for _, k in STARTERS]
    for a, b in ((0, 1), (0, 2), (1, 2)):
        assert sets[a] != sets[b], "два набора одинаковы"


# ── один список наборов вместо двух ─────────────────────────────────────────

def _rows(panel, kind):
    return [n for k, n in panel._set_rows if k == kind]


def test_ready_made_and_my_own_sets_live_in_one_list(panel):
    """Раньше готовые наборы лежали в одном выпадающем списке, а свои — в
    соседнем. Это одно и то же желание «покажи вот эти виджеты», и держать
    его в двух местах значит заставлять помнить, в каком из них искать."""
    from overlay.panel import STARTERS
    panel._boxes["fuel"].setChecked(True)
    panel.config.save_profile("Spa night")
    panel._refresh_profiles()

    assert _rows(panel, "starter") == [n for n, _ in STARTERS]
    assert _rows(panel, "mine") == ["Spa night"]
    assert _rows(panel, "save") == [""], "нет строки «сохранить как набор»"


def test_picking_a_ready_made_set_does_not_move_the_widgets(panel):
    """Готовый набор отвечает на вопрос «что показать», а не «где». Человек
    выстроил экран под свой монитор — переставлять всё под наш вкус нельзя."""
    panel._boxes["fuel"].setChecked(True)
    panel.config.set_geometry("fuel", 1234, 567, 300, 120)

    i = [k for k, _ in panel._set_rows].index("starter")
    panel._on_set_picked(i)                       # Sprint race, там есть fuel

    assert panel.config.geometry("fuel")[:2] == (1234, 567), "виджет уехал"


def test_picking_my_own_set_puts_everything_back_including_places(panel):
    """Свой набор для того и сохраняли: вернуть экран целиком, а не только
    галочки. Иначе он ничем не отличался бы от готового."""
    panel._boxes["fuel"].setChecked(True)
    panel.config.set_geometry("fuel", 100, 200, 300, 120)
    panel.config.save_profile("Spa night")

    panel.config.set_geometry("fuel", 999, 999, 300, 120)   # всё сдвинули
    panel._boxes["fuel"].setChecked(False)                  # и выключили
    panel._refresh_profiles()

    i = [k for k, _ in panel._set_rows].index("mine")
    panel._on_set_picked(i)

    assert panel.config.is_enabled("fuel"), "набор не вернул виджет"
    assert panel.config.geometry("fuel")[:2] == (100, 200), "место не вернулось"


def test_the_header_line_of_the_list_does_nothing(panel):
    panel._boxes["fuel"].setChecked(True)
    panel._on_set_picked(0)                       # «— pick a set —»
    assert panel.config.is_enabled("fuel"), "заголовок списка стёр выбор"


def test_the_save_row_asks_for_a_name_and_saves_under_it(panel, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Monza wet", True)))
    panel._boxes["radar"].setChecked(True)

    i = [k for k, _ in panel._set_rows].index("save")
    panel._on_set_picked(i)

    assert "Monza wet" in panel.config.profiles()
    assert _rows(panel, "mine") == ["Monza wet"], "новый набор не встал в список"


def test_backing_out_of_the_save_dialog_leaves_no_half_made_set(panel, monkeypatch):
    """Нажал «сохранить», передумал — список обязан вернуться в прежний вид,
    а не остаться стоять на строке, которая ничего не значит."""
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))
    i = [k for k, _ in panel._set_rows].index("save")
    panel._on_set_picked(i)

    assert panel.config.profiles() == [], "сохранился набор без имени"
    assert panel._set_rows[panel.prof.currentIndex()][0] != "save"


def test_saving_over_an_existing_set_asks_first(panel, monkeypatch):
    """Набор — снимок, и запись поверх стирает его насовсем. Раньше вопрос
    был не нужен, потому что набор и так молча затирался при каждом движении
    виджета; теперь он единственная защита."""
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    panel._boxes["fuel"].setChecked(True)
    panel.config.save_profile("Spa night")
    panel._refresh_profiles()

    panel._boxes["fuel"].setChecked(False)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Spa night", True)))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    panel.save_as_profile()

    assert panel.config.load_profile("Spa night")
    assert panel.config.is_enabled("fuel"), "набор затёрли, хотя ответили «нет»"


def test_saying_yes_does_replace_it(panel, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    panel._boxes["fuel"].setChecked(True)
    panel.config.save_profile("Spa night")
    panel._boxes["fuel"].setChecked(False)

    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Spa night", True)))
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    panel.save_as_profile()

    panel.config.load_profile("Spa night")
    assert not panel.config.is_enabled("fuel"), "ответили «да», а набор прежний"


def test_a_new_name_is_saved_without_extra_questions(panel, monkeypatch):
    """Вопрос уместен только там, где что-то теряется. На новом имени он шум."""
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    def refuse(*a, **k):
        raise AssertionError("спросили про замену там, где нечего заменять")

    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Monza wet", True)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(refuse))
    panel.save_as_profile()
    assert "Monza wet" in panel.config.profiles()


def test_the_home_page_offers_a_way_into_the_showcase(app, tmp_path, monkeypatch):
    """Витрина хорошая, и её никто не видел: адрес надо помнить, а помнить
    его неоткуда. Кнопка стоит там, куда смотрят на главной в первую
    секунду."""
    from PySide6.QtWidgets import QPushButton

    import ire.paths as P
    monkeypatch.setattr(P, "data_dir", lambda: tmp_path)
    import app as A
    monkeypatch.setattr(A.Engineer, "start", lambda self: None)

    opened = []
    monkeypatch.setattr(A.webbrowser, "open", opened.append)

    w = A.App()
    try:
        btn = next(b for b in w.home.findChildren(QPushButton)
                   if "showcase" in b.text().lower())
        btn.click()
        assert opened == [A.DASH + "/about"], opened
    finally:
        w.close()
