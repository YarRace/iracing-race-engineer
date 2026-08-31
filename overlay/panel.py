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
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel,
                               QFrame, QScrollArea, QPushButton, QSlider, QComboBox,
                               QInputDialog, QLineEdit, QSizePolicy, QSplitter,
                               QGridLayout, QStackedWidget)

from overlay.hotkey import GlobalHotkey
from overlay.preview import BACKDROPS, PreviewCanvas

GROUPS = [("solo", "🟢 SOLO"), ("endur", "🔵 ENDURANCE"), ("setup", "🟣 SETUP")]

# Готовые наборы. Сорок пять виджетов — это каталог, и выбирать из него
# с нуля человек не хочет: он хочет ехать. Удалять «лишние» при этом
# неправильно — они не лишние, это разные формы одного и того же
# (крупная цифра / полоса / бегущий график), и каждому подходит своё.
# Правильный ответ не «убрать», а «выбрать за него первый раз».
STARTERS = [
    ("Sprint race", ["inputs", "shift", "delta", "relative", "position",
                     "fuel", "radar", "flags"]),
    ("Endurance", ["inputs", "fuel", "e_driver", "e_time", "e_incidents",
                   "relative", "standings", "wear", "weather", "trackmap"]),
    ("Practice / hotlap", ["inputs", "shift", "deltatrace", "laptimegraph",
                           "timing", "topspeed", "cornerloss", "trackmap"]),
]

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
QPushButton#fav { background:transparent; border:none; padding:2px 4px; font-size:13px; color:#3a4150; }
QPushButton#fav:hover { color:#e74c3c; }
QPushButton#fav:checked { color:#e74c3c; }
QPushButton#open { background:#1d4ed8; border:none; border-radius:8px; padding:9px 12px;
  font-weight:700; color:#eaf1ff; }
