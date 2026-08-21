"""Панель управления оверлеями — в стиле Kapps.

Тёмное окно: сверху статус связи, крупная кнопка «Режим правки» (двигать/настраивать
оверлеи; сквозной клик выключается) + глобальный ползунок прозрачности всех оверлеев;
ниже — сгруппированный список оверлеев (🟢 Соло / 🔵 Endurance / 🟣 Setup) с тумблерами.
Режим правки переключается и глобальным хоткеем Ctrl+Shift+L (работает поверх игры).
Всё состояние (что включено, позиции, прозрачность) сохраняется в Config.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel,
                               QFrame, QScrollArea, QPushButton, QSlider, QComboBox,
                               QInputDialog, QStackedWidget)

from overlay.hotkey import GlobalHotkey

GROUPS = [("solo", "🟢 SOLO"), ("endur", "🔵 ENDURANCE"), ("setup", "🟣 SETUP")]

QSS = """
QWidget { background:#0f1216; color:#e8eaed; font-family:'Segoe UI'; font-size:13px; }
QScrollArea { border:none; background:#0f1216; }
QLabel#title { font-size:15px; font-weight:800; }
QLabel#group { color:#9099a6; font-weight:800; letter-spacing:1px; font-size:11px; }
QLabel#hint { color:#69727f; font-size:11px; }
QCheckBox { padding:4px 2px; spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:4px; border:1px solid #2a2f38; background:#181c22; }
QCheckBox::indicator:checked { background:#2ecc71; border-color:#2ecc71; }
QPushButton { background:#181c22; border:1px solid #2a2f38; border-radius:8px; padding:7px 10px; }
QPushButton:hover { background:#232a33; }
QPushButton#edit { font-weight:700; }
QPushButton#edit:checked { background:#17512f; border-color:#2ecc71; color:#eafff2; }
QPushButton#link { background:transparent; border:none; color:#69727f; padding:2px 4px; font-size:12px; }
QPushButton#link:hover { color:#cdd3dc; }
QPushButton#gear { background:transparent; border:none; color:#69727f; padding:2px 6px; font-size:15px; }
QPushButton#gear:hover { color:#3ea6ff; }
QPushButton#back { background:#181c22; border:1px solid #2a2f38; border-radius:8px; padding:6px 12px; font-weight:700; color:#3ea6ff; }
QPushButton#back:hover { background:#232a33; }
QFrame#card { background:#14181e; border:1px solid #20262e; border-radius:12px; }
QFrame#sep { color:#1b2027; max-height:1px; }
QSlider::groove:horizontal { height:6px; background:#232a33; border-radius:3px; }
QSlider::sub-page:horizontal { background:#3ea6ff; border-radius:3px; }
QSlider::handle:horizontal { width:14px; background:#e8eaed; border-radius:7px; margin:-5px 0; }
"""


class ControlPanel(QWidget):
    def __init__(self, store, config, widget_classes):
        super().__init__()
        self.setWindowTitle("Race Engineer — Overlays")
        self.resize(390, 640)
        self.setStyleSheet(QSS)
        self.store = store
        self.config = config
        self.widgets = {}                     # key -> экземпляр виджета
        self._boxes = {}                      # key -> QCheckBox
        self._group_by_key = {}               # key -> "solo"/"endur"/"setup"
        self._cls_by_key = {}                 # key -> класс виджета (для пересборки профиля)

        outer = QVBoxLayout(self)                         # весь контент — в стеке страниц
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        main = QWidget()                                  # страница 0: список оверлеев
        self._stack.addWidget(main)
        root = QVBoxLayout(main)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(QLabel("🏁 Race Engineer", objectName="title"))
        head.addStretch(1)
        self.status = QLabel("● …")
        head.addWidget(self.status)
        root.addLayout(head)

        # ---- профили раскладок (пресеты, как в Kapps) ----
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Profile"))
        self.prof = QComboBox()
        self.prof.currentTextChanged.connect(self._on_profile_selected)
        prow.addWidget(self.prof, 1)
        addb = QPushButton("＋")
        addb.setToolTip("Save current layout as a new profile")
        addb.setFixedWidth(34)
        addb.clicked.connect(self.save_as_profile)
        prow.addWidget(addb)
        delb = QPushButton("🗑")
        delb.setToolTip("Delete active profile")
        delb.setFixedWidth(34)
        delb.clicked.connect(self.delete_profile)
        prow.addWidget(delb)
        root.addLayout(prow)

        # ---- карточка глобальных настроек (режим правки + прозрачность) ----
        card = QFrame(objectName="card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(10)
        self.edit_btn = QPushButton("✏️  Edit mode  ·  move / customize", objectName="edit")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setChecked(config.edit_mode())
        self.edit_btn.toggled.connect(self.set_edit)
        cl.addWidget(self.edit_btn)
        cl.addWidget(QLabel("Off = overlays are click-through (clicks go to the game). Hotkey: Ctrl+Shift+L",
                            objectName="hint"))
        orow = QHBoxLayout()
        orow.addWidget(QLabel("Opacity"))
        self.op = QSlider(Qt.Horizontal)
        self.op.setRange(30, 100)
        self.op.setValue(int(config.opacity() * 100))
        self.op.valueChanged.connect(self.set_opacity)
        orow.addWidget(self.op, 1)
        self.op_lbl = QLabel(f"{self.op.value()}%")
        self.op_lbl.setMinimumWidth(36)
        orow.addWidget(self.op_lbl)
        cl.addLayout(orow)
        self.hide_cb = QCheckBox("Hide overlays when off track (in menus / replay)")
        self.hide_cb.setChecked(config.hide_offtrack())
        self.hide_cb.toggled.connect(self.set_hide_offtrack)
        cl.addWidget(self.hide_cb)
        root.addWidget(card)

        # ---- список оверлеев по группам (прокрутка) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(2)

        by_group = {g: [] for g, _ in GROUPS}
        for cls in widget_classes:
            g = getattr(cls, "GROUP", "solo")
            by_group.setdefault(g, by_group["solo"]).append(cls)
            self._group_by_key[cls.KEY] = g

        for gkey, gtitle in GROUPS:
            classes = by_group.get(gkey) or []
            if not classes:
                continue
            head2 = QHBoxLayout()
            head2.addWidget(QLabel(gtitle, objectName="group"))
            head2.addStretch(1)
            btn = QPushButton("hide all", objectName="link")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, g=gkey: self._toggle_group(g))
            head2.addWidget(btn)
            wrap = QWidget()
            wrap.setLayout(head2)
            lay.addWidget(wrap)
            for cls in classes:
                r = QWidget()
                rh = QHBoxLayout(r)
                rh.setContentsMargins(0, 0, 0, 0)
                rh.setSpacing(4)
                cb = QCheckBox(cls.TITLE)
                cb.setChecked(config.is_enabled(cls.KEY))
                cb.toggled.connect(lambda v, c=cls: self.toggle(c, v))
                self._boxes[cls.KEY] = cb
                self._cls_by_key[cls.KEY] = cls
                rh.addWidget(cb, 1)
                gear = QPushButton("⚙", objectName="gear")
                gear.setToolTip("Configure in app")
                gear.setCursor(Qt.PointingHandCursor)
                gear.setFixedWidth(30)
                gear.clicked.connect(lambda _=False, c=cls: self._open_settings_page(c))
                rh.addWidget(gear)
                lay.addWidget(r)
                if config.is_enabled(cls.KEY):
                    self.toggle(cls, True)
            sep = QFrame(objectName="sep")
            sep.setFrameShape(QFrame.HLine)
            lay.addWidget(sep)
        lay.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self._build_settings_page()                       # страница 1: настройки виджета (в приложении)

        # глобальный хоткей Ctrl+Shift+L → режим правки (работает поверх игры)
        self._hotkey = GlobalHotkey(self._hotkey_toggle_edit)
        self._refresh_profiles()

    # ---------- настройки виджета ВНУТРИ приложения (как в Kapps) ----------
    def _build_settings_page(self):
        sp = QWidget()
        spl = QVBoxLayout(sp)
        spl.setContentsMargins(12, 12, 12, 12)
        spl.setSpacing(8)
        top = QHBoxLayout()
        back = QPushButton("←  Back", objectName="back")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        top.addWidget(back)
        top.addStretch(1)
        self._sp_title = QLabel("", objectName="title")
        top.addWidget(self._sp_title)
        spl.addLayout(top)
        self._sp_scroll = QScrollArea()
        self._sp_scroll.setWidgetResizable(True)
        spl.addWidget(self._sp_scroll, 1)
        spl.addWidget(QLabel("Move / resize on the overlay itself (edit mode).",
                             objectName="hint"))
        self._stack.addWidget(sp)

    def _open_settings_page(self, cls):
        key = cls.KEY
        if key not in self.widgets:                       # включаем — нужен живой экземпляр для настройки
            self._boxes[key].setChecked(True)
        w = self.widgets.get(key)
        if w is None:
            return
        from overlay.settings_dialog import WidgetSettingsDialog
        self._sp_scroll.setWidget(WidgetSettingsDialog(w, embed=True))   # заменяет прежние
        self._sp_title.setText(cls.TITLE)
        self._stack.setCurrentIndex(1)
        self._refresh_visibility()

    # ---------- режим правки / прозрачность ----------
    def set_edit(self, val):
        self.config.set_edit_mode(val)
        if self.edit_btn.isChecked() != val:
            self.edit_btn.setChecked(val)
        self._refresh_visibility()                        # в правке показываем даже вне трассы
        for w in self.widgets.values():
            w.apply_input_mode()
            w.update()                                    # показать/скрыть ⚙ и уголок сразу

    def _hotkey_toggle_edit(self):
        self.edit_btn.toggle()                            # → set_edit через toggled

    def set_opacity(self, v):
        self.op_lbl.setText(f"{v}%")
        self.config.set_opacity(v / 100.0)
        for w in self.widgets.values():
            w.apply_opacity()

    # ---------- профили раскладок ----------
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
            self.prof.addItem("— no profile —")
        self.prof.blockSignals(False)

    def _on_profile_selected(self, name):
        if name and name in self.config.profiles() and name != self.config.active_profile():
            self.config.load_profile(name)
            self._rebuild_from_config()

    def save_as_profile(self):
        name, ok = QInputDialog.getText(self, "New profile", "Layout name:")
        name = (name or "").strip()
        if ok and name:
            self.config.save_profile(name)              # снимок текущей раскладки
            self._refresh_profiles(select=name)

    def delete_profile(self):
        name = self.config.active_profile()
        if name:
            self.config.delete_profile(name)
            self._refresh_profiles()

    def _rebuild_from_config(self):
        """Пересобрать оверлеи под загруженный профиль (позиции/настройки/прозрачность)."""
        if hasattr(self, "_stack"):                       # уходим со страницы настроек — виджеты пересоздаём
            self._stack.setCurrentIndex(0)
            self._sp_scroll.takeWidget()
        for w in list(self.widgets.values()):
            w.close()
            w.deleteLater()
        self.widgets.clear()
        for key, cb in self._boxes.items():             # синхронизировать галочки
            cb.blockSignals(True)
            cb.setChecked(self.config.is_enabled(key))
            cb.blockSignals(False)
        for key, cls in self._cls_by_key.items():       # создать включённые заново (свежая геометрия)
            if self.config.is_enabled(key):
                self.widgets[key] = cls(self.store, self.config)
        self._refresh_visibility()                       # показать по правилам (правка/вне трассы)
        self.op.blockSignals(True)                      # синхронизировать ползунок прозрачности
        self.op.setValue(int(self.config.opacity() * 100))
        self.op.blockSignals(False)
        self.op_lbl.setText(f"{self.op.value()}%")
        self._update_active()

    def _toggle_group(self, gkey):
        """Скрыть/показать все виджеты группы разом (по кнопке)."""
        target = [k for k in self._boxes if self._group_by_key.get(k) == gkey]
        any_on = any(self._boxes[k].isChecked() for k in target)
        for k in target:
            self._boxes[k].setChecked(not any_on)

    def toggle(self, cls, show):
        self.config.set_enabled(cls.KEY, show)
        if show and cls.KEY not in self.widgets:
            self.widgets[cls.KEY] = cls(self.store, self.config)
        self._refresh_visibility()

    def set_hide_offtrack(self, val):
        self.config.set_hide_offtrack(val)
        self._refresh_visibility()

    def _refresh_visibility(self):
        """Видимость оверлея = включён И (режим правки ИЛИ не прячем вне трассы ИЛИ на трассе).
        Даёт Kapps-логику «скрывать в меню/реплее», не ломая ручные тумблеры."""
        hide = self.config.hide_offtrack()
        on = bool((self.store.get("live") or {}).get("on_track"))
        edit = self.config.edit_mode()
        changed = False
        for key, w in self.widgets.items():
            should = self.config.is_enabled(key) and (edit or not hide or on)
            if w.isVisible() != should:
                w.setVisible(should)
                if should:                                # после показа — native exstyle + прозрачность
                    w.apply_input_mode()
                    w.apply_opacity()
                changed = True
        if changed:
            self._update_active()

    def _update_active(self):
        """Опрашивать только те эндпоинты, что нужны видимым виджетам."""
        active = set()
        for w in self.widgets.values():
            if w.isVisible():
                active.update(w.ENDPOINTS)
        self.store.set_active(active)

    def repaint_all(self):
        if self.store.ok:
            self.status.setText("<span style='color:#2ecc71'>🟢 data flowing</span>")
        else:
            self.status.setText("<span style='color:#e74c3c'>🔴 start «Race Engineer (Race)»</span>")
        self._refresh_visibility()                        # авто-скрытие вне трассы (если включено)
        for w in self.widgets.values():
            if w.isVisible():
                w.update()

    def closeEvent(self, e):
        for w in self.widgets.values():
            w.close()
        e.accept()
