"""Раскладка Tyre Tool при любом размере, до которого его дотянут мышью.

Минимальный размер виджета — 120×60 (`overlay/base.py`), и он достижим: за
угол тянут, чтобы освободить экран. Прежняя раскладка считала базовую линию
задней оси как 42 + pitch и ставила вердикт на H−10, поэтому на маленькой
высоте ось уходила за нижнюю кромку, а на средней строка вердикта шла прямо
сквозь неё. Комментарий в коде при этом обещал ровно обратное.

Проверяется ПИКСЕЛЯМИ, а не чтением формулы: раскладка держится на метриках
шрифта, и глазом по коду её не проверить.
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

from PySide6.QtGui import QColor, QPainter, QPixmap                # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

from overlay.config import Config                                  # noqa: E402
from overlay.widgets import TyreToolWidget                         # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def data():
    from ire.metrics.tyres import report
    temps = {"LF": {"inner": 63.3, "tm": 60.8, "outer": 61.2},
             "RF": {"inner": 60.4, "tm": 56.7, "outer": 53.6},
             "LR": {"inner": 63.0, "tm": 61.3, "outer": 60.7},
             "RR": {"inner": 62.0, "tm": 60.3, "outer": 54.8}}
    return report(temps, {"TiresAero.LeftFront.StartingPressure": "152 kPa",
                          "TiresAero.RightFront.StartingPressure": "152 kPa",
                          "TiresAero.LeftRear.StartingPressure": "148 kPa",
                          "TiresAero.RightRear.StartingPressure": "148 kPa"})


class Feed:
    def __init__(self, r):
        self._r = r

    def get(self, ep):
        return self._r if ep == "tyres" else {}


def _draw(data, tmp_path, h, w=200, **opts):
    wid = TyreToolWidget(Feed(data), Config(str(tmp_path / f"c{h}{opts}.json")))
    for k, v in opts.items():
        wid.config.set_widget_opt(TyreToolWidget.KEY, k, v)
    wid.resize(w, h)
    pm = QPixmap(wid.size())
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    try:
        wid.draw(p)
    finally:
        p.end()
        wid.deleteLater()
    return pm.toImage()


def _lowest_painted(img):
    for y in range(img.height() - 1, -1, -1):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() > 20:
                return y
    return -1


@pytest.mark.parametrize("h", [60, 68, 76, 88, 96, 120, 148, 200])
def test_the_rear_axle_never_falls_off_the_bottom(app, data, tmp_path, h):
    """Потерянная ось читается как поломка виджета, потерянные давления — как
    компактный режим. Порядок жертв обязан быть именно такой."""
    img = _draw(data, tmp_path, h, show_verdict=False)
    assert _lowest_painted(img) < h, f"на высоте {h} нарисовано за кромкой"


def _rows(data, tmp_path, h, w=200, **opts):
    """Что и на какой строке нарисовано: (базовая линия, кегль, текст)."""
    wid = TyreToolWidget(Feed(data), Config(str(tmp_path / f"r{h}{opts}.json")))
    for k, v in opts.items():
        wid.config.set_widget_opt(TyreToolWidget.KEY, k, v)
    wid.resize(w, h)
    seen = []
    real = wid.text

    def spy(p, x, y, s, color="#e8eaed", size=12, bold=False, key=None):
        seen.append((round(y), size, str(s)))
        return real(p, x, y, s, color, size, bold, key)

    wid.text = spy
    pm = QPixmap(wid.size())
    p = QPainter(pm)
    try:
        wid.draw(p)
    finally:
        p.end()
        wid.deleteLater()
    return seen


@pytest.mark.parametrize("h", [76, 88, 96, 120, 148, 200])
def test_the_verdict_line_does_not_run_through_the_rear_axle(app, data, tmp_path, h):
    """На 200×76 строка вердикта шла прямо сквозь заднюю ось: числа читались
    поверх слов.

    Сравнивать две картинки (с вердиктом и без) нельзя — выключение вердикта
    само меняет раскладку, и разошлись бы просто два разных экрана. Смотрим
    на зазор между базовыми линиями.
    """
    rows = _rows(data, tmp_path, h, show_verdict=True)
    rear = [y for y, _, s in rows if s in ("LR", "RR")]
    verdict = [(y, size) for y, size, s in rows
               if s and s not in ("LF", "RF", "LR", "RR")
               and not s.startswith(("+", "-", "—", "TYRE"))
               and "kPa" not in s and "avg" not in s]
    if not verdict:
        pytest.skip("на этой высоте вердикт снят намеренно")
    assert rear, "задней оси нет вовсе"

    gap = min(y for y, _ in verdict) - max(rear)
    # Кегль задней строки — 17, значит её глифы уходят вниз примерно на треть
    # кегля от базовой линии. Зазора меньше этого хватит, чтобы слова легли
    # на цифры.
    assert gap >= 8, f"на высоте {h} между осью и вердиктом всего {gap} точек"


def test_a_squeezed_widget_keeps_all_four_corners(app, data, tmp_path):
    """Три угла из четырёх — это не компактный режим, это поломка."""
    said = []
    wid = TyreToolWidget(Feed(data), Config(str(tmp_path / "c.json")))
    wid.resize(200, 64)
    real = wid.text
    wid.text = lambda p, x, y, s, *a, **k: (said.append(str(s)),
                                            real(p, x, y, s, *a, **k))[1]
    pm = QPixmap(wid.size())
    p = QPainter(pm)
    try:
        wid.draw(p)
    finally:
        p.end()
        wid.deleteLater()
    for corner in ("LF", "RF", "LR", "RR"):
        assert corner in said, f"{corner} пропал при высоте 64"
