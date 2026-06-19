#!/usr/bin/env python3
"""Оверлей-таблица заездов (standings tower) поверх iRacing.

Показывает все машины: позиция, номер, имя, разрыв до лидера, последний/лучший
круг, круг, пит. Своя машина подсвечена. Данные из localhost:8000/api/standings.

Запуск: python overlay_standings.py (нужен запущенный run.py).
Перетаскивается мышью, Esc — выход.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import httpx
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

DASH = "http://localhost:8000"
ROW_H = 26
MAX_ROWS = 16


def lap_time(sec):
    if not isinstance(sec, (int, float)) or sec <= 0:
        return "—"
    m = int(sec // 60)
    return f"{m}:{sec - m*60:06.3f}"


class Standings(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.rows = []
        self._drag = None
        self.resize(560, ROW_H + 6)
        self.move(60, 60)
        t = QTimer(self)
        t.timeout.connect(self.poll)
        t.start(300)

    def poll(self):
        try:
            self.rows = httpx.get(f"{DASH}/api/standings", timeout=0.5).json() or []
        except Exception:
            pass
        n = min(len(self.rows), MAX_ROWS)
        self.resize(560, ROW_H * max(n, 1) + 6)
        self.update()

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
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rows = self.rows[:MAX_ROWS]
        if not rows:
            p.setBrush(QColor(13, 15, 18, 190)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(0, 0, self.width(), ROW_H + 6), 8, 8)
            p.setPen(QColor("#9099a6")); p.setFont(QFont("Segoe UI", 10))
            p.drawText(12, 20, "Нет данных (запусти Гонку и выезжай на трассу) · Esc")
            return

        # колонки: позиция | номер | имя | gap | посл. круг | круг | пит
        X = {"pos": 10, "num": 44, "name": 86, "gap": 300, "last": 380, "lap": 480, "pit": 520}
        for i, r in enumerate(rows):
            y = i * ROW_H + 3
            bg = QColor(46, 80, 120, 210) if r.get("is_player") else QColor(13, 15, 18, 185)
            p.setBrush(bg); p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(0, y, self.width(), ROW_H - 2), 5, 5)

            def t(x, s, color="#e8eaed", size=12, bold=False):
                f = QFont("Segoe UI", size); f.setBold(bold)
                p.setFont(f); p.setPen(QPen(QColor(color)))
                p.drawText(int(x), int(y + ROW_H - 8), str(s))

            t(X["pos"], r.get("pos", ""), "#e8eaed", 12, True)
            t(X["num"], f"#{r.get('number','')}", "#9099a6", 11)
            name = (r.get("name") or "")[:22]
            t(X["name"], name, "#fff" if r.get("is_player") else "#e8eaed", 12, r.get("is_player"))
            t(X["gap"], f"+{r.get('gap','')}" if r.get("pos") != 1 else "лидер", "#cdd3dc", 11)
            t(X["last"], lap_time(r.get("last")), "#cdd3dc", 11)
            t(X["lap"], f"L{r.get('lap','')}" if r.get("lap") not in (None, -1) else "", "#9099a6", 11)
            if r.get("on_pit"):
                t(X["pit"], "PIT", "#f1c40f", 11, True)


def main():
    app = QApplication(sys.argv)
    w = Standings()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
