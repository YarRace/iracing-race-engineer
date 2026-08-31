"""Виджет секторов: отставание видно в круге, а не в итогах заезда.

Проверяется то, что ломается молча, — какие СТРОКИ виджет рисует. Виджет,
который «не упал», но нарисовал пустоту, читается как сломанная программа,
и поймать это можно только глядя на вывод.
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

from PySide6.QtGui import QPainter, QPixmap                         # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

from overlay.config import Config                                   # noqa: E402
from overlay.widgets import SectorWidget                            # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class Feed:
    def __init__(self, sectors):
        self._s = sectors

    def get(self, ep):
        return {"sectors": self._s} if ep == "race" else {}


MID_LAP = {"count": 3, "now": 2, "elapsed": 12.68,
           "cur": [32.76, 32.32, None], "ref": [33.10, 32.20, 26.70],
           "best": [32.90, 32.20, 26.70],
           "delta": [-0.34, 0.12, None], "record": [True, False, False],
           "have_ref": True}


def drawn(app, tmp_path, sectors, **opts):
    """Что виджет реально вывел: список строк в порядке отрисовки."""
    w = SectorWidget(Feed(sectors), Config(str(tmp_path / "c.json")))
    for k, v in opts.items():
        w.config.set_widget_opt(SectorWidget.KEY, k, v)
    w.resize(*SectorWidget.DEFAULT)

    said = []
    real_text, real_right = w.text, w.text_right
    w.text = lambda p, x, y, s, *a, **k: (said.append(str(s)), real_text(p, x, y, s, *a, **k))[1]
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


def test_a_finished_sector_shows_its_delta_mid_lap(app, tmp_path):
    """Ради этого виджет и делался: цифра стоит на месте с границы сектора,
    и прочесть её можно на прямой."""
    said = drawn(app, tmp_path, MID_LAP)
    assert "-0.34" in said and "+0.12" in said


def test_the_sector_you_are_in_shows_the_running_time_not_a_blank(app, tmp_path):
    """Иначе виджет оживал бы только на границе сектора и стоял мёртвым всю
    прямую — ровно там, где на него смотрят."""
    said = drawn(app, tmp_path, MID_LAP)
    assert "12.68" in said, "время в текущем секторе не показано"
    assert "on it" in said


def test_a_track_without_sectors_says_so_instead_of_going_blank(app, tmp_path):
    """Пустой виджет читается как поломка. Трасса без разметки — не поломка."""
    said = drawn(app, tmp_path, {})
    assert any("no sectors" in s for s in said)


def test_the_first_lap_says_there_is_nothing_to_compare_with_yet(app, tmp_path):
    v = dict(MID_LAP, delta=[None, None, None], have_ref=False,
             record=[False, False, False])
    said = drawn(app, tmp_path, v)
    assert any("no full lap" in s for s in said)


def test_turning_off_the_times_leaves_the_deltas(app, tmp_path):
    """Две настройки — две разные вещи. Выключив времена, человек не должен
    потерять то, ради чего виджет стоит на экране."""
    said = drawn(app, tmp_path, MID_LAP, show_times=False)
    assert "32.76" not in said
    assert "-0.34" in said


def test_a_missing_field_does_not_take_the_widget_down(app, tmp_path):
    """Сервер отдал полуготовый ответ — виджет обязан пережить это молча:
    он рисуется шестьдесят раз в секунду посреди гонки."""
    said = drawn(app, tmp_path, {"count": 3})
    assert said, "виджет не нарисовал ничего вовсе"
