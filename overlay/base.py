"""Базовый прозрачный виджет-оверлей поверх iRacing.

Каждый виджет: без рамки, полупрозрачный фон, always-on-top, не крадёт фокус.
Перетаскивается мышью, тянется за нижний-правый угол; позиция сохраняется в
Config. В режиме «блокировка» клики проходят сквозь виджет в игру (не мешают
в гонке). Наследники переопределяют draw(painter).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

HANDLE = 16


def lap_time(sec):
    if not isinstance(sec, (int, float)) or sec <= 0:
        return "—"
    m = int(sec // 60)
    return f"{m}:{sec - m*60:05.2f}"


class OverlayWidget(QWidget):
    KEY = "base"
    TITLE = "Виджет"
    DEFAULT = (300, 160)
    ENDPOINTS = ()          # какие /api/* нужны этому виджету (для точечного опроса)

    def __init__(self, store, config):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.store = store
        self.config = config
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(120, 60)
        geo = config.geometry(self.KEY)
        if geo:
            self.setGeometry(*geo)
        else:
            self.resize(*self.DEFAULT)
            self.move(80, 80)
        self._drag = None
        self._resize = None
        self._eased = {}
        self.apply_lock()

    def ease(self, key, target, alpha=0.3):
        """Плавно «доводит» показываемое значение к target каждый кадр (мягкое движение).
        Нечисловые значения возвращаются как есть."""
        if not isinstance(target, (int, float)):
            return target
        cur = self._eased.get(key)
        cur = target if cur is None else cur + (target - cur) * alpha
        self._eased[key] = cur
        return cur

    def apply_lock(self):
        # блокировка → клики проходят сквозь виджет в игру
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.config.locked())

    # ---------- помощники отрисовки (для наследников) ----------
    def _bg(self, p):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(13, 15, 18, 200))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)

    def text(self, p, x, y, s, color="#e8eaed", size=12, bold=False):
        f = QFont("Segoe UI", size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QPen(QColor(color)))
        p.drawText(int(x), int(y), str(s))

    def text_center(self, p, s, color, size, y=None, bold=True):
        f = QFont("Segoe UI", size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QPen(QColor(color)))
        r = QRectF(0, 0, self.width(), self.height()) if y is None else QRectF(0, y - size, self.width(), size * 1.6)
        p.drawText(r, Qt.AlignCenter, str(s))

    def bar(self, p, x, y, w, h, frac, color):
        frac = max(0.0, min(1.0, frac or 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 12, 15))
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(x, y, w * frac, h), h / 2, h / 2)

    def title(self, p, name):
        self.text(p, 12, 20, name, "#9099a6", 8, True)

    # ---------- отрисовка ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._bg(p)
        try:
            self.draw(p)
        except Exception:
            pass
        if not self.config.locked():                       # уголок для ресайза
            p.setPen(QPen(QColor(90, 107, 122)))
            for i in (4, 8, 12):
                p.drawLine(self.width() - i, self.height() - 3, self.width() - 3, self.height() - i)

    def draw(self, p):
        """Переопределяется в наследниках."""

    # ---------- взаимодействие ----------
    def _in_handle(self, pos):
        return pos.x() >= self.width() - HANDLE and pos.y() >= self.height() - HANDLE

    def mousePressEvent(self, e):
        if self.config.locked() or e.button() != Qt.LeftButton:
            return
        if self._in_handle(e.position().toPoint()):
            self._resize = (e.globalPosition().toPoint(), self.width(), self.height())
        else:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._resize is not None:
            start, w0, h0 = self._resize
            d = e.globalPosition().toPoint() - start
            self.resize(max(120, w0 + d.x()), max(60, h0 + d.y()))
        elif self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = self._resize = None
        g = self.geometry()
        self.config.set_geometry(self.KEY, g.x(), g.y(), g.width(), g.height())
