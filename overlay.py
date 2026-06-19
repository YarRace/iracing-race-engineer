#!/usr/bin/env python3
"""Прозрачный оверлей Race Engineer поверх iRacing (как Kapps, но наш).

Берёт данные из нашего дашборда (localhost:8000/api/*) и рисует их компактной
полупрозрачной панелью поверх игры. Перетаскивается мышью. Always-on-top.

Запуск: python overlay.py  (нужен запущенный run.py — дашборд-сервер).
ВАЖНО: iRacing должен быть в режиме «окно без рамки»/оконном (не эксклюзивный
полный экран), иначе оверлей поверх игры не покажется.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import httpx
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

DASH = "http://localhost:8000"


def lap_time(sec):
    if sec is None:
        return "—"
    try:
        sec = float(sec)
    except Exception:
        return "—"
    m = int(sec // 60)
    return f"{m}:{sec - m*60:05.2f}"


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(300, 196)
        self.move(40, 40)
        self.data = {"live": {}, "race": {}, "strategy": {}}
        self._drag = None
        t = QTimer(self)
        t.timeout.connect(self.poll)
        t.start(250)

    def poll(self):
        for ep in ("live", "race", "strategy"):
            try:
                self.data[ep] = httpx.get(f"{DASH}/api/{ep}", timeout=0.4).json()
            except Exception:
                pass
        self.update()

    # перетаскивание окна мышью
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            QApplication.quit()

    def paintEvent(self, e):
        live = self.data.get("live") or {}
        race = self.data.get("race") or {}
        strat = self.data.get("strategy") or {}
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(13, 15, 18, 190))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)

        white = QColor("#e8eaed")
        muted = QColor("#9099a6")
        green = QColor("#2ecc71")
        red = QColor("#e74c3c")
        amber = QColor("#f1c40f")

        # споттер: полосы по бокам
        lr = race.get("car_left_right") or 0
        if lr in (1, 3, 4):
            p.setBrush(amber); p.drawRoundedRect(QRectF(0, 30, 6, self.height()-60), 3, 3)
        if lr in (2, 3, 5):
            p.setBrush(amber); p.drawRoundedRect(QRectF(self.width()-6, 30, 6, self.height()-60), 3, 3)

        def text(x, y, s, color=white, size=13, bold=False):
            f = QFont("Segoe UI", size)
            f.setBold(bold)
            p.setFont(f)
            p.setPen(QPen(color))
            p.drawText(x, y, s)

        # скорость + передача
        spd = live.get("speed")
        kmh = round(spd*3.6) if isinstance(spd, (int, float)) else "—"
        g = live.get("gear")
        gear = ("N" if g == 0 else ("R" if g == -1 else g)) if g is not None else "—"
        text(16, 44, f"{kmh}", white, 30, True)
        text(95, 44, "км/ч", muted, 11)
        text(self.width()-58, 44, f"{gear}", white, 30, True)

        # дельта к лучшему + прогноз круга
        d = race.get("delta_best")
        if isinstance(d, (int, float)):
            text(16, 78, f"Δ {d:+.2f}", green if d <= 0 else red, 15, True)
        text(self.width()-150, 78, f"круг {lap_time(race.get('predicted'))}", muted, 12)

        # топливо
        fuel = strat.get("fuel")
        add = strat.get("fuel_to_add")
        text(16, 108, f"Топливо {fuel if fuel is not None else '—'} л", white, 13)
        if isinstance(add, (int, float)) and add > 0:
            text(170, 108, f"долить +{add}", amber, 13, True)

        # осталось на баке
        lof = strat.get("laps_on_fuel")
        if lof is not None:
            text(16, 130, f"хватит на {lof} кр.", muted, 12)

        # позиция + разрывы
        pos = race.get("position")
        if pos:
            text(16, 164, f"P{pos}", white, 18, True)
            sa = race.get("standing_ahead"); sb = race.get("standing_behind")
            text(70, 164, f"▲ {sa if sa is not None else '—'}   ▼ {sb if sb is not None else '—'}", muted, 13)

        # флаг (если активен)
        flags = race.get("flags") or []
        if flags:
            text(16, 186, flags[0].get("label", ""), amber, 12, True)
        else:
            text(16, 186, "перетащи мышью · Esc — выход", muted, 10)


def main():
    app = QApplication(sys.argv)
    w = Overlay()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
