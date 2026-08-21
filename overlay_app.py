#!/usr/bin/env python3
"""Свой оверлей Race Engineer (как RaceLab/Kapps) — прозрачные виджеты поверх iRacing.

Открывает панель управления: виджеты сгруппированы как вкладки инженера —
🟢 Соло / 🔵 Endurance / 🟣 Setup (всего 31). Галочкой включаешь нужный.
Виджеты перетаскиваются мышью и тянутся за угол; раскладка сохраняется.
«Блокировка» — клики проходят в игру.

Запуск: python overlay_app.py  (нужен запущенный run.py — дашборд на :8000).
ВАЖНО: iRacing в оконном/безрамочном режиме (не эксклюзивный фуллскрин).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from overlay.store import Store
from overlay.config import Config
from overlay.panel import ControlPanel
from overlay.widgets import WIDGETS


def main():
    app = QApplication(sys.argv)
    store = Store()
    config = Config(os.path.join(os.path.dirname(__file__), "data", "overlay_config.json"))
    panel = ControlPanel(store, config, WIDGETS)

    store.start()                                       # опрос сети — в ФОНОВОМ потоке
    timer = QTimer()
    timer.timeout.connect(panel.repaint_all)            # GUI только перерисовывает (быстро)
    timer.start(33)                                     # ~30 кадров/сек — плавно и ЛЕГКО (60 грузило GPU/игру)

    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
