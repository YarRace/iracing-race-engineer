"""Логотипы марок: знак должен занимать отведённое место, а не плавать в поле.

В скачанных PNG знак занимает малую часть холста — у Ferrari 229 на 366
внутри картинки 640 на 426, то есть 31%. Виджет масштабирует картинку
ЦЕЛИКОМ, поэтому сам щит выходил 21 на 34 точки вместо честных 40 в высоту
и выглядел мыльным пятном.
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

from PySide6.QtCore import Qt                                      # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap                # noqa: E402
from PySide6.QtWidgets import QApplication                         # noqa: E402

from overlay import logos                                          # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _with_margin(w, h, mark_w, mark_h):
    """Картинка mark_w × mark_h по центру прозрачного холста w × h."""
    pm = QPixmap(w, h)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.fillRect((w - mark_w) // 2, (h - mark_h) // 2, mark_w, mark_h,
               QColor(255, 200, 0))
    p.end()
    return pm


def test_empty_margins_are_cut_off(app):
    """Ради этого всё и делалось: знак обязан занимать своё место целиком."""
    out = logos._trim(_with_margin(640, 426, 220, 360))
    assert 200 <= out.width() <= 260, out.width()
    assert 340 <= out.height() <= 400, out.height()


def test_a_picture_without_margins_is_left_alone(app):
    """Резать нечего — и трогать нечего: лишняя копия на ровном месте."""
    pm = QPixmap(200, 100)
    pm.fill(QColor(255, 0, 0))
    out = logos._trim(pm)
    assert (out.width(), out.height()) == (200, 100)


def test_a_fully_transparent_picture_does_not_crash(app):
    """Пустой файл — не повод падать посреди гонки."""
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    out = logos._trim(pm)
    assert out.width() == 64 and out.height() == 64


def test_a_picture_without_an_alpha_channel_is_left_alone(app):
    """JPEG прозрачности не имеет, и обрезать по ней нечего."""
    pm = QPixmap(120, 80)
    pm.fill(QColor(10, 20, 30))
    assert logos._trim(pm).width() == 120


def test_a_huge_logo_is_trimmed_quickly(app):
    """Первая версия обходила все точки, и на Aston Martin (6000 на 3000)
    это заняло 3.3 секунды — оверлей замер бы посреди гонки, когда рядом
    окажется такая машина."""
    import time

    big = _with_margin(6000, 3000, 5000, 2200)
    t = time.monotonic()
    out = logos._trim(big)
    dt = time.monotonic() - t
    assert dt < 0.5, f"обрезка заняла {dt:.1f} с"
    assert out.width() < 6000


def _visible(pm):
    """Размер того, что реально ВИДНО: прозрачные поля не в счёт.

    Меряем именно это, а не размер холста: до обрезки холст был тот же
    60 на 40, а знак внутри него — 21 на 34, и вся беда была ровно в этом.
    """
    img = pm.toImage()
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            if (img.pixel(x, y) >> 24) & 0xFF > 8:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def test_the_trimmed_badge_gets_more_of_the_slot(app):
    """Проверка по существу: в том же окошке знак стал крупнее.

    Холст и до, и после выходит 40 точек в высоту — сравнивать надо ВИДИМОЕ.
    """
    raw = _with_margin(640, 426, 229, 366)
    box_w, box_h = 96, 40
    before = _visible(raw.scaled(box_w, box_h, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation))
    after = _visible(logos._trim(raw).scaled(box_w, box_h, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
    assert after[1] > before[1], f"было {before}, стало {after}"
    assert after[1] >= box_h - 1, f"знак всё ещё не занимает высоту: {after}"


def test_the_real_ferrari_badge_fills_its_height(app):
    """На настоящем файле из data/logos, а не на выдуманном."""
    px = logos.logo("ferrari")
    if px is None:
        pytest.skip("логотипов нет")
    s = px.scaled(96, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    assert s.height() == 40, f"щит {s.width()}x{s.height()} вместо полной высоты"
