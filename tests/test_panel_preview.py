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
    # && снимаем: в тексте кнопки Qt требует удвоения амперсанда
    return [b.text().replace("&&", "&") for b in panel._rows.values()
            if not b.parentWidget().isHidden()]


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


def test_demo_feed_fills_every_endpoint():
    """Настраивать виджет по прочеркам бессмысленно — демо-поток даёт данные."""
    from overlay.demo import DemoFeed
    d = DemoFeed()
    for ep in ("live", "race", "standings", "relative", "strategy",
               "wear", "session", "damage", "result", "trackmap"):
        assert d.get(ep), f"эндпоинт {ep} пуст"


def test_demo_pedals_are_not_stuck_at_the_limits():
    """Первая версия давала газ 1.00 и тормоз 0.00 весь круг: множитель
    подобрали на глаз, а производная профиля оказалась в ±0.07."""
    import time
    from overlay.demo import DemoFeed, LAP_TIME
    vals = []
    for i in range(40):
        d = DemoFeed(t0=time.monotonic() - LAP_TIME * i / 40)
        live = d.get("live")
        vals.append((live["throttle"], live["brake"]))
    thr = [t for t, _ in vals]
    # Ноль на тяжёлом торможении — это ПРАВИЛЬНО, гонщик там отпускает педаль
    # полностью. Плохо не «дошло до края», а «стоит на краю весь круг».
    assert sum(1 for t in thr if t <= 0.001) <= 3     # изредка, а не постоянно
    assert sum(1 for t in thr if t >= 0.999) == 0     # в полу не залипает вовсе
    assert len({round(t, 1) for t in thr}) > 3        # и действительно меняется


def test_demo_speed_never_flatlines():
    """Профиль круга не должен упираться в нижний предел: на графике это
    выглядело как остановка машины на пятой части круга."""
    from overlay.demo import _shape
    vals = [_shape(i / 200) for i in range(200)]
    assert min(vals) > 0.13                            # предел 0.12 не достигается


def test_preview_store_falls_back_to_demo_but_live_wins():
    """Боевые оверлеи обязаны показывать прочерки без сима: выдуманные цифры
    поверх игры — прямой путь к неверному решению на трассе."""
    from overlay.demo import DemoFeed
    from overlay.panel import _PreviewStore

    class Empty:
        ok = False
        def get(self, ep): return {}
        def set_active(self, e): pass

    class Live:
        ok = True
        def get(self, ep): return {"speed": 42.0} if ep == "live" else {}
        def set_active(self, e): pass

    s = _PreviewStore(Empty(), DemoFeed())
    assert s.get("live")                               # пусто → берём демо
    s.allow_demo = False
    assert s.get("live") == {}                         # выключили → снова пусто

    s = _PreviewStore(Live(), DemoFeed())
    assert s.get("live")["speed"] == 42.0              # живое всегда важнее демо


def test_favourites_lift_widgets_to_the_top(panel):
    """Сорок четыре строки — прокрутка на каждый чих, нужных обычно десяток."""
    assert panel._fav_head.isHidden()                  # пока пусто — группы не видно

    panel._favs["fuel"].setChecked(True)
    panel._favs["standings"].setChecked(True)
    assert panel.config.favourites() == ["fuel", "standings"]
    assert not panel._fav_head.isHidden()
    assert panel._fav_lay.count() == 2

    panel._favs["fuel"].setChecked(False)
    assert panel.config.favourites() == ["standings"]
    assert panel._fav_lay.count() == 1


def test_favourite_row_is_a_copy_not_a_move(panel):
    """Строка обязана остаться и в своей группе: иначе виджет пропадает
    из привычного места и его ищут заново."""
    panel._favs["fuel"].setChecked(True)
    assert "fuel" in panel._rows                       # исходная строка на месте
    assert not panel._rows["fuel"].parentWidget().isHidden()


