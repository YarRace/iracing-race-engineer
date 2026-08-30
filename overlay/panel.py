"""Панель управления оверлеями — три колонки, как в RaceLab.

Раньше панель была одной колонкой со списком и отдельной страницей настроек:
чтобы увидеть результат правки, приходилось лезть в игру. Теперь окно
разделено так же, как у RaceLab, потому что схема рабочая:

    ┌──────────┬────────────────────┬──────────────┐
    │ список   │  ЖИВОЙ ПРЕДПРОСМОТР │  настройки   │
    │ оверлеев │  выбранного виджета │  выбранного  │
    └──────────┴────────────────────┴──────────────┘

Крутишь ползунок справа — видишь результат в центре сразу, не выходя из окна.
Предпросмотр берёт те же данные из того же хранилища, что и боевой оверлей,
поэтому он не «примерно похож», а буквально тот же виджет (см. preview.py).

Сохранено из прежней панели: профили раскладок, глобальная прозрачность,
режим правки с хоткеем Ctrl+Shift+L, скрытие вне трассы, точечный опрос
только нужных эндпоинтов.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel,
                               QFrame, QScrollArea, QPushButton, QSlider, QComboBox,
                               QInputDialog, QLineEdit, QSplitter)

from overlay.hotkey import GlobalHotkey
from overlay.preview import BACKDROPS, PreviewCanvas

GROUPS = [("solo", "🟢 SOLO"), ("endur", "🔵 ENDURANCE"), ("setup", "🟣 SETUP")]

QSS = """
QWidget { background:#0f1216; color:#e8eaed; font-family:'Segoe UI'; font-size:13px; }
QScrollArea, QSplitter { border:none; background:#0f1216; }
QSplitter::handle { background:#1b2027; width:1px; }
QLabel#title { font-size:15px; font-weight:800; }
QLabel#group { color:#9099a6; font-weight:800; letter-spacing:1px; font-size:11px; }
QLabel#colhead { color:#7d8797; font-weight:800; letter-spacing:1.2px; font-size:10px; }
QLabel#hint { color:#69727f; font-size:11px; }
QLabel#wname { font-size:15px; font-weight:800; }
QLabel#wmeta { color:#69727f; font-size:11px; }
QCheckBox { padding:4px 2px; spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:4px; border:1px solid #2a2f38; background:#181c22; }
QCheckBox::indicator:checked { background:#2ecc71; border-color:#2ecc71; }
QLineEdit { background:#181c22; border:1px solid #2a2f38; border-radius:8px; padding:6px 9px; }
QLineEdit:focus { border-color:#3ea6ff; }
QPushButton { background:#181c22; border:1px solid #2a2f38; border-radius:8px; padding:7px 10px; }
QPushButton:hover { background:#232a33; }
QPushButton#edit { font-weight:700; }
QPushButton#edit:checked { background:#17512f; border-color:#2ecc71; color:#eafff2; }
QPushButton#link { background:transparent; border:none; color:#69727f; padding:2px 4px; font-size:12px; }
QPushButton#link:hover { color:#cdd3dc; }
QPushButton#row { background:transparent; border:none; text-align:left; padding:5px 8px; border-radius:7px; }
QPushButton#row:hover { background:#181c22; }
QPushButton#row:checked { background:#1d2b3d; color:#8ec7ff; font-weight:700; }
QPushButton#tiny { padding:4px 8px; font-size:12px; }
QFrame#card { background:#14181e; border:1px solid #20262e; border-radius:12px; }
QFrame#sep { color:#1b2027; max-height:1px; }
QSlider::groove:horizontal { height:6px; background:#232a33; border-radius:3px; }
QSlider::sub-page:horizontal { background:#3ea6ff; border-radius:3px; }
QSlider::handle:horizontal { width:14px; background:#e8eaed; border-radius:7px; margin:-5px 0; }
"""


class _PreviewStore:
    """Хранилище для предпросмотра: живые данные, а без них — демо.

    Отдельный класс, а не флаг внутри Store: боевые оверлеи ДОЛЖНЫ показывать
    прочерки, когда сима нет. Выдуманные цифры поверх игры — прямой путь
    к неверному решению на трассе.
    """

    def __init__(self, real, demo):
        self._real = real
        self._demo = demo
        self.allow_demo = True

    @property
    def ok(self):
        return getattr(self._real, "ok", False)

    def get(self, ep):
        data = self._real.get(ep)
        if data:
            return data
        return self._demo.get(ep) if self.allow_demo else data

    def set_active(self, endpoints):
        self._real.set_active(endpoints)


class ControlPanel(QWidget):
    def __init__(self, store, config, widget_classes):
        super().__init__()
        self.setWindowTitle("Race Engineer — Overlays")
        self.resize(1180, 720)
        self.setStyleSheet(QSS)
        self.store = store
        self.config = config
        self.widgets = {}                     # key -> живой оверлей поверх игры
        self._boxes = {}                      # key -> QCheckBox «включён»
        self._rows = {}                       # key -> QPushButton строки списка
        self._group_by_key = {}
        self._cls_by_key = {}
        self._selected = None                 # какой виджет показан в центре

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)
        root.addLayout(self._build_header())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_list(widget_classes))
        split.addWidget(self._build_preview())
        split.addWidget(self._build_settings())
        split.setSizes([250, 610, 320])
        split.setStretchFactor(1, 1)
        root.addWidget(split, 1)

        root.addWidget(self._build_footer())

        self._hotkey = GlobalHotkey(self._hotkey_toggle_edit)
        self._refresh_profiles()
        first = widget_classes[0] if widget_classes else None
        if first is not None:
            self.select(first.KEY)

    # ───────────────────────────── шапка ────────────────────────────────────
    def _build_header(self):
        h = QHBoxLayout()
        h.addWidget(QLabel("🏁 Race Engineer", objectName="title"))
        h.addSpacing(12)
        self.status = QLabel("● …")
        h.addWidget(self.status)
        h.addStretch(1)
        h.addWidget(QLabel("Раскладка", objectName="hint"))
        self.prof = QComboBox()
        self.prof.setMinimumWidth(150)
        self.prof.currentTextChanged.connect(self._on_profile_selected)
        h.addWidget(self.prof)
        addb = QPushButton("＋", objectName="tiny")
        addb.setToolTip("Сохранить текущую раскладку как новую")
        addb.clicked.connect(self.save_as_profile)
        h.addWidget(addb)
        delb = QPushButton("🗑", objectName="tiny")
        delb.setToolTip("Удалить активную раскладку")
        delb.clicked.connect(self.delete_profile)
        h.addWidget(delb)
        return h

    # ──────────────────────── левая колонка: список ─────────────────────────
    def _build_list(self, widget_classes):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(6)
        lay.addWidget(QLabel("ОВЕРЛЕИ", objectName="colhead"))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск оверлея…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_list)
        lay.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 6, 0)
        il.setSpacing(2)

        by_group = {g: [] for g, _ in GROUPS}
        for cls in widget_classes:
            g = getattr(cls, "GROUP", "solo")
            by_group.setdefault(g, by_group["solo"]).append(cls)
            self._group_by_key[cls.KEY] = g

        self._group_heads = {}
        for gkey, gtitle in GROUPS:
            classes = by_group.get(gkey) or []
            if not classes:
                continue
            head = QWidget()
            hh = QHBoxLayout(head)
            hh.setContentsMargins(0, 6, 0, 2)
            hh.addWidget(QLabel(gtitle, objectName="group"))
            hh.addStretch(1)
            btn = QPushButton("скрыть все", objectName="link")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, g=gkey: self._toggle_group(g))
            hh.addWidget(btn)
            il.addWidget(head)
            self._group_heads[gkey] = head

            for cls in classes:
                il.addWidget(self._build_row(cls))
                if config_enabled := self.config.is_enabled(cls.KEY):
                    self.toggle(cls, True)
        il.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        return box

    def _build_row(self, cls):
        """Строка списка: галочка «включён» + кнопка выбора для предпросмотра."""
        r = QWidget()
        rh = QHBoxLayout(r)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(2)

        cb = QCheckBox()
        cb.setChecked(self.config.is_enabled(cls.KEY))
        cb.setToolTip("Показывать поверх игры")
        cb.toggled.connect(lambda v, c=cls: self.toggle(c, v))
        self._boxes[cls.KEY] = cb
        self._cls_by_key[cls.KEY] = cls
        rh.addWidget(cb)

        btn = QPushButton(cls.TITLE, objectName="row")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _=False, k=cls.KEY: self.select(k))
        self._rows[cls.KEY] = btn
        rh.addWidget(btn, 1)

        r.setProperty("wkey", cls.KEY)
        return r

    def _filter_list(self, text):
        """Поиск по названию. Пустые группы прячем целиком, чтобы не мозолили."""
        q = (text or "").strip().lower()
        shown = {g: 0 for g, _ in GROUPS}
        for key, btn in self._rows.items():
            row = btn.parentWidget()
            ok = not q or q in btn.text().lower()
            row.setVisible(ok)
            if ok:
                shown[self._group_by_key.get(key, "solo")] += 1
        for gkey, head in self._group_heads.items():
            head.setVisible(shown.get(gkey, 0) > 0)

    # ─────────────────────── центр: живой предпросмотр ──────────────────────
    def _build_preview(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)
        lay.addWidget(QLabel("ПРЕДПРОСМОТР", objectName="colhead"))

        # Предпросмотр берёт демо-поток, когда сим молчит: настраивать виджет
        # по прочеркам бессмысленно — не видно ни цветов, ни ширины колонок.
        from overlay.demo import DemoFeed
        self._demo = DemoFeed()
        self.preview = PreviewCanvas(_PreviewStore(self.store, self._demo), self.config)
        lay.addWidget(self.preview, 1)

        bar = QHBoxLayout()
        self.demo_cb = QCheckBox("Демо-данные, когда сим не запущен")
        self.demo_cb.setChecked(True)
        self.demo_cb.setToolTip("Выключи, чтобы видеть настоящие прочерки")
        self.demo_cb.toggled.connect(lambda v: setattr(self.preview.store, "allow_demo", v))
        bar.addWidget(self.demo_cb)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Фон", objectName="hint"))
        self.bg = QComboBox()
        self.bg.addItems([b[0] for b in BACKDROPS])
        self.bg.currentIndexChanged.connect(self.preview.set_backdrop)
        bar.addWidget(self.bg)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Масштаб", objectName="hint"))
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(50, 200)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(140)
        self.zoom.valueChanged.connect(lambda v: self.preview.set_zoom(v / 100.0))
        bar.addWidget(self.zoom)
        self.zoom_lbl = QLabel("100%", objectName="hint")
        self.zoom_lbl.setMinimumWidth(38)
        self.zoom.valueChanged.connect(lambda v: self.zoom_lbl.setText(f"{v}%"))
        bar.addWidget(self.zoom_lbl)
        bar.addStretch(1)
        lay.addLayout(bar)
        return box

    # ───────────────────── правая колонка: настройки ────────────────────────
    def _build_settings(self):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(QLabel("НАСТРОЙКИ", objectName="colhead"))

        card = QFrame(objectName="card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(2)
        self.sel_name = QLabel("—", objectName="wname")
        cl.addWidget(self.sel_name)
        self.sel_meta = QLabel("", objectName="wmeta")
        cl.addWidget(self.sel_meta)
        lay.addWidget(card)

        self.sel_on = QCheckBox("Показывать поверх игры")
        self.sel_on.toggled.connect(self._toggle_selected)
        lay.addWidget(self.sel_on)

        self.sfilter = QLineEdit()
        self.sfilter.setPlaceholderText("Фильтр настроек…")
        self.sfilter.setClearButtonEnabled(True)
        self.sfilter.textChanged.connect(self._filter_settings)
        lay.addWidget(self.sfilter)

        self.sscroll = QScrollArea()
        self.sscroll.setWidgetResizable(True)
        lay.addWidget(self.sscroll, 1)
        lay.addWidget(QLabel("Двигать и растягивать — на самом оверлее, в режиме правки.",
                             objectName="hint"))
        return box

    def _filter_settings(self, text):
        """Прячем строки настроек, где нет искомого. Ищем по подписям QLabel."""
        w = self.sscroll.widget()
        if w is None:
            return
        q = (text or "").strip().lower()
        for row in w.findChildren(QWidget):
            if row.property("srow") is None:
                continue
            labels = " ".join(lbl.text() for lbl in row.findChildren(QLabel))
            row.setVisible(not q or q in labels.lower())

    # ──────────────────────────── подвал ────────────────────────────────────
    def _build_footer(self):
        card = QFrame(objectName="card")
        h = QHBoxLayout(card)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(12)

        self.edit_btn = QPushButton("✏️  Режим правки", objectName="edit")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setChecked(self.config.edit_mode())
        self.edit_btn.setToolTip("Двигать оверлеи мышью. Вне режима клики уходят в игру. "
                                 "Хоткей Ctrl+Shift+L")
        self.edit_btn.toggled.connect(self.set_edit)
        h.addWidget(self.edit_btn)

        h.addWidget(QLabel("Прозрачность", objectName="hint"))
        self.op = QSlider(Qt.Horizontal)
        self.op.setRange(30, 100)
        self.op.setValue(int(self.config.opacity() * 100))
        self.op.setFixedWidth(160)
        self.op.valueChanged.connect(self.set_opacity)
        h.addWidget(self.op)
        self.op_lbl = QLabel(f"{self.op.value()}%", objectName="hint")
        self.op_lbl.setMinimumWidth(36)
        h.addWidget(self.op_lbl)

        self.hide_cb = QCheckBox("Прятать вне трассы (в меню и повторах)")
        self.hide_cb.setChecked(self.config.hide_offtrack())
        self.hide_cb.toggled.connect(self.set_hide_offtrack)
        h.addWidget(self.hide_cb)
        h.addStretch(1)
        return card

    # ──────────────────────────── выбор виджета ─────────────────────────────
    def select(self, key):
        cls = self._cls_by_key.get(key)
        if cls is None:
            return
        self._selected = key
        for k, btn in self._rows.items():
            btn.setChecked(k == key)

        self.sel_name.setText(cls.TITLE)
        group = {"solo": "Соло", "endur": "Endurance", "setup": "Setup"}.get(
            self._group_by_key.get(key, "solo"), "")
        w, hgt = cls.DEFAULT
        self.sel_meta.setText(f"{group}  ·  {w}×{hgt} по умолчанию  ·  "
                              f"данные: {', '.join(cls.ENDPOINTS) or '—'}")
        self.sel_on.blockSignals(True)
        self.sel_on.setChecked(self.config.is_enabled(key))
        self.sel_on.blockSignals(False)

        self.preview.show_widget(cls)
        self._load_settings(cls)

    def _load_settings(self, cls):
        """Настройки строим на ПРЕДПРОСМОТРЕ: он всегда существует, а боевой
        виджет может быть выключен — раньше ради настройки его приходилось
        принудительно включать, и он выскакивал поверх игры."""
        from overlay.settings_dialog import WidgetSettingsDialog
        target = self.preview._widget
        if target is None:
            self.sscroll.takeWidget()
            return
        dlg = WidgetSettingsDialog(target, embed=True)
        dlg.destroyed.connect(lambda: None)
        self.sscroll.setWidget(dlg)
        self.sfilter.clear()

    def _toggle_selected(self, on):
        cls = self._cls_by_key.get(self._selected)
        if cls is None:
            return
        box = self._boxes.get(cls.KEY)
        if box is not None and box.isChecked() != on:
            box.setChecked(on)                    # через галочку — чтобы не раздваивать логику

    # ───────────────────── режим правки / прозрачность ──────────────────────
    def set_edit(self, val):
        self.config.set_edit_mode(val)
        if self.edit_btn.isChecked() != val:
            self.edit_btn.setChecked(val)
        self._refresh_visibility()
        for w in self.widgets.values():
            w.apply_input_mode()
            w.update()

    def _hotkey_toggle_edit(self):
        self.edit_btn.toggle()

    def set_opacity(self, v):
        self.op_lbl.setText(f"{v}%")
        self.config.set_opacity(v / 100.0)
        for w in self.widgets.values():
            w.apply_opacity()

    # ───────────────────────── профили раскладок ────────────────────────────
    def _refresh_profiles(self, select=None):
        self.prof.blockSignals(True)
        self.prof.clear()
        names = self.config.profiles()
        if names:
            self.prof.addItems(names)
            active = select or self.config.active_profile()
            if active in names:
                self.prof.setCurrentText(active)
        else:
            self.prof.addItem("— нет раскладок —")
        self.prof.blockSignals(False)

    def _on_profile_selected(self, name):
        if name and name in self.config.profiles() and name != self.config.active_profile():
            self.config.load_profile(name)
            self._rebuild_from_config()

    def save_as_profile(self):
        name, ok = QInputDialog.getText(self, "Новая раскладка", "Название:")
        name = (name or "").strip()
        if ok and name:
            self.config.save_profile(name)
            self._refresh_profiles(select=name)

    def delete_profile(self):
        name = self.config.active_profile()
        if name:
            self.config.delete_profile(name)
            self._refresh_profiles()

    def _rebuild_from_config(self):
        """Пересобрать оверлеи под загруженную раскладку."""
        for w in list(self.widgets.values()):
            w.close()
            w.deleteLater()
        self.widgets.clear()
        for key, cb in self._boxes.items():
            cb.blockSignals(True)
            cb.setChecked(self.config.is_enabled(key))
            cb.blockSignals(False)
        for key, cls in self._cls_by_key.items():
            if self.config.is_enabled(key):
                self.widgets[key] = cls(self.store, self.config)
        self._refresh_visibility()
        self.op.blockSignals(True)
        self.op.setValue(int(self.config.opacity() * 100))
        self.op.blockSignals(False)
        self.op_lbl.setText(f"{self.op.value()}%")
        if self._selected:
            self.select(self._selected)           # предпросмотр и настройки — под новую раскладку
        self._update_active()

    # ───────────────────────────── тумблеры ─────────────────────────────────
    def _toggle_group(self, gkey):
        target = [k for k in self._boxes if self._group_by_key.get(k) == gkey]
        any_on = any(self._boxes[k].isChecked() for k in target)
        for k in target:
            self._boxes[k].setChecked(not any_on)

    def toggle(self, cls, show):
        self.config.set_enabled(cls.KEY, show)
        if show and cls.KEY not in self.widgets:
            self.widgets[cls.KEY] = cls(self.store, self.config)
        if self._selected == cls.KEY and hasattr(self, "sel_on"):
            self.sel_on.blockSignals(True)
            self.sel_on.setChecked(show)
            self.sel_on.blockSignals(False)
        self._refresh_visibility()

    def set_hide_offtrack(self, val):
        self.config.set_hide_offtrack(val)
        self._refresh_visibility()

    def _refresh_visibility(self):
        """Видимость = включён И (правка ИЛИ не прячем вне трассы ИЛИ на трассе)."""
        hide = self.config.hide_offtrack()
        on = bool((self.store.get("live") or {}).get("on_track"))
        edit = self.config.edit_mode()
        changed = False
        for key, w in self.widgets.items():
            should = self.config.is_enabled(key) and (edit or not hide or on)
            if w.isVisible() != should:
                w.setVisible(should)
                if should:
                    w.apply_input_mode()
                    w.apply_opacity()
                changed = True
        if changed:
            self._update_active()

    def _update_active(self):
        """Опрашиваем только те эндпоинты, что нужны видимым виджетам и предпросмотру."""
        active = set()
        for w in self.widgets.values():
            if w.isVisible():
                active.update(w.ENDPOINTS)
        cls = self._cls_by_key.get(self._selected)
        if cls is not None:
            active.update(cls.ENDPOINTS)          # иначе предпросмотр стоял бы пустым
        self.store.set_active(active)

    def repaint_all(self):
        if self.store.ok:
            self.status.setText("<span style='color:#2ecc71'>🟢 данные идут</span>")
        else:
            self.status.setText("<span style='color:#e74c3c'>🔴 запусти «run.py»</span>")
        self._refresh_visibility()
        for w in self.widgets.values():
            if w.isVisible():
                w.update()

    def closeEvent(self, e):
        for w in self.widgets.values():
            w.close()
        e.accept()
