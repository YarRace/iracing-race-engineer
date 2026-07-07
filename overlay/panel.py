"""Панель управления оверлеем: галочки показать/скрыть виджеты + блокировка.

Обычное окошко (с рамкой). Тумблер у каждого виджета создаёт/прячет его окно;
состояние и позиции сохраняются в Config. «Блокировка» → клики проходят сквозь
все виджеты в игру (удобно в гонке).
"""
from __future__ import annotations

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QCheckBox, QLabel, QFrame)


class ControlPanel(QWidget):
    def __init__(self, store, config, widget_classes):
        super().__init__()
        self.setWindowTitle("Race Engineer — Оверлей")
        self.resize(300, 40 + 28 * (len(widget_classes) + 3))
        self.store = store
        self.config = config
        self.widgets = {}                     # key -> экземпляр виджета

        lay = QVBoxLayout(self)
        self.status = QLabel("● связь с инженером: проверяю…")
        lay.addWidget(self.status)
        lay.addWidget(QLabel("<b>Оверлеи</b> — галочка показывает виджет:"))
        for cls in widget_classes:
            cb = QCheckBox(cls.TITLE)
            cb.setChecked(config.is_enabled(cls.KEY))
            cb.toggled.connect(lambda v, c=cls: self.toggle(c, v))
            lay.addWidget(cb)
            if config.is_enabled(cls.KEY):
                self.toggle(cls, True)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        lay.addWidget(line)
        lock = QCheckBox("🔒 Заблокировать (клики проходят в игру)")
        lock.setChecked(config.locked())
        lock.toggled.connect(self.set_lock)
        lay.addWidget(lock)
        lay.addWidget(QLabel("Перетаскивай виджеты мышью, тяни за угол.\n"
                             "iRacing — в оконном/безрамочном режиме."))
        lay.addStretch(1)

    def toggle(self, cls, show):
        self.config.set_enabled(cls.KEY, show)
        w = self.widgets.get(cls.KEY)
        if show:
            if w is None:
                w = cls(self.store, self.config)
                self.widgets[cls.KEY] = w
            w.apply_lock()
            w.show()
        elif w is not None:
            w.hide()
        self._update_active()

    def _update_active(self):
        """Опрашивать только те эндпоинты, что нужны видимым виджетам."""
        active = set()
        for w in self.widgets.values():
            if w.isVisible():
                active.update(w.ENDPOINTS)
        self.store.set_active(active)

    def set_lock(self, val):
        self.config.set_locked(val)
        for w in self.widgets.values():
            w.apply_lock()

    def repaint_all(self):
        if self.store.ok:
            self.status.setText("<span style='color:#2ecc71'>🟢 данные от инженера идут</span>")
        else:
            self.status.setText("<span style='color:#e74c3c'>🔴 нет связи — запусти «Race Engineer (Гонка)»</span>")
        for w in self.widgets.values():
            if w.isVisible():
                w.update()

    def closeEvent(self, e):
        for w in self.widgets.values():
            w.close()
        e.accept()