def test_open_button_reflects_and_controls_state(panel):
    panel.select("weather")
    panel.toggle(panel._cls_by_key["weather"], False)
    assert not panel.open_btn.isChecked()
    assert "Add to layout" == panel.open_btn.text()

    panel.open_btn.setChecked(True)                    # нажали кнопку
    assert panel.config.is_enabled("weather")
    assert "In the layout" == panel.open_btn.text()


def test_widget_preset_moves_look_without_touching_layout(panel):
    """Профиль тащит всю раскладку. Пресет виджета — только его настройки."""
    cfg = panel.config
    panel.select("fuel")
    cfg.set_widget_opt("fuel", "warn_laps", 6)
    cfg.set_enabled("standings", True)                 # посторонняя часть раскладки

    cfg.save_widget_preset("fuel", "endurance")
    cfg.set_widget_opt("fuel", "warn_laps", 2)
    cfg.set_enabled("standings", False)

    assert cfg.load_widget_preset("fuel", "endurance")
    assert cfg.widget_opt("fuel", "warn_laps") == 6
    assert cfg.is_enabled("standings") is False        # раскладку пресет не трогал


def test_widget_preset_list_is_per_widget(panel):
    cfg = panel.config
    cfg.save_widget_preset("fuel", "a")
    cfg.save_widget_preset("weather", "b")
    assert cfg.widget_presets("fuel") == ["a"]
    assert cfg.widget_presets("weather") == ["b"]


def test_ampersand_survives_in_button_labels(panel):
    """Qt считает «&» началом горячей клавиши и съедает его: «Fuel & pit»
    превращалось в «Fuel _pit» с подчёркнутой буквой."""
    assert panel._rows["fuel"].text() == "Fuel && pit"
    assert panel._rows["position"].text() == "Position && gaps"
    panel.search.setText("fuel &")                     # поиск всё равно находит
    assert "Fuel & pit" in _visible_rows(panel)
    panel.search.setText("")


def test_favourite_rows_are_not_squashed(panel):
    """Вложенный контейнер сжимался родительской раскладкой до 11 пикселей,
    и от строки оставалась одна галочка без названия."""
    for k in ("fuel", "standings", "laplog"):
        panel._favs[k].setChecked(True)
    assert panel._fav_box.minimumHeight() >= 3 * 26
    for i in range(panel._fav_lay.count()):
        row = panel._fav_lay.itemAt(i).widget()
        assert row.minimumHeight() >= 26


def test_long_value_shrinks_instead_of_leaving_the_widget(panel):
    """Строка шире виджета уезжала за левый край и наползала на соседнюю.

    В «Front/rear balance» подсказка «softer front / more rear wing» не
    помещалась в 240 пикселей: text_right считает x = правый край минус
    ширина строки, уходил в минус, и Qt честно рисовал текст за границей.
    Проверяем на самом узком случае — что рисовать начинают внутри виджета.
    """
    from PySide6.QtGui import QPainter

    from overlay.widgets import BalanceWidget

    class Narrow(BalanceWidget):
        def rows(self):
            return [("Try", "softer front / more rear wing", "#9099a6")]

    from PySide6.QtGui import QFontMetrics

    w = Narrow(panel.store, panel.config)
    w.resize(240, 150)
    fm = QFontMetrics(w._font_for("Try", 14, True))
    assert fm.horizontalAdvance("softer front / more rear wing") > 240 - 24, \
        "тест потерял смысл: строка перестала быть длинной"

    pix = QPixmap(240, 150)          # держим ссылку: без неё Qt рисует в мусор
    p = QPainter(pix)
    w.draw(p)
    p.end()

    assert w._elrects, "строка не отрисовалась"
    for _, rect in w._elrects:
        assert rect.left() >= 0, "текст начинается за левым краем виджета"
        assert rect.right() <= w.width() + 1, "текст уходит за правый край"


