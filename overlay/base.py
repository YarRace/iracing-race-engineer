"""Базовый прозрачный виджет-оверлей поверх iRacing.

Каждый виджет: без рамки, полупрозрачный фон, always-on-top, не крадёт фокус.
ПО УМОЛЧАНИЮ клики проходят СКВОЗЬ виджет — в игру и любые окна/кнопки за ним
(нативный WS_EX_TRANSPARENT на Windows, где бы и какого размера ни был оверлей).
Двигать/менять размер — только когда включён режим правки (config.edit_mode()):
тогда виджет ловит мышь, тянется за угол; позиция сохраняется в Config.
Наследники переопределяют draw(painter).
"""
from __future__ import annotations

import sys

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
    TITLE = "Widget"
    DEFAULT = (300, 160)
    ENDPOINTS = ()          # какие /api/* нужны этому виджету (для точечного опроса)
    REORDERABLE = False     # можно ли менять порядок элементов (списковые виджеты)

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
        self._elrects = []          # [(key, QRectF)] — кликабельные зоны элементов (за кадр)
        self._sel_key = None        # выбранный элемент (подсветка)
        self.apply_input_mode()
        self.apply_opacity()

    def apply_opacity(self):
        """Глобальная прозрачность всех оверлеев (как в Kapps)."""
        self.setWindowOpacity(self.config.opacity())

    def apply_input_mode(self):
        """Сквозной клик, кроме режима правки. Сквозной = мышь идёт в игру/окна за нами."""
        through = not self.config.edit_mode()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, through)
        if self.isVisible():                               # native-часть нужна после создания окна
            self._native_clickthrough(through)

    def showEvent(self, e):
        # exstyle надёжно ставим ПОСЛЕ создания окна (иначе Qt может перетереть на show)
        super().showEvent(e)
        self._native_clickthrough(not self.config.edit_mode())
        self.apply_opacity()

    def _native_clickthrough(self, on):
        """Windows: WS_EX_TRANSPARENT — реальный сквозной клик в ДРУГИЕ приложения
        (одного WA_TransparentForMouseEvents для окна поверх игры не хватает).
        WS_EX_NOACTIVATE — оверлей НИКОГДА не забирает фокус/активацию у iRacing
        (чтобы игра не «моргала»/не лагала при появлении окон)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = -20, 0x00080000, 0x00000020, 0x08000000
            u = ctypes.windll.user32
            s = u.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_NOACTIVATE
            s = (s | WS_EX_TRANSPARENT) if on else (s & ~WS_EX_TRANSPARENT)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, s)
        except Exception:
            pass

    # ---------- оформление: по виджету + по КАЖДОМУ элементу ----------
    def _opt(self, name, default):
        return self.config.widget_opt(self.KEY, name, default)

    def _el(self, key):
        """Оформление одного элемента: {color, size, family, hidden}."""
        return (self._opt("el", {}) or {}).get(key, {}) if key else {}

    def _fs(self, size):
        return max(5.0, size * float(self._opt("font", 1.0)))       # общий множитель виджета

    def _ink(self, color):
        """Белый текст (значения) → «цвет значений» виджета; семантику не трогаем."""
        return self._opt("accent", "#e8eaed") if color == "#e8eaed" else color

    def _font_for(self, key, size, bold):
        el = self._el(key)                                          # семейство/размер элемента
        f = QFont(el.get("family") or self._opt("family", "Segoe UI"))
        f.setPointSizeF(max(5.0, self._fs(size) * float(el.get("size", 1.0))))
        style = self._opt("font_style", "regular")                  # Kapps «Font style»
        f.setBold(bold or style == "bold")
        if style == "italic":
            f.setItalic(True)
        elif style == "condensed":
            f.setStretch(QFont.Condensed)
        return f

    def _font(self, size, bold):                                    # совместимость
        return self._font_for(None, size, bold)

    def _color_for(self, key, color):
        return self._el(key).get("color") or self._ink(color)

    def _cb(self, color):
        """Colour-blind remap (Kapps «Color Blind Mode»): зелёный→синий, красный→оранжевый."""
        if not self._opt("colorblind", False):
            return color
        return {"#2ecc71": "#3ea6ff", "#e74c3c": "#e67e22"}.get(color, color)

    def parts(self):
        """Элементы виджета: [(key, подпись)] — их можно кликнуть и настроить по отдельности."""
        return []

    def part_on(self, key):
        return not self._el(key).get("hidden", False)

    def _pcolor(self, key, default):
        return self._el(key).get("color") or default

    def ordered_parts(self):
        """parts() в пользовательском порядке (⚙ ↑↓): сначала заданные, затем новые."""
        parts = self.parts()
        order = self._opt("order", []) or []
        oset = set(order)
        known = [kv for k in order for kv in parts if kv[0] == k]
        return known + [kv for kv in parts if kv[0] not in oset]

    def extra_settings(self, lay):
        """Виджет может добавить свои ползунки в диалог ⚙ (напр. трек-мапа: ширина/размер)."""
        return

    def _form_row(self, lay, title, control):
        """Строка настройки в стиле Kapps: подпись справа-выровнена слева | контрол справа."""
        from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)
        lbl = QLabel(title, objectName="flabel")
        lbl.setFixedWidth(96)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setWordWrap(True)
        h.addWidget(lbl)
        h.addWidget(control, 1)
        lay.addWidget(row)

    def opt_slider(self, lay, title, name, lo, hi, default):
        """Ползунок с боксом значения справа (как в Kapps)."""
        from PySide6.QtWidgets import QLabel, QSlider, QHBoxLayout, QWidget
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(self._opt(name, default)))
        val = QLabel(str(s.value()), objectName="vbox")
        val.setFixedWidth(46)
        val.setAlignment(Qt.AlignCenter)

        def upd(v):
            val.setText(str(v))
            self.config.set_widget_opt(self.KEY, name, v)
            self.update()
        s.valueChanged.connect(upd)
        h.addWidget(s, 1)
        h.addWidget(val)
        self._form_row(lay, title, box)

    def opt_check(self, lay, title, name, default=True):
        """Галочка вкл/выкл — подпись слева, чекбокс справа (стиль Kapps)."""
        from PySide6.QtWidgets import QCheckBox
        cb = QCheckBox()
        cb.setChecked(bool(self._opt(name, default)))
        cb.toggled.connect(lambda on: (self.config.set_widget_opt(self.KEY, name, bool(on)), self.update()))
        self._form_row(lay, title, cb)

    def opt_choice(self, lay, title, name, choices):
        """Выбор из вариантов: радио-кнопки (≤5) как в Kapps, иначе выпадашка. choices=[(value, подпись)]."""
        from PySide6.QtWidgets import (QHBoxLayout, QGridLayout, QComboBox, QWidget,
                                       QRadioButton, QButtonGroup)
        cur = self._opt(name, choices[0][0])
        box = QWidget()

        def pick(on, v):
            if on:
                self.config.set_widget_opt(self.KEY, name, v)
                self.update()

        if len(choices) <= 6:                              # радио-кнопки (перенос по 3, чтобы влезло в узкую панель)
            per = 3 if len(choices) > 4 else len(choices)
            g = QGridLayout(box)
            g.setContentsMargins(0, 0, 0, 0)
            g.setHorizontalSpacing(10)
            g.setVerticalSpacing(3)
            grp = QButtonGroup(box)
            for i, (val, label) in enumerate(choices):
                rb = QRadioButton(label)
                rb.setChecked(val == cur)
                rb.toggled.connect(lambda on, v=val: pick(on, v))
                grp.addButton(rb)
                g.addWidget(rb, i // per, i % per)
            g.setColumnStretch(per, 1)
        else:                                              # много вариантов — выпадашка
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            cb = QComboBox()
            for val, label in choices:
                cb.addItem(label, val)
            cb.setCurrentIndex(next((i for i, (v, _) in enumerate(choices) if v == cur), 0))
            cb.currentIndexChanged.connect(
                lambda i: (self.config.set_widget_opt(self.KEY, name, cb.itemData(i)), self.update()))
            h.addWidget(cb, 1)
        self._form_row(lay, title, box)

    def opt_number(self, lay, title, name, lo, hi, default):
        """Число-инпут (Kapps «Rows»): подпись слева | спинбокс справа."""
        from PySide6.QtWidgets import QSpinBox
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(int(self._opt(name, default)))
        sb.setFixedWidth(72)
        sb.valueChanged.connect(lambda v: (self.config.set_widget_opt(self.KEY, name, v), self.update()))
        self._form_row(lay, title, sb)

    # ---------- помощники отрисовки (для наследников) ----------
    def _mark(self, key, x, y, w, h):
        if key:                                                    # кликабельная зона элемента
            self._elrects.append((key, QRectF(x, y, max(w, 8), max(h, 8))))

    def _bg(self, p):
        a = float(self._opt("bg", 0.78))                           # 0 = убран, 1 = плотный
        if a <= 0.01:
            return
        lvl = int(max(0, min(70, self._opt("bg_bright", 18))) * 0.7)  # яркость фона (Kapps «Brightness»)
        r = int(self._opt("radius", 10))                           # скругление углов (Kapps «Border radius»)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(lvl, lvl + 2, lvl + 5, int(a * 255)))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), r, r)

    def text(self, p, x, y, s, color="#e8eaed", size=12, bold=False, key=None):
        p.setFont(self._font_for(key, size, bold))
        if self._opt("text_shadow", False):                        # Kapps «Text Shadow»
            p.setPen(QPen(QColor(0, 0, 0, 190)))
            p.drawText(int(x) + 1, int(y) + 1, str(s))
        p.setPen(QPen(QColor(self._color_for(key, color))))
        p.drawText(int(x), int(y), str(s))
        if key:
            fm = p.fontMetrics()
            self._mark(key, x, y - fm.ascent(), fm.horizontalAdvance(str(s)), fm.height())

    def text_right(self, p, xr, y, s, color="#e8eaed", size=12, bold=True, key=None):
        p.setFont(self._font_for(key, size, bold))
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(str(s))
        if self._opt("text_shadow", False):
            p.setPen(QPen(QColor(0, 0, 0, 190)))
            p.drawText(int(xr - w) + 1, int(y) + 1, str(s))
        p.setPen(QPen(QColor(self._color_for(key, color))))
        p.drawText(int(xr - w), int(y), str(s))
        if key:
            self._mark(key, xr - w, y - fm.ascent(), w, fm.height())

    def text_center(self, p, s, color, size, y=None, bold=True, key=None):
        p.setFont(self._font_for(key, size, bold))
        r = QRectF(0, 0, self.width(), self.height()) if y is None else QRectF(0, y - size, self.width(), size * 1.6)
        if self._opt("text_shadow", False):
            p.setPen(QPen(QColor(0, 0, 0, 190)))
            p.drawText(r.adjusted(1, 1, 1, 1), Qt.AlignCenter, str(s))
        p.setPen(QPen(QColor(self._color_for(key, color))))
        p.drawText(r, Qt.AlignCenter, str(s))
        if key:
            self._mark(key, 0, r.y(), self.width(), r.height())

    def bar(self, p, x, y, w, h, frac, color, key=None):
        frac = max(0.0, min(1.0, frac or 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 12, 15))
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        ov = self._el(key).get("color") if key else None
        p.setBrush(QColor(ov) if ov else color)
        p.drawRoundedRect(QRectF(x, y, w * frac, h), h / 2, h / 2)
        self._mark(key, x, y - 3, w, h + 6)

    def hit(self, key, x, y, w, h):
        """Явная (более широкая) кликабельная зона элемента."""
        self._mark(key, x, y, w, h)

    def title(self, p, name):
        self.text(p, 12, 20, name, "#9099a6", 8, True)

    # ---------- отрисовка ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._elrects = []                                 # зоны элементов пересобираем каждый кадр
        self._bg(p)
        try:
            self.draw(p)
        except Exception:
            pass
        if self.config.edit_mode():                        # правка: подсветка + шестерёнка + уголок
            if self._sel_key:                              # рамка вокруг выбранного элемента
                for k, r in self._elrects:
                    if k == self._sel_key:
                        p.setBrush(Qt.NoBrush)
                        pen = QPen(QColor("#3ea6ff"))
                        pen.setWidth(2)
                        p.setPen(pen)
                        p.drawRoundedRect(r.adjusted(-3, -2, 3, 2), 4, 4)
                        break
            gr = self._gear_rect()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(30, 34, 40, 235))
            p.drawEllipse(gr)
            f = QFont("Segoe UI")
            f.setPointSizeF(11)
            p.setFont(f)
            p.setPen(QPen(QColor("#cdd3dc")))
            p.drawText(gr, Qt.AlignCenter, "⚙")
            p.setPen(QPen(QColor(90, 107, 122)))
            for i in (4, 8, 12):
                p.drawLine(self.width() - i, self.height() - 3, self.width() - 3, self.height() - i)

    def draw(self, p):
        """Переопределяется в наследниках."""

    # ---------- взаимодействие ----------
    def _in_handle(self, pos):
        return pos.x() >= self.width() - HANDLE and pos.y() >= self.height() - HANDLE

    def _gear_rect(self):
        return QRectF(self.width() - 23, 4, 19, 19)        # ⚙ в правом верхнем углу

    def _open_settings(self):
        from overlay.settings_dialog import WidgetSettingsDialog
        if getattr(self, "_settings", None) is None:
            self._settings = WidgetSettingsDialog(self)
        self._settings.move(self.x() + self.width() + 8, self.y())
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def _element_at(self, pos):
        for key, r in reversed(self._elrects):              # верхний (позже нарисованный) — первым
            if r.contains(pos):
                return key
        return None

    def _open_element_editor(self, key):
        from overlay.settings_dialog import ElementEditor
        label = dict(self.parts()).get(key, key)
        ed = getattr(self, "_eleditor", None)
        if ed is not None:
            ed.close()
        self._eleditor = ElementEditor(self, key, label)
        self._eleditor.move(self.x() + self.width() + 8, self.y() + 44)
        self._eleditor.show()
        self._eleditor.raise_()
        self._eleditor.activateWindow()

    def mousePressEvent(self, e):
        if not self.config.edit_mode() or e.button() != Qt.LeftButton:
            return
        pos = e.position()
        if self._gear_rect().contains(pos):                 # ⚙ → настройка всего виджета
            self._open_settings()
            return
        key = self._element_at(pos)                         # клик по элементу → правка ЕГО стиля
        if key is not None:
            self._sel_key = key
            self.update()
            self._open_element_editor(key)
            return
        if self._in_handle(pos.toPoint()):                  # угол → ресайз
            self._resize = (e.globalPosition().toPoint(), self.width(), self.height())
        else:                                               # пусто/заголовок → двигаем весь виджет
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
