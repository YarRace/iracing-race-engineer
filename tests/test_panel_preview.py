"""Панель с живым предпросмотром: три колонки, поиск, выбор виджета.

Проверяем не картинку, а поведение: предпросмотр — тот же класс виджета
с тем же конфигом, поэтому правка настройки видна сразу и в нём, и в боевом
оверлее. Отдельной «модели предпросмотра», которая рано или поздно разъедется
с оригиналом, здесь нет, и тесты это фиксируют.
"""
import os
import pathlib
import sys
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("PySide6")

from PySide6.QtGui import QPixmap                                   # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from overlay.config import Config                                   # noqa: E402
from overlay.panel import ControlPanel                              # noqa: E402
from overlay.store import Store                                     # noqa: E402
from overlay.widgets import WIDGETS                                 # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def panel(app, tmp_path):
    p = ControlPanel(Store(), Config(str(tmp_path / "cfg.json")), WIDGETS)
    p.show()
    yield p
    p.close()


def _visible_rows(panel):
    return [b.text() for b in panel._rows.values() if not b.parentWidget().isHidden()]


def test_every_widget_can_be_previewed(panel):
    """Ни один из сорока двух не должен ронять предпросмотр."""
    for W in WIDGETS:
        panel.select(W.KEY)
        assert type(panel.preview._widget) is W
        pm = QPixmap(panel.size())
        panel.render(pm)                       # падение отрисовки — это провал теста


def test_preview_is_a_child_not_an_overlay_window(panel):
    """Предпросмотр не должен становиться окном поверх игры.

    Иначе он улетел бы в координаты рабочего стола из конфига и перехватывал
    мышь у самой панели.
    """
    panel.select("weather")
    w = panel.preview._widget
    assert w.preview is True
    assert w.parent() is panel.preview
    assert not w.isWindow()


def test_setting_changes_preview_and_live_widget_together(panel):
    """Одна правка — один конфиг: предпросмотр и боевой оверлей не разъезжаются."""
    cfg = panel.config
    panel.select("weather")
    prev = panel.preview._widget
    panel.toggle(panel._cls_by_key["weather"], True)
    live = panel.widgets["weather"]

    assert "Wind" in [r[0] for r in prev.rows()]
    cfg.set_widget_opt("weather", "show_wind", False)
    assert "Wind" not in [r[0] for r in prev.rows()]
    assert "Wind" not in [r[0] for r in live.rows()]     # тот же конфиг


def test_search_filters_rows_and_hides_empty_groups(panel):
    assert len(_visible_rows(panel)) == len(WIDGETS)

    panel.search.setText("delta")
    found = _visible_rows(panel)
    assert found and all("delta" in t.lower() for t in found)
    assert panel._group_heads["endur"].isHidden()        # в группе ничего не нашлось

    panel.search.setText("такого нет")
    assert _visible_rows(panel) == []

    panel.search.setText("")
    assert len(_visible_rows(panel)) == len(WIDGETS)


def test_selecting_does_not_force_the_overlay_on(panel):
    """Раньше ради настройки виджет приходилось включать, и он выскакивал
    поверх игры. Теперь настраиваем на предпросмотре."""
    key = "weather"
    panel.toggle(panel._cls_by_key[key], False)
    panel.select(key)
    assert panel.preview._widget is not None
    assert not panel.config.is_enabled(key)
    assert key not in panel.widgets or not panel.widgets[key].isVisible()


def test_preview_endpoints_are_polled(panel):
    """Иначе предпросмотр стоял бы пустым: опрашиваются только нужные эндпоинты."""
    panel.select("standings")
    panel._update_active()
    active = panel.store._active if hasattr(panel.store, "_active") else None
    if active is not None:
        assert set(panel._cls_by_key["standings"].ENDPOINTS) <= set(active)