def test_reset_button_returns_the_widget_to_factory(panel):
    """Накликанное оформление откатить было нечем — только руками в JSON."""
    panel.select("fuel")
    panel.config.set_widget_opt("fuel", "bg", 0.15)
    panel.config.set_geometry("fuel", 900, 40, 640, 480)

    assert panel.reset_selected(confirm=False) is True
    assert panel.config.widget_opt("fuel", "bg") is None
    assert panel.config.geometry("fuel") is None
    # предпросмотр пересобран и снова показывает тот же виджет
    assert panel.preview._widget is not None
    assert panel.preview._cls.KEY == "fuel"


def test_reset_does_not_touch_the_neighbours(panel):
    panel.config.set_widget_opt("delta", "bg", 0.9)
    panel.select("fuel")
    panel.config.set_widget_opt("fuel", "bg", 0.15)
    panel.reset_selected(confirm=False)
    assert panel.config.widget_opt("delta", "bg") == 0.9


def test_layout_travels_to_another_config_through_a_file(panel, tmp_path):
    """То, ради чего экспорт и делался: перенос настроенной раскладки."""
    from overlay.config import Config

    panel.config.set_enabled("fuel", True)
    panel.config.set_geometry("fuel", 12, 34, 230, 220)
    panel.config.set_favourite("standings", True)
    out = tmp_path / "trip.json"
    panel.config.export_layout(str(out))

    other = Config(str(tmp_path / "other.json"))
    other.import_layout(str(out))
    assert other.is_enabled("fuel")
    assert other.geometry("fuel") == (12, 34, 230, 220)
    assert other.is_favourite("standings")


def test_reset_shrinks_the_live_overlay_too(panel):
    """Сброс должен доехать до окна поверх игры, а не только до конфига.

    Иначе виджет остаётся растянутым до перезапуска, и кнопка выглядит
    сломанной: цвета вернулись, рамка — нет.
    """
    cls = panel._cls_by_key["fuel"]
    panel.select("fuel")
    panel.toggle(cls, True)
    live = panel.widgets["fuel"]
    panel.config.set_geometry("fuel", 50, 50, 700, 500)
    live.resize(700, 500)

    panel.reset_selected(confirm=False)
    assert live.size().toTuple() == tuple(cls.DEFAULT)
    assert panel.config.geometry("fuel") is None, "геометрия записалась обратно"


def test_reset_all_backs_up_before_wiping(panel):
    """Кнопка стирает работу вечера одним нажатием — копия не опция."""
    import pathlib as _p

    from overlay.config import Config

    panel.config.set_enabled("fuel", True)
    panel.config.set_widget_opt("fuel", "bg", 0.2)
    panel.config.set_widget_opt("delta", "bg", 0.3)
    panel.config.set_geometry("fuel", 5, 6, 700, 500)
    panel.config.set_opacity(0.5)

    assert panel.reset_all(confirm=False) is True
    assert panel.config.widget_opt("fuel", "bg") is None
    assert panel.config.widget_opt("delta", "bg") is None
    assert panel.config.opacity() == 1.0
    assert panel.op.value() == 100                    # ползунок тоже вернулся

    backups = sorted((_p.Path(panel.config.path).parent
                      / Config.BACKUP_DIR).glob("*.json"))
    assert backups, "копии не осталось — откатиться было бы нечем"
    back = Config(str(_p.Path(panel.config.path).parent / "restored.json"))
    back.import_layout(str(backups[-1]))
    assert back.widget_opt("fuel", "bg") == 0.2       # из копии всё достаётся


def test_closing_the_panel_leaves_a_snapshot(app, tmp_path):
    """Конфиг перезаписывается на каждое движение ползунка: «вчерашнего»
    состояния нигде не было."""
    import pathlib as _p

    from overlay.config import Config

    cfg = Config(str(tmp_path / "cfg.json"))
    p = ControlPanel(Store(), cfg, WIDGETS)
    cfg.set_widget_opt("fuel", "bg", 0.42)
    p.close()
    backups = sorted((_p.Path(cfg.path).parent / Config.BACKUP_DIR).glob("*.json"))
    assert backups
    back = Config(str(tmp_path / "back.json"))
    back.import_layout(str(backups[-1]))
    assert back.widget_opt("fuel", "bg") == 0.42