QPushButton#open:hover { background:#2563eb; }
QPushButton#open:checked { background:#17512f; }
QFrame#card { background:#14181e; border:1px solid #20262e; border-radius:12px; }
QFrame#sep { color:#1b2027; max-height:1px; }
QSlider::groove:horizontal { height:6px; background:#232a33; border-radius:3px; }
QSlider::sub-page:horizontal { background:#3ea6ff; border-radius:3px; }
QSlider::handle:horizontal { width:14px; background:#e8eaed; border-radius:7px; margin:-5px 0; }
"""


def _btn_text(title):
    """Название для кнопки.

    Qt считает «&» в тексте кнопки началом горячей клавиши и съедает его,
    подчёркивая следующую букву: «Fuel & pit» превращалось в «Fuel _pit».
    Удваиваем — так символ рисуется как есть.
    """
    return title.replace("&", "&&")


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
    def __init__(self, store, config, widget_classes, embedded=False):
        super().__init__()
        # Внутри общего окна своя шапка не нужна: логотип и индикатор связи
        # уже стоят наверху приложения, и вторая пара выглядит как ошибка.
        self.embedded = embedded
        self.setWindowTitle("Race Engineer — Overlays")
        self.resize(1180, 720)
        self.setStyleSheet(QSS)
        self.store = store
        self.config = config
        self.widgets = {}                     # key -> живой оверлей поверх игры
        self._boxes = {}                      # key -> QCheckBox «включён»
        self._rows = {}                       # key -> QPushButton строки списка
        self._favs = {}                       # key -> кнопка-сердечко
        self._group_by_key = {}
        self._cls_by_key = {}
        self._selected = None                 # какой виджет показан в центре

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(8)
        root.addLayout(self._build_header())

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self._build_list(widget_classes))
        self.split.addWidget(self._build_preview())
        self.split.addWidget(self._build_settings())
        self.split.setSizes([250, 610, 320])
        self.split.setStretchFactor(1, 1)
        root.addWidget(self.split, 1)

        root.addWidget(self._build_footer())

        self._hotkey = GlobalHotkey(self._hotkey_toggle_edit)
        self._refresh_profiles()
        self._rebuild_favourites()
        first = widget_classes[0] if widget_classes else None
        if first is not None:
            self.select(first.KEY)

    # ───────────────────────────── шапка ────────────────────────────────────
    def _build_header(self):
        h = QHBoxLayout()
        self.status = QLabel("● …")
        if not self.embedded:
            h.addWidget(QLabel("🏁 Race Engineer", objectName="title"))
            h.addSpacing(12)
            h.addWidget(self.status)
        else:
            self.status.hide()
        h.addStretch(1)
        # ОДИН список наборов, а не два. Раньше готовые наборы лежали в одном
        # выпадающем списке, а свои — в другом, рядом. С точки зрения человека
        # это одно и то же желание («покажи вот эти виджеты»), и держать его
        # в двух местах значит заставлять помнить, в каком из них искать.
        h.addWidget(QLabel("Set", objectName="hint"))
        self.prof = QComboBox()
        self.prof.setMinimumWidth(190)
        self.prof.activated.connect(self._on_set_picked)
        h.addWidget(self.prof)
        delb = QPushButton("🗑", objectName="tiny")
        delb.setToolTip("Delete the set you are on (only your own)")
        delb.clicked.connect(self.delete_profile)
        h.addWidget(delb)
        # Обмен раскладками одним файлом: перенос на второй компьютер и
        # обратная дорога, если правки завели не туда.

        expb = QPushButton("Export", objectName="tiny")
        expb.setToolTip("Export this layout to a file")
        expb.clicked.connect(self.export_layout)
        h.addWidget(expb)
        impb = QPushButton("Import", objectName="tiny")
        impb.setToolTip("Import a layout from a file")
        impb.clicked.connect(self.import_layout)
        h.addWidget(impb)
        return h

    # ──────────────────────── левая колонка: список ─────────────────────────
    def _build_list(self, widget_classes):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(QLabel("OVERLAYS", objectName="colhead"))
        head.addStretch(1)
        # Список — быстро искать, галерея — узнавать в лицо. У RaceLab
        # только карточки, но сорок пять картинок листать дольше, чем
        # набрать три буквы. Поэтому оба вида и переключатель.
        self.view_btn = QPushButton("gallery", objectName="link")
        self.view_btn.setCheckable(True)
        self.view_btn.setCursor(Qt.PointingHandCursor)
        self.view_btn.toggled.connect(self._toggle_view)
        head.addWidget(self.view_btn)
        lay.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search overlays…")
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

        # Избранное отдельной группой сверху: сорок четыре строки — это
        # прокрутка на каждый чих, а нужных обычно десяток.
        fav_head = QWidget()
        fh = QHBoxLayout(fav_head)
        fh.setContentsMargins(0, 2, 0, 2)
        fh.addWidget(QLabel("♥ FAVOURITES", objectName="group"))
        fh.addStretch(1)
        il.addWidget(fav_head)
        self._fav_head = fav_head
        self._fav_box = QWidget()
        self._fav_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._fav_lay = QVBoxLayout(self._fav_box)
        self._fav_lay.setContentsMargins(0, 0, 0, 0)
        self._fav_lay.setSpacing(2)
        il.addWidget(self._fav_box)

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
            btn = QPushButton("hide all", objectName="link")
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

        # Два вида в стопке: список и галерея. Галерея строится ЛЕНИВО,
        # при первом показе — сорок пять картинок с диска на старте окна
        # это лишняя секунда на пустом месте.
        self.views = QStackedWidget()
        self.views.addWidget(scroll)
        self._gallery = QScrollArea()
        self._gallery.setWidgetResizable(True)
        self.views.addWidget(self._gallery)
        self._gallery_built = False
        lay.addWidget(self.views, 1)
        return box

    def _toggle_view(self, gallery):
        """Галерея шире списка: карточка со снимком в колонку на 250 пикселей
        не помещается — картинка обрезается ровно там, где на неё смотрят.
        Поэтому вместе с видом меняется и ширина колонки."""
        self.view_btn.setText("list" if gallery else "gallery")
        if gallery and not self._gallery_built:
            self._build_gallery()
        self.views.setCurrentIndex(1 if gallery else 0)
        total = sum(self.split.sizes()) or self.width() or 1180
        if gallery:
            self.split.setSizes([380, max(300, total - 700), 320])
        else:
            self.split.setSizes([250, max(300, total - 570), 320])

    def _build_gallery(self):
        """Карточки со снимками виджетов — узнать в лицо, а не по названию.

        Снимки те же, что на сайте (docs/widgets/*.png, tools/render_widgets.py).
        Нет файла — карточка всё равно есть, просто без картинки: галерея
        не должна разваливаться оттого, что снимки не собирали.
        """
        from ire import paths
        self._gallery_built = True
        shots = paths.res_root() / "docs" / "widgets"

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 6, 0)
        grid.setSpacing(8)
        for i, (key, cls) in enumerate(sorted(self._cls_by_key.items(),
                                              key=lambda kv: kv[1].TITLE.lower())):
            card = QFrame(objectName="card")
            v = QVBoxLayout(card)
            v.setContentsMargins(8, 8, 8, 8)
            v.setSpacing(4)
            pic = QLabel()
            pic.setAlignment(Qt.AlignCenter)
            pic.setMinimumHeight(64)
            f = shots / f"{key}.png"
            if f.exists():
                pm = QPixmap(str(f))
                if not pm.isNull():
                    # Ширина под ячейку сетки, а не «на глаз»: карточка
                    # шире колонки обрезается ровно там, куда смотрят.
                    pic.setPixmap(pm.scaledToWidth(155, Qt.SmoothTransformation))
            else:
                pic.setText("no snapshot")
                pic.setObjectName("hint")
            v.addWidget(pic)

            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(self.config.is_enabled(key))
            cb.setToolTip("Include in the layout")
            cb.toggled.connect(lambda on, c=cls: self.toggle(c, on))
            self._boxes[key].toggled.connect(
                lambda on, box=cb: (box.blockSignals(True), box.setChecked(on),
                                    box.blockSignals(False)))
            row.addWidget(cb)
            name = QPushButton(_btn_text(cls.TITLE), objectName="row")
            name.setCursor(Qt.PointingHandCursor)
            name.clicked.connect(lambda _=False, k=key: self.select(k))
            row.addWidget(name, 1)
            v.addLayout(row)
            grid.addWidget(card, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(grid.rowCount(), 1)
        self._gallery.setWidget(inner)

    def _build_row(self, cls):
        """Строка списка: галочка «включён» + кнопка выбора для предпросмотра."""
        r = QWidget()
        rh = QHBoxLayout(r)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(2)

        cb = QCheckBox()
        cb.setChecked(self.config.is_enabled(cls.KEY))
        cb.setToolTip("Include in the layout — Start overlays shows it")
        cb.toggled.connect(lambda v, c=cls: self.toggle(c, v))
        self._boxes[cls.KEY] = cb
        self._cls_by_key[cls.KEY] = cls
        rh.addWidget(cb)

        btn = QPushButton(_btn_text(cls.TITLE), objectName="row")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _=False, k=cls.KEY: self.select(k))
        self._rows[cls.KEY] = btn
        rh.addWidget(btn, 1)

        fav = QPushButton("♥", objectName="fav")
        fav.setCheckable(True)
        fav.setChecked(self.config.is_favourite(cls.KEY))
        fav.setToolTip("Add to favourites — moves to the top of the list")
        fav.setCursor(Qt.PointingHandCursor)
        fav.setFixedWidth(24)
        fav.toggled.connect(lambda v, k=cls.KEY: self._toggle_fav(k, v))
        self._favs[cls.KEY] = fav
        rh.addWidget(fav)

        r.setProperty("wkey", cls.KEY)
        return r

    def _toggle_fav(self, key, on):
        """Сердечко: виджет уезжает в группу «Избранное» и обратно."""
        self.config.set_favourite(key, on)
        self._rebuild_favourites()

    def _rebuild_favourites(self):
        """Дубли строк для избранного.

        Именно КОПИИ, а не перенос: строка в своей группе должна остаться,
        иначе виджет пропадает из привычного места и его ищут заново.
        """
        while self._fav_lay.count():
            it = self._fav_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        keys = [k for k in self.config.favourites() if k in self._cls_by_key]
        for key in keys:
            cls = self._cls_by_key[key]
            row = QWidget()
            # Высоту задаём явно: вложенный контейнер сжимался родительской
            # раскладкой до 11 пикселей, и от строки оставалась одна галочка
            # без названия — выглядело как пустая группа.
            row.setMinimumHeight(26)
            rh = QHBoxLayout(row)
            rh.setContentsMargins(0, 0, 0, 0)
            rh.setSpacing(2)
            cb = QCheckBox()
            cb.setChecked(self.config.is_enabled(key))
            cb.toggled.connect(lambda v, c=cls: self.toggle(c, v))
            # держим обе галочки в согласии: их две на один виджет
            self._boxes[key].toggled.connect(
                lambda v, box=cb: (box.blockSignals(True), box.setChecked(v),
                                   box.blockSignals(False)))
            rh.addWidget(cb)
            b = QPushButton(_btn_text(cls.TITLE), objectName="row")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            rh.addWidget(b, 1)
            self._fav_lay.addWidget(row)
        # Контейнер не пересчитывает себя сам после добавления детей —
        # оставался 25 пикселей и обрезал все строки, кроме первой.
        self._fav_box.setMinimumHeight(len(keys) * 28 if keys else 0)
        self._fav_head.setVisible(bool(keys))
        self._fav_box.setVisible(bool(keys))

    def _filter_list(self, text):
        """Поиск по названию. Пустые группы прячем целиком, чтобы не мозолили."""
        q = (text or "").strip().lower()
        shown = {g: 0 for g, _ in GROUPS}
        for key, btn in self._rows.items():
            row = btn.parentWidget()
            ok = not q or q in btn.text().replace("&&", "&").lower()
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
        lay.addWidget(QLabel("PREVIEW", objectName="colhead"))

        # Предпросмотр берёт демо-поток, когда сим молчит: настраивать виджет
        # по прочеркам бессмысленно — не видно ни цветов, ни ширины колонок.
        from overlay.demo import DemoFeed
        self._demo = DemoFeed()
        self.preview = PreviewCanvas(_PreviewStore(self.store, self._demo), self.config)
        lay.addWidget(self.preview, 1)

        bar = QHBoxLayout()
        self.demo_cb = QCheckBox("Demo data when the sim is off")
        self.demo_cb.setChecked(True)
        self.demo_cb.setToolTip("Turn off to see the real dashes")
        self.demo_cb.toggled.connect(lambda v: setattr(self.preview.store, "allow_demo", v))
        bar.addWidget(self.demo_cb)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Backdrop", objectName="hint"))
        self.bg = QComboBox()
        self.bg.addItems([b[0] for b in BACKDROPS])
        self.bg.currentIndexChanged.connect(self.preview.set_backdrop)
        bar.addWidget(self.bg)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Zoom", objectName="hint"))
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
        lay.addWidget(QLabel("SETTINGS", objectName="colhead"))

        card = QFrame(objectName="card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(2)
        self.sel_name = QLabel("—", objectName="wname")
        cl.addWidget(self.sel_name)
        self.sel_meta = QLabel("", objectName="wmeta")
        cl.addWidget(self.sel_meta)
        lay.addWidget(card)

        # Крупная кнопка вместо галочки: у RaceLab это главное действие
        # карточки, и оно должно читаться с одного взгляда.
        self.open_btn = QPushButton("Add to layout", objectName="open")
        self.open_btn.setCheckable(True)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.toggled.connect(self._toggle_selected)
        lay.addWidget(self.open_btn)
        self.sel_on = self.open_btn                  # прежнее имя — для совместимости

        prow = QHBoxLayout()
        prow.addWidget(QLabel("Preset", objectName="hint"))
        self.wpreset = QComboBox()
        self.wpreset.setMinimumWidth(110)
        self.wpreset.activated.connect(self._load_widget_preset)
        prow.addWidget(self.wpreset, 1)
        pa = QPushButton("+", objectName="tiny")
        pa.setToolTip("Save this widget's settings")
        pa.clicked.connect(self._save_widget_preset)
        prow.addWidget(pa)
        pd = QPushButton("🗑", objectName="tiny")
        pd.setToolTip("Delete preset")
        pd.clicked.connect(self._delete_widget_preset)
        prow.addWidget(pd)
        lay.addLayout(prow)

        # Накликанное оформление откатить было нечем: только руками в
        # overlay_config.json, а туда лезть страшно и незачем.
        self.reset_btn = QPushButton("Reset to defaults", objectName="tiny")
        self.reset_btn.setToolTip("Colours, sizes, fonts, hidden rows, position "
                                  "and size — back to factory")
        self.reset_btn.clicked.connect(self.reset_selected)
        lay.addWidget(self.reset_btn)

        self.sfilter = QLineEdit()
        self.sfilter.setPlaceholderText("Filter settings…")
        self.sfilter.setClearButtonEnabled(True)
        self.sfilter.textChanged.connect(self._filter_settings)
        lay.addWidget(self.sfilter)

        self.sscroll = QScrollArea()
        self.sscroll.setWidgetResizable(True)
        lay.addWidget(self.sscroll, 1)
        lay.addWidget(QLabel("Move and resize on the overlay itself, in edit mode.",
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

        self.edit_btn = QPushButton("✏️  Edit mode", objectName="edit")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setChecked(self.config.edit_mode())
        self.edit_btn.setToolTip("Drag overlays with the mouse. Otherwise clicks go "
                                 "to the game. Hotkey Ctrl+Shift+L")
        self.edit_btn.toggled.connect(self.set_edit)
        h.addWidget(self.edit_btn)

        h.addWidget(QLabel("Opacity", objectName="hint"))
        self.op = QSlider(Qt.Horizontal)
        self.op.setRange(30, 100)
        self.op.setValue(int(self.config.opacity() * 100))
        self.op.setFixedWidth(160)
        self.op.valueChanged.connect(self.set_opacity)
        h.addWidget(self.op)
        self.op_lbl = QLabel(f"{self.op.value()}%", objectName="hint")
        self.op_lbl.setMinimumWidth(36)
        h.addWidget(self.op_lbl)

        self.hide_cb = QCheckBox("Hide when off track (menus and replays)")
        self.hide_cb.setChecked(self.config.hide_offtrack())
        self.hide_cb.toggled.connect(self.set_hide_offtrack)
        h.addWidget(self.hide_cb)
        h.addStretch(1)

        # Сброс всего — в подвале, рядом с остальными «на весь оверлей»
        # переключателями, и подальше от кнопки одного виджета.
        self.reset_all_btn = QPushButton("Reset all overlays", objectName="tiny")
        self.reset_all_btn.setToolTip("Every widget back to factory look, "
                                      "position and size. A backup is saved first.")
        self.reset_all_btn.clicked.connect(self.reset_all)
        h.addWidget(self.reset_all_btn)
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
        group = {"solo": "Solo", "endur": "Endurance", "setup": "Setup"}.get(
            self._group_by_key.get(key, "solo"), "")
        w, hgt = cls.DEFAULT
        self.sel_meta.setText(f"{group}  ·  {w}×{hgt} default  ·  "
                              f"data: {', '.join(cls.ENDPOINTS) or '—'}")
        on = self.config.is_enabled(key)
        self.open_btn.blockSignals(True)
        self.open_btn.setChecked(on)
        self.open_btn.setText("In the layout" if on else "Add to layout")
        self.open_btn.blockSignals(False)
        self._refresh_widget_presets()

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

    # ---------- пресеты одного виджета ----------
    def _refresh_widget_presets(self):
        """Профиль хранит ВСЮ раскладку. Перенести вид одного виджета между
        раскладками профилем нельзя — он утащит позиции и включённость всех
        остальных. Отсюда отдельные пресеты на виджет."""
        self.wpreset.blockSignals(True)
        self.wpreset.clear()
        names = self.config.widget_presets(self._selected or "")
        self.wpreset.addItem("— none —" if not names else "— choose —")
        self.wpreset.addItems(names)
        self.wpreset.blockSignals(False)

    def _save_widget_preset(self):
        if not self._selected:
            return
        name, ok = QInputDialog.getText(self, "Widget preset", "Name:")
        name = (name or "").strip()
        if ok and name:
            self.config.save_widget_preset(self._selected, name)
            self._refresh_widget_presets()
            self.wpreset.setCurrentText(name)

    def _load_widget_preset(self, index):
        name = self.wpreset.itemText(index)
        if index <= 0 or not self._selected:
            return
        if self.config.load_widget_preset(self._selected, name):
            self.select(self._selected)               # пересобрать предпросмотр и настройки

    def _delete_widget_preset(self):
        name = self.wpreset.currentText()
        if self._selected and self.wpreset.currentIndex() > 0:
            self.config.delete_widget_preset(self._selected, name)
            self._refresh_widget_presets()

    def reset_selected(self, confirm=True):
        """Сбросить выбранный виджет к заводскому виду.

        Спрашиваем: накликанное оформление — это полчаса работы, и вернуть
        его после случайного нажатия неоткуда. `confirm=False` — для тестов
        и для вызова из кода.
        """
        key = self._selected
        if not key:
            return False
        if confirm:
            from PySide6.QtWidgets import QMessageBox
            cls = self._cls_by_key.get(key)
            title = cls.TITLE if cls is not None else key
            answer = QMessageBox.question(
                self, "Reset to defaults",
                f"Reset “{title}” — colours, sizes, fonts, hidden rows, "
                f"position and size?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return False

        self.config.reset_widget(key)
        live = self.widgets.get(key)
        if live is not None:                 # боевой виджет уже на экране
            cls = self._cls_by_key[key]
            live.resize(*cls.DEFAULT)
            live.update()
        self.select(key)                     # предпросмотр и настройки — заново
        return True

    def _apply_starter(self, index):
        """Включить готовый набор. Прежний выбор СТИРАЕТСЯ — иначе поверх
        своей раскладки лёг бы чужой набор, и на экране оказалось бы всё
        сразу, чего никто не просил."""
        if index <= 0:
            return
        name, keys = STARTERS[index - 1]
        want = set(keys)
        for key, box in self._boxes.items():
            box.setChecked(key in want)
        if self._selected:
            self.select(self._selected)

    def reset_all(self, confirm=True):
        """Сбросить вид ВСЕХ виджетов. Перед этим — резервная копия.

        Кнопка стирает работу целого вечера одним нажатием, поэтому копия
        не опция: без неё «отмена» есть только у того, кто заранее сделал
        экспорт, а заранее его не делает никто.
        """
        backup = self.config.backup_layout()
        if confirm:
            from PySide6.QtWidgets import QMessageBox
            where = f"\n\nA backup was saved to\n{backup}" if backup else ""
            answer = QMessageBox.question(
                self, "Reset all overlays",
                "Every widget goes back to its factory look, position and size."
                "\nWhich overlays are on, your favourites and your saved layouts "
                "stay as they are." + where,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return False

        self.config.reset_all()
        for key, w in self.widgets.items():
            cls = self._cls_by_key.get(key)
            if cls is not None:
                w.resize(*cls.DEFAULT)
            w.apply_opacity()
            w.update()
        self.op.blockSignals(True)
        self.op.setValue(int(self.config.opacity() * 100))
        self.op.blockSignals(False)
        self.op_lbl.setText(f"{self.op.value()}%")
        if self._selected:
            self.select(self._selected)
        return True

    # ───────────────────── обмен раскладками файлом ─────────────────────────
    def export_layout(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        suggested = (self.config.active_profile() or "layout") + ".json"
        path, _ = QFileDialog.getSaveFileName(self, "Export layout", suggested,
                                              "Layout files (*.json)")
        if not path:
            return None
        try:
            name = self.config.export_layout(path)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return None
        QMessageBox.information(self, "Layout exported",
                                f"“{name}” saved to\n{path}")
        return path

    def import_layout(self):
        import os

        from PySide6.QtWidgets import QFileDialog, QMessageBox
        # Открываемся в папке автоснимков: самый частый импорт — не «принёс
        # файл с флешки», а «верни как было вчера».
        start = os.path.join(os.path.dirname(os.path.abspath(self.config.path)),
                             self.config.BACKUP_DIR)
        if not os.path.isdir(start):
            start = ""
        path, _ = QFileDialog.getOpenFileName(self, "Import layout", start,
                                              "Layout files (*.json)")
        if not path:
            return None
        try:
            name = self.config.import_layout(path)
        except (OSError, ValueError) as exc:
            # Отдельное сообщение, а не молчание: подсунуть сюда чужой JSON
            # легко, и тогда непонятно, почему ничего не изменилось.
            QMessageBox.warning(self, "Import failed", str(exc))
            return None
        self._rebuild_from_config()
        self._rebuild_favourites()
        for key, fav in self._favs.items():
            fav.blockSignals(True)
            fav.setChecked(self.config.is_favourite(key))
            fav.blockSignals(False)
        self._refresh_profiles(select=name)
        return name

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

    # ───────────────────────────── наборы ───────────────────────────────────
    # Готовый набор и свой набор — разные вещи, и разница видна на экране.
    # Готовый только СТАВИТ ГАЛОЧКИ: места виджетов остаются там, куда их
    # поставил человек, — иначе выбор набора раскидывал бы выстроенный экран.
    # Свой набор возвращает всё, включая места: он для того и сохранялся.
    SAVE_ITEM = "+  Save what I have now as a set…"

    def _refresh_profiles(self, select=None):
        """Пересобрать список: сначала готовые, потом свои, внизу «сохранить».

        Разделители — не украшение: без них свой набор с именем «Spa night»
        стоит вплотную к «Endurance», и непонятно, почему один переставляет
        виджеты, а другой нет.
        """
        self.prof.blockSignals(True)
        self.prof.clear()
        self._set_rows = []                    # что означает каждая строка

        self.prof.addItem("— pick a set —")
        self._set_rows.append(("none", ""))
        for name, _ in STARTERS:
            self.prof.addItem(name)
            self._set_rows.append(("starter", name))

        mine = self.config.profiles()
        if mine:
            self.prof.insertSeparator(self.prof.count())
            self._set_rows.append(("sep", ""))
            for name in mine:
                self.prof.addItem(name)
                self._set_rows.append(("mine", name))

        self.prof.insertSeparator(self.prof.count())
        self._set_rows.append(("sep", ""))
        self.prof.addItem(self.SAVE_ITEM)
        self._set_rows.append(("save", ""))

        active = select or self.config.active_profile()
        if active:
            for i, (kind, name) in enumerate(self._set_rows):
                if kind == "mine" and name == active:
                    self.prof.setCurrentIndex(i)
                    break
        self.prof.blockSignals(False)

    def _on_set_picked(self, index):
        kind, name = (self._set_rows[index] if 0 <= index < len(self._set_rows)
                      else ("none", ""))
        if kind == "starter":
            self._apply_starter([n for n, _ in STARTERS].index(name) + 1)
        elif kind == "mine":
            # Грузим ВСЕГДА, даже если этот набор уже значится активным.
            # Именно в этом случае он и нужен: человек сохранил набор, потом
            # всё сдвинул и выбирает его же, чтобы вернуть как было. Проверка
            # «уже активный» превращала эту кнопку в ничего не делающую.
            self.config.load_profile(name)
            self._rebuild_from_config()
        elif kind == "save":
            self.save_as_profile()
        else:                                  # заголовок или разделитель
            self._refresh_profiles()

    def save_as_profile(self):
        name, ok = QInputDialog.getText(self, "Save set", "Name:")
        name = (name or "").strip()
        if not (ok and name):
            self._refresh_profiles()           # передумал — вернуть список в вид
            return
        # Набор — снимок, и запись поверх существующего стирает его насовсем.
        # Спрашиваем ровно в этом случае: на новом имени вопрос был бы шумом.
        if name in self.config.profiles():
            from PySide6.QtWidgets import QMessageBox
            q = QMessageBox.question(
                self, "Replace set",
                f"There is already a set called «{name}». "
                "Replace it with what is on screen now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if q != QMessageBox.Yes:
                self._refresh_profiles()
                return
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

    def set_overlays_running(self, on):
        """Показать или убрать всю раскладку разом."""
        self.config.set_overlays_running(on)
        self._refresh_visibility()
        if on:
            for w in self.widgets.values():
                if w.isVisible():
                    w.apply_input_mode()
                    w.apply_opacity()

    def toggle(self, cls, show):
        self.config.set_enabled(cls.KEY, show)
        if show and cls.KEY not in self.widgets:
            self.widgets[cls.KEY] = cls(self.store, self.config)
        if self._selected == cls.KEY and hasattr(self, "open_btn"):
            self.open_btn.blockSignals(True)
            self.open_btn.setChecked(show)
            self.open_btn.setText("In the layout" if show else "Add to layout")
            self.open_btn.blockSignals(False)
        self._refresh_visibility()

    def set_hide_offtrack(self, val):
        self.config.set_hide_offtrack(val)
        self._refresh_visibility()

    def _refresh_visibility(self):
        """Видимость = ЗАПУЩЕНЫ И включён И (правка ИЛИ не прячем ИЛИ на трассе).

        Первое условие новое. Раньше галочка выбрасывала виджет на экран
        немедленно, и собрать раскладку спокойно было нельзя: половина экрана
        занята ещё до того, как выбрал остальное. Теперь галочка означает
        «входит в раскладку», а показывает всё кнопка «Start overlays».
        """
        hide = self.config.hide_offtrack()
        on = bool((self.store.get("live") or {}).get("on_track"))
        edit = self.config.edit_mode()
        live = self.config.overlays_running()
        changed = False
        for key, w in self.widgets.items():
            should = (live and self.config.is_enabled(key)
                      and (edit or not hide or on))
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
            self.status.setText("<span style='color:#2ecc71'>🟢 data flowing</span>")
        else:
            self.status.setText("<span style='color:#e74c3c'>🔴 start run.py</span>")
        self._refresh_visibility()
        for w in self.widgets.values():
            if w.isVisible():
                w.update()

    def closeEvent(self, e):
        # Снимок раскладки на выход. Конфиг перезаписывается на каждое
        # движение ползунка, так что «вчерашнего» состояния нигде не было:
        # заметить, что вчера было лучше, обычно получается уже назавтра.
        self.config.backup_layout()
        for w in self.widgets.values():
            w.close()
        e.accept()
