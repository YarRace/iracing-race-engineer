"""Настройка оформления оверлея.

- WidgetSettingsDialog — по клику на шестерёнку ⚙ (весь виджет): фон, размер/шрифт/
  цвет ВСЕХ значений; список элементов — показать/скрыть + порядок ↑↓.
- ElementEditor — по клику на КОНКРЕТНЫЙ элемент (цифру/полосу): его цвет, размер,
  шрифт, скрыть. Оба применяют СРАЗУ и сохраняют в Config per-виджет (opts[KEY]).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
                               QPushButton, QComboBox, QCheckBox, QFrame)

# тёмный стиль диалога — секции-карточки как в Kapps (работает и встроенным, и всплывашкой)
SETTINGS_QSS = """
QWidget { background:#0f1216; color:#e8eaed; font-family:'Segoe UI'; font-size:13px; }
QFrame#card { background:#14181e; border:1px solid #20262e; border-radius:10px; }
QLabel#section { color:#9099a6; font-weight:800; letter-spacing:1px; font-size:11px; }
QLabel#hint { color:#69727f; font-size:11px; }
QLabel#flabel { color:#9099a6; font-weight:600; }
QLabel#vbox { background:#181c22; border:1px solid #2a2f38; border-radius:6px; color:#e8eaed; padding:3px 0; }
QRadioButton { spacing:5px; }
QRadioButton::indicator { width:14px; height:14px; border-radius:7px; border:1px solid #3a4048; background:#181c22; }
QRadioButton::indicator:checked { background:#3ea6ff; border-color:#3ea6ff; }
QPushButton { background:#181c22; border:1px solid #2a2f38; border-radius:8px; padding:6px 10px; }
QPushButton:hover { background:#232a33; }
QComboBox { background:#181c22; border:1px solid #2a2f38; border-radius:6px; padding:4px 8px; }
QCheckBox { padding:3px 2px; spacing:8px; }
QCheckBox::indicator { width:15px; height:15px; border-radius:4px; border:1px solid #2a2f38; background:#181c22; }
QCheckBox::indicator:checked { background:#2ecc71; border-color:#2ecc71; }
QSlider::groove:horizontal { height:6px; background:#232a33; border-radius:3px; }
QSlider::sub-page:horizontal { background:#3ea6ff; border-radius:3px; }
QSlider::handle:horizontal { width:14px; background:#e8eaed; border-radius:7px; margin:-5px 0; }
"""

# цвет ЗНАЧЕНИЙ виджета (белый = по умолчанию, без изменения)
ACCENTS = [("White", "#e8eaed"), ("Blue", "#3ea6ff"), ("Green", "#2ecc71"),
           ("Yellow", "#f1c40f"), ("Orange", "#e67e22"), ("Red", "#e74c3c"),
           ("Purple", "#c77dff"), ("Cyan", "#22d3ee")]
FONTS = ["Segoe UI", "Consolas", "Cascadia Mono", "Tahoma", "Verdana", "Arial", "Impact"]
# цвет ОТДЕЛЬНОГО элемента (умолч. = не переопределять)
ELEM_COLORS = [("Default", None), ("Blue", "#3ea6ff"), ("Cyan", "#22d3ee"), ("Green", "#2ecc71"),
               ("Yellow", "#f1c40f"), ("Orange", "#e67e22"), ("Red", "#e74c3c"),
               ("Purple", "#c77dff"), ("White", "#e8eaed")]


def _swatch(btn, hexv, selected):
    mark = "2px solid #fff" if selected else "1px solid #555"
    btn.setStyleSheet(f"background:{hexv or '#3a3f47'};border:{mark};border-radius:5px")


class WidgetSettingsDialog(QWidget):
    """⚙ всего виджета: фон / размер / шрифт / цвет значений + список элементов.
    embed=True — встраивается прямо в панель приложения (как в Kapps), а не всплывает."""
    def __init__(self, widget, embed=False):
        if embed:
            super().__init__()                            # обычный дочерний виджет — ляжет в панель
        else:
            super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.w = widget
        self.cfg = widget.config
        self.setWindowTitle(f"⚙ {widget.TITLE}")
        self.setMinimumWidth(280)
        self.setStyleSheet(SETTINGS_QSS)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(QLabel(f"<b>⚙ {widget.TITLE}</b>"))

        sec = self._section(lay, "BACKGROUND")
        self.bg = QSlider(Qt.Horizontal)
        self.bg.setRange(0, 100)
        self.bg.setValue(int(float(self._opt("bg", 0.78)) * 100))
        self.bg.valueChanged.connect(self._bg_changed)
        self.bg_lbl = QLabel(objectName="vbox")
        self.bg_lbl.setFixedWidth(46)
        self.bg_lbl.setAlignment(Qt.AlignCenter)
        off = QPushButton("Remove")
        off.clicked.connect(lambda: self.bg.setValue(0))
        bctl = QWidget()
        bh = QHBoxLayout(bctl)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(8)
        bh.addWidget(self.bg, 1)
        bh.addWidget(self.bg_lbl)
        bh.addWidget(off)
        self._row(sec, "Opacity", bctl)
        self._opt_slider(sec, "Brightness", "bg_bright", 0, 70, 18)
        self._opt_slider(sec, "Radius", "radius", 0, 30, 10)

        sec = self._section(lay, "FONT")
        self.fs = QSlider(Qt.Horizontal)
        self.fs.setRange(70, 170)
        self.fs.setValue(int(float(self._opt("font", 1.0)) * 100))
        self.fs.valueChanged.connect(self._fs_changed)
        self.fs_lbl = QLabel(objectName="vbox")
        self.fs_lbl.setFixedWidth(46)
        self.fs_lbl.setAlignment(Qt.AlignCenter)
        fctl = QWidget()
        fh = QHBoxLayout(fctl)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(8)
        fh.addWidget(self.fs, 1)
        fh.addWidget(self.fs_lbl)
        self._row(sec, "Size", fctl)
        self.family = QComboBox()
        self.family.addItems(FONTS)
        curf = self._opt("family", "Segoe UI")
        if curf not in FONTS:
            self.family.addItem(curf)
        self.family.setCurrentText(curf)
        self.family.currentTextChanged.connect(self._family_changed)
        self._row(sec, "Font", self.family)
        self._opt_choice(sec, "Style", "font_style",
                         [("regular", "Regular"), ("bold", "Bold"), ("italic", "Italic"), ("condensed", "Cond.")],
                         "regular")
        self._opt_check(sec, "Shadow", "text_shadow", False)

        sec = self._section(lay, "VALUE COLOR")
        swwrap = QWidget()
        sw = QHBoxLayout(swwrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(4)
        self._acc_btns = []
        cur = self._opt("accent", "#e8eaed")
        for name, hexv in ACCENTS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, h=hexv: self._accent(h))
            sw.addWidget(b)
            self._acc_btns.append((hexv, b))
        sw.addStretch(1)
        self._row(sec, "Color", swwrap)
        self._paint_accents(cur)
        self._opt_check(sec, "Colour-blind", "colorblind", False)

        opt = self._section(lay, "OPTIONS")                 # свои ползунки виджета
        widget.extra_settings(opt)
        if opt.count() <= 1:                                # добавился только заголовок → опций нет → убрать
            card = opt.parentWidget()
            if card is not None:
                card.setParent(None)
                card.deleteLater()

        if widget.parts():
            sec = self._section(lay, "ELEMENTS")
            sec.addWidget(QLabel("color / size / font — click an element on the overlay", objectName="hint"))
            self._elbox = QVBoxLayout()
            self._elbox.setSpacing(3)
            sec.addLayout(self._elbox)
            self._build_elements()

        reset = QPushButton("↺ Reset whole widget")
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)
        lay.addStretch(1)
        self._sync_labels()

    def _section(self, lay, title):
        """Карточка-секция с заголовком (как разделы настроек в Kapps). Возвращает её layout."""
        card = QFrame(objectName="card")
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        v.addWidget(QLabel(title, objectName="section"))
        lay.addWidget(card)
        return v

    def _row(self, lay, title, control):
        """Двухколоночная строка: подпись слева | контрол справа (стиль Kapps)."""
        r = QWidget()
        h = QHBoxLayout(r)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)
        t = QLabel(title, objectName="flabel")
        t.setFixedWidth(70)
        t.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(t)
        h.addWidget(control, 1)
        lay.addWidget(r)

    # универсальные настройки (пишут в opts ЛЮБОГО виджета — годятся для всех)
    def _opt_slider(self, sec, title, key, lo, hi, default):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(self._opt(key, default)))
        val = QLabel(str(s.value()), objectName="vbox")
        val.setFixedWidth(46)
        val.setAlignment(Qt.AlignCenter)

        def upd(v):
            val.setText(str(v))
            self.cfg.set_widget_opt(self.w.KEY, key, v)
            self.w.update()
        s.valueChanged.connect(upd)
        box = QWidget()
        hh = QHBoxLayout(box)
        hh.setContentsMargins(0, 0, 0, 0)
        hh.setSpacing(8)
        hh.addWidget(s, 1)
        hh.addWidget(val)
        self._row(sec, title, box)

    def _opt_check(self, sec, title, key, default):
        cb = QCheckBox()
        cb.setChecked(bool(self._opt(key, default)))
        cb.toggled.connect(lambda on: (self.cfg.set_widget_opt(self.w.KEY, key, bool(on)), self.w.update()))
        self._row(sec, title, cb)

    def _opt_choice(self, sec, title, key, choices, default):
        cb = QComboBox()
        for val, label in choices:
            cb.addItem(label, val)
        cur = self._opt(key, default)
        cb.setCurrentIndex(next((i for i, (v, _) in enumerate(choices) if v == cur), 0))
        cb.currentIndexChanged.connect(
            lambda i: (self.cfg.set_widget_opt(self.w.KEY, key, cb.itemData(i)), self.w.update()))
        self._row(sec, title, cb)

    def _opt(self, name, default):
        return self.cfg.widget_opt(self.w.KEY, name, default)

    def _build_elements(self):
        while self._elbox.count():
            it = self._elbox.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        el = self._opt("el", {}) or {}
        for key, label in self.w.ordered_parts():
            r = QWidget()
            h = QHBoxLayout(r)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            cb = QCheckBox(label)
            cb.setChecked(not el.get(key, {}).get("hidden", False))
            cb.toggled.connect(lambda on, k=key: self._part_toggled(k, on))
            h.addWidget(cb, 1)
            if self.w.REORDERABLE:
                up = QPushButton("↑")
                up.setFixedWidth(26)
                up.clicked.connect(lambda _=False, k=key: self._move(k, -1))
                h.addWidget(up)
                dn = QPushButton("↓")
                dn.setFixedWidth(26)
                dn.clicked.connect(lambda _=False, k=key: self._move(k, 1))
                h.addWidget(dn)
            self._elbox.addWidget(r)

    def _sync_labels(self):
        self.bg_lbl.setText(f"{self.bg.value()}%")
        self.fs_lbl.setText(f"{self.fs.value()}%")

    def _paint_accents(self, cur):
        for hexv, b in self._acc_btns:
            _swatch(b, hexv, hexv == cur)

    def _bg_changed(self, v):
        self.cfg.set_widget_opt(self.w.KEY, "bg", v / 100.0)
        self._sync_labels()
        self.w.update()

    def _fs_changed(self, v):
        self.cfg.set_widget_opt(self.w.KEY, "font", v / 100.0)
        self._sync_labels()
        self.w.update()

    def _family_changed(self, name):
        self.cfg.set_widget_opt(self.w.KEY, "family", name)
        self.w.update()

    def _accent(self, hexv):
        self.cfg.set_widget_opt(self.w.KEY, "accent", hexv)
        self._paint_accents(hexv)
        self.w.update()

    def _part_toggled(self, key, on):
        el = dict(self._opt("el", {}) or {})
        d = dict(el.get(key, {}))
        if on:
            d.pop("hidden", None)
        else:
            d["hidden"] = True
        el[key] = d if d else {}
        if not el[key]:
            el.pop(key, None)
        self.cfg.set_widget_opt(self.w.KEY, "el", el)
        self.w.update()

    def _move(self, key, delta):
        order = [k for k, _ in self.w.ordered_parts()]
        i = order.index(key)
        j = i + delta
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            self.cfg.set_widget_opt(self.w.KEY, "order", order)
            self.w.update()
            self._build_elements()

    def _reset(self):
        self.cfg.clear_widget_opts(self.w.KEY)
        self.bg.setValue(78)
        self.fs.setValue(100)
        self.family.setCurrentText("Segoe UI")
        self._paint_accents("#e8eaed")
        if self.w.parts():
            self._build_elements()
        self._sync_labels()
        self.w.update()


class ElementEditor(QWidget):
    """Клик по элементу оверлея → правка ЕГО цвета / размера / шрифта / видимости."""
    def __init__(self, widget, key, label):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.w = widget
        self.cfg = widget.config
        self.key = key
        self.setWindowTitle(f"⚙ {label}")
        self.setMinimumWidth(250)
        el = self._el()

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{widget.TITLE}</b> · <b>{label}</b>"))

        lay.addWidget(QLabel("Color:"))
        sw = QHBoxLayout()
        sw.setSpacing(4)
        self._sw = []
        for name, hexv in ELEM_COLORS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, h=hexv: self._set_color(h))
            sw.addWidget(b)
            self._sw.append((hexv, b))
        sw.addStretch(1)
        lay.addLayout(sw)
        self._paint_sw(el.get("color"))

        self.sz_lbl = QLabel()
        lay.addWidget(self.sz_lbl)
        self.sz = QSlider(Qt.Horizontal)
        self.sz.setRange(50, 250)
        self.sz.setValue(int(float(el.get("size", 1.0)) * 100))
        self.sz.valueChanged.connect(self._set_size)
        lay.addWidget(self.sz)

        frow = QHBoxLayout()
        frow.addWidget(QLabel("Font:"))
        self.fam = QComboBox()
        self.fam.addItem("Same as widget", None)
        for f in FONTS:
            self.fam.addItem(f, f)
        self.fam.setCurrentIndex(next((i for i in range(self.fam.count())
                                       if self.fam.itemData(i) == el.get("family")), 0))
        self.fam.currentIndexChanged.connect(lambda i: self._set("family", self.fam.itemData(i)))
        frow.addWidget(self.fam, 1)
        lay.addLayout(frow)

        self.hide_cb = QCheckBox("Hide this element")
        self.hide_cb.setChecked(bool(el.get("hidden")))
        self.hide_cb.toggled.connect(lambda on: self._set("hidden", True if on else None))
        lay.addWidget(self.hide_cb)

        rb = QPushButton("↺ Reset element")
        rb.clicked.connect(self._reset)
        lay.addWidget(rb)
        lay.addStretch(1)
        self._sync()

    def _el(self):
        return dict((self.cfg.widget_opt(self.w.KEY, "el", {}) or {}).get(self.key, {}))

    def _sync(self):
        self.sz_lbl.setText(f"Size: {self.sz.value()}%")

    def _paint_sw(self, cur):
        for hexv, b in self._sw:
            _swatch(b, hexv, hexv == cur)

    def _set(self, prop, val):
        el = dict(self.cfg.widget_opt(self.w.KEY, "el", {}) or {})
        d = dict(el.get(self.key, {}))
        if val is None:
            d.pop(prop, None)
        else:
            d[prop] = val
        if d:
            el[self.key] = d
        else:
            el.pop(self.key, None)
        self.cfg.set_widget_opt(self.w.KEY, "el", el)
        self.w.update()

    def _set_color(self, hexv):
        self._set("color", hexv)
        self._paint_sw(hexv)

    def _set_size(self, v):
        self._set("size", v / 100.0)
        self._sync()

    def _reset(self):
        el = dict(self.cfg.widget_opt(self.w.KEY, "el", {}) or {})
        el.pop(self.key, None)
        self.cfg.set_widget_opt(self.w.KEY, "el", el)
        self.sz.setValue(100)
        self.fam.setCurrentIndex(0)
        self.hide_cb.setChecked(False)
        self._paint_sw(None)
        self.w.update()
