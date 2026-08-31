"""Tyre Tool в оверлее: развал по кромкам, не выходя из машины.

Проверяется то, что ломается молча, — какие СТРОКИ виджет рисует. Виджет,
который «не упал», но нарисовал пустоту, читается как сломанная программа,
и поймать это можно только глядя на вывод.

Числа настоящие: так Road America выглядит в его телеметрии.
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

from PySide6.QtGui import QPainter, QPixmap                        # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

from overlay.config import Config                                  # noqa: E402
from overlay.widgets import TyreToolWidget, _tyre_todo_line        # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Feed:
    def __init__(self, tyres):
        self._t = tyres

    def get(self, ep):
        return self._t if ep == "tyres" else {}


def _report(**over):
    from ire.metrics.tyres import report
    temps = {"LF": {"inner": 63.3, "tm": 60.8, "outer": 61.2},
             "RF": {"inner": 60.4, "tm": 56.7, "outer": 53.6},
             "LR": {"inner": 63.0, "tm": 61.3, "outer": 60.7},
             "RR": {"inner": 62.0, "tm": 60.3, "outer": 54.8},
             "front_rear_balance": -1.0}
    r = report(temps, {"TiresAero.LeftFront.StartingPressure": "152 kPa",
                       "TiresAero.RightFront.StartingPressure": "152 kPa",
                       "TiresAero.LeftRear.StartingPressure": "148 kPa",
                       "TiresAero.RightRear.StartingPressure": "148 kPa"})
    r.update(over)
    return r


def drawn(app, tmp_path, tyres, size=None, **opts):
    """Что виджет реально вывел: список строк в порядке отрисовки."""
    w = TyreToolWidget(Feed(tyres), Config(str(tmp_path / "c.json")))
    for k, v in opts.items():
        w.config.set_widget_opt(TyreToolWidget.KEY, k, v)
    w.resize(*(size or TyreToolWidget.DEFAULT))

    said = []
    real_text, real_right = w.text, w.text_right
    w.text = lambda p, x, y, s, *a, **k: (said.append(str(s)),
                                          real_text(p, x, y, s, *a, **k))[1]
    w.text_right = lambda p, x, y, s, *a, **k: (said.append(str(s)),
                                                real_right(p, x, y, s, *a, **k))[1]
    pm = QPixmap(w.size())
    p = QPainter(pm)
    try:
        w.draw(p)
    finally:
        p.end()
        w.deleteLater()
    return said


# ── то, ради чего виджет и делался ──────────────────────────────────────────

def test_every_corner_shows_its_camber_with_a_sign(app, tmp_path):
    """Знак важнее числа: он говорит, в какую сторону крутить."""
    said = drawn(app, tmp_path, _report())
    assert "+6.8°" in said and "+7.2°" in said
    assert "+2.1°" in said and "+2.3°" in said


def test_the_change_to_make_is_said_in_words(app, tmp_path):
    """Цифры на четырёх углах ещё надо сложить в голове на скорости 250."""
    said = drawn(app, tmp_path, _report())
    assert any("too much camber" in s for s in said)


def test_nothing_to_change_is_said_out_loud(app, tmp_path):
    """Молчание читается как поломка виджета, а не как «всё хорошо»."""
    even = {c: {"inner": 60.0, "tm": 60.0, "outer": 60.0}
            for c in ("LF", "RF", "LR", "RR")}
    from ire.metrics.tyres import report
    said = drawn(app, tmp_path, report(even))
    assert any("nothing to change" in s for s in said)


def test_the_average_temperature_is_shown_next_to_the_verdict(app, tmp_path):
    """На холодной резине кромки сходятся в ноль, и «менять нечего» тогда
    читается как «сетап хорош». Число рядом снимает обман."""
    said = drawn(app, tmp_path, _report())
    assert any("avg" in s for s in said)


# ── отказы ──────────────────────────────────────────────────────────────────

def test_a_refusal_is_explained_rather_than_left_blank(app, tmp_path):
    """«Машина не выезжала» и «нет температур» — разные вещи, и во втором
    случае человек пойдёт искать поломку там, где её нет."""
    said = drawn(app, tmp_path, {"ok": False,
                                 "reason": "the car barely moved in this session — "
                                           "the tyre edges say nothing yet"})
    joined = " ".join(said)
    assert "barely moved" in joined
    assert len(said) > 1, "длинная причина не перенесена по словам"


def test_no_report_at_all_still_says_something(app, tmp_path):
    said = drawn(app, tmp_path, {})
    assert any("no tyre report" in s for s in said)


def test_a_half_built_answer_does_not_take_the_widget_down(app, tmp_path):
    """Сервер отдал недоделанный ответ — виджет рисуется шестьдесят раз в
    секунду посреди гонки и падать не должен."""
    assert drawn(app, tmp_path, {"ok": True, "corners": {}})


# ── настройки и размер ──────────────────────────────────────────────────────

def test_turning_pressures_off_keeps_the_camber(app, tmp_path):
    """Две настройки — две разные вещи. Выключив давления, человек не должен
    потерять то, ради чего виджет стоит на экране."""
    said = drawn(app, tmp_path, _report(), show_pressure=False)
    assert "152 kPa" not in said
    assert "+6.8°" in said


def test_a_squeezed_widget_drops_the_pressures_not_the_rear_axle(app, tmp_path):
    """Потерянная ось выглядит как поломка, потерянные давления — как
    компактный режим."""
    said = drawn(app, tmp_path, _report(), size=(250, 96))
    assert "LR" in said and "RR" in said, "задняя ось пропала"
    assert "148 kPa" not in said


def test_a_car_that_hides_its_pressures_says_so_once(app, tmp_path):
    """Пустое место под цифрой выглядит как недогруженные данные."""
    from ire.metrics.tyres import report
    temps = {"LF": {"inner": 63.3, "tm": 60.8, "outer": 61.2},
             "RF": {"inner": 60.4, "tm": 56.7, "outer": 53.6},
             "LR": {"inner": 63.0, "tm": 61.3, "outer": 60.7},
             "RR": {"inner": 62.0, "tm": 60.3, "outer": 54.8}}
    said = drawn(app, tmp_path, report(temps))
    assert sum(1 for s in said if "no pressures" in s) == 1


# ── строка правки ───────────────────────────────────────────────────────────

def test_two_corners_of_one_axle_are_named_together():
    """Два одинаковых угла — это про ось, и решать их надо вместе."""
    assert _tyre_todo_line([{"corner": "RF", "what": "camber", "delta": 6.8},
                            {"corner": "RR", "what": "camber", "delta": 7.2}]) \
        == "RF/RR: too much camber"


def test_the_rest_are_counted_not_dropped():
    """Показать одну правку и молча съесть остальные — значит соврать."""
    line = _tyre_todo_line([{"corner": "RF", "what": "camber", "delta": 6.8},
                            {"corner": "RR", "what": "camber", "delta": 7.2},
                            {"corner": "LF", "what": "pressure", "delta": 3.0}])
    assert line == "RF/RR: too much camber  +1 more"


def test_an_empty_list_is_not_a_line():
    assert _tyre_todo_line([]) is None
    assert _tyre_todo_line(None) is None


def test_a_verdict_without_a_number_is_skipped_rather_than_guessed():
    assert _tyre_todo_line([{"corner": "LF", "what": "camber", "delta": None}]) is None


# ── связь с данными ─────────────────────────────────────────────────────────

def test_the_widget_asks_for_the_endpoint_that_actually_feeds_it():
    """Без этого виджет молча стоял бы пустым: панель опрашивает объединение
    ENDPOINTS по включённым виджетам."""
    assert TyreToolWidget.ENDPOINTS == ("tyres",)


def test_the_tyres_endpoint_is_not_polled_at_full_rate():
    """Свод по шинам пересчитывается раз в круг: спрашивать его двадцать раз
    в секунду значит отбирать процессор у сима без всякой пользы."""
    from overlay.store import ENDPOINTS, SLOW
    assert "tyres" in ENDPOINTS
    assert SLOW.get("tyres", 0) >= 1.0
