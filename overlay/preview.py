"""Живой предпросмотр оверлея внутри окна настроек.

Раньше настроить виджет можно было только вслепую: покрутил ползунок в панели
и полез в игру смотреть, что вышло. RaceLab решает это иначе — в центре окна
показан сам оверлей на фоне трассы, и он меняется прямо во время правки.

Здесь то же самое, но со своим отличием: фон рисуется, а не подгружается
картинкой. Причина простая — картинку трассы пришлось бы где-то взять и
положить в репозиторий, а нарисованный фон весит ноль, работает без файлов
и не спорит ни с чьими правами. Задача фона одна: показать, читается ли
виджет поверх неоднородной картинки, а не быть красивым пейзажем.

Виджет в предпросмотре — НАСТОЯЩИЙ экземпляр того же класса, с тем же
хранилищем и тем же конфигом. Значит он берёт живые данные из сима и
мгновенно отзывается на любую настройку: никакой отдельной «модели
предпросмотра», которая рано или поздно разъедется с оригиналом.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QTimer, QPointF
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

BACKDROPS = [
    # (подпись, небо сверху, небо снизу, полотно, обочина)
    ("Закат", "#2b3a55", "#c96f3f", "#2a2d33", "#3d4a35"),
    ("День", "#4a7fb5", "#a9c8e8", "#33363c", "#41582f"),
    ("Ночь", "#0b1020", "#1a2440", "#202329", "#1d2a1b"),
    ("Дождь", "#3b4450", "#6c7683", "#3a3f47", "#2f3a2c"),
]


class PreviewCanvas(QWidget):
    """Холст с нарисованной трассой и живым виджетом поверх."""

    FPS = 30

    def __init__(self, store, config, parent=None):
        super().__init__(parent)
        self.store = store
        self.config = config
        self._widget = None
        self._cls = None
        self._bg = 0
        self._zoom = 1.0
        self.setMinimumSize(420, 300)

        # Перерисовка по таймеру: виджет читает store сам, но сам себя не
        # обновляет — в бою это делает цикл оверлея, здесь его нет.
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._t.start(int(1000 / self.FPS))

    # ---------- управление ----------
    def show_widget(self, cls):
        """Показать другой виджет. Старый экземпляр уничтожается."""
        if self._widget is not None:
            self._widget.setParent(None)
            self._widget.deleteLater()
            self._widget = None
        self._cls = cls
        if cls is not None:
            self._widget = cls(self.store, self.config, parent=self)
            self._widget.show()
        self._place()
        self.update()

    def set_backdrop(self, i):
        self._bg = i % len(BACKDROPS)
        self.update()

    def set_zoom(self, z):
        self._zoom = max(0.5, min(2.0, z))
        self._place()

    def refresh(self):
        """Позвать после смены настроек — размер виджета мог измениться."""
        self._place()
        if self._widget is not None:
            self._widget.update()

    # ---------- внутреннее ----------
    def _tick(self):
        if self._widget is not None and self.isVisible():
            self._widget.update()

    def _place(self):
        """Виджет по центру холста, в своём настоящем размере."""
        if self._widget is None:
            return
        w, h = self._cls.DEFAULT
        geo = self.config.geometry(self._cls.KEY)
        if geo:
            w, h = geo[2], geo[3]                # показываем размер как в бою
        w, h = int(w * self._zoom), int(h * self._zoom)
        w = min(w, max(120, self.width() - 24))
        h = min(h, max(60, self.height() - 24))
        self._widget.setGeometry((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        _, sky_top, sky_bot, road, grass = BACKDROPS[self._bg]
        horizon = H * 0.42

        g = QLinearGradient(0, 0, 0, horizon)
        g.setColorAt(0.0, QColor(sky_top))
        g.setColorAt(1.0, QColor(sky_bot))
        p.fillRect(QRectF(0, 0, W, horizon), g)
        p.fillRect(QRectF(0, horizon, W, H - horizon), QColor(grass))

        # Полотно трассы: трапеция в перспективе. Точные пропорции не важны,
        # важно, что под виджетом есть и светлое, и тёмное — на однородном
        # фоне не видно, читается ли текст.
        road_top, road_bot = W * 0.16, W * 1.5
        path = [QPointF((W - road_top) / 2, horizon), QPointF((W + road_top) / 2, horizon),
                QPointF((W + road_bot) / 2, H), QPointF((W - road_bot) / 2, H)]
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(road))
        p.drawPolygon(path)

        p.setPen(QPen(QColor(255, 255, 255, 70), 3))         # разметка по центру
        for i in range(7):
            t0, t1 = i / 7.0, i / 7.0 + 0.05
            y0, y1 = horizon + (H - horizon) * t0 ** 2, horizon + (H - horizon) * t1 ** 2
            p.drawLine(QPointF(W / 2, y0), QPointF(W / 2, y1))

        p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, 28))  # лёгкое затемнение

        if self._widget is None:
            f = QFont("Segoe UI")
            f.setPixelSize(14)
            p.setFont(f)
            p.setPen(QPen(QColor("#cdd3dc")))
            p.drawText(QRectF(0, 0, W, H), Qt.AlignCenter,
                       "Выберите оверлей слева")
            return

        # Рамка вокруг виджета: без неё непонятно, где его границы —
        # фон полупрозрачный и края теряются.
        r = self._widget.geometry()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(62, 166, 255, 90), 1, Qt.DashLine))
        p.drawRect(QRectF(r.x() - 1, r.y() - 1, r.width() + 2, r.height() + 2))

        f = QFont("Segoe UI")
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QPen(QColor(160, 170, 185)))
        p.drawText(QRectF(8, H - 22, W - 16, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{r.width()}×{r.height()} пикселей"
                   f"  ·  фон: {BACKDROPS[self._bg][0]}")
