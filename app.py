#!/usr/bin/env python3
"""Race Engineer — ОДНО приложение вместо двух.

Раньше запускались два процесса: инженер (читает сим, отдаёт дашборд) и
панель оверлея. Порядок имел значение, окон было два, и человек честно
спрашивал, почему нельзя одной кнопкой. Лаунчер это сгладил, но не убрал:
он всё равно открывал два окна.

Здесь инженер крутится ФОНОВЫМ ПОТОКОМ внутри этого же процесса, а окно
одно, с верхней панелью страниц — как в приложении RaceLab:

    ┌───────────────────────────────────────────────────────┐
    │ 🏁  Home │ Overlays │ Dashboard │ News        ● статус │
    ├───────────────────────────────────────────────────────┤
    │                                                       │
    │                    выбранная страница                 │
    │                                                       │
    ├───────────────────────────────────────────────────────┤
    │  [ Start overlays ]        12 в раскладке             │
    └───────────────────────────────────────────────────────┘

Главное отличие от того, что было: галочка у виджета больше НЕ выбрасывает
его на экран немедленно. Она означает «входит в раскладку», а показывает
всё кнопка внизу. Так собирают набор у RaceLab, и так это можно сделать
спокойно — не воюя с половиной экрана, занятой уже включённым.

Дашборд остаётся страницей в браузере: встроить его сюда значит утащить
QtWebEngine, а это 150 МБ к сборке ради окна, которое у человека и так
открыто на втором экране.

Запуск:
    python app.py
"""
import os
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ire import preflight                                        # noqa: E402
preflight.check(extra=preflight.OVERLAY + [("irsdk", "pyirsdk")])

from PySide6.QtCore import Qt, QTimer                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel,  # noqa: E402
                               QPushButton, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

from ire import paths                                            # noqa: E402
from overlay.config import Config                                # noqa: E402
from overlay.panel import ControlPanel                           # noqa: E402
from overlay.store import Store                                  # noqa: E402
from overlay.widgets import WIDGETS                              # noqa: E402

PORT = int(os.environ.get("IRE_PORT", "8000"))
DASH = f"http://localhost:{PORT}"

QSS = """
QWidget { background:#0f1216; color:#e8eaed; font-family:'Segoe UI'; font-size:13px; }
QScrollArea { border:none; }
QLabel#logo { font-size:16px; font-weight:800; letter-spacing:.5px; }
QLabel#h1 { font-size:22px; font-weight:800; }
QLabel#h2 { font-size:11px; font-weight:800; letter-spacing:1.4px; color:#7d8797; }
QLabel#dim { color:#69727f; }
QLabel#big { font-size:26px; font-weight:800; }
QPushButton#tab { background:transparent; border:none; color:#8a93a0;
  padding:8px 14px; border-radius:9px; font-weight:600; }
QPushButton#tab:hover { color:#e8eaed; background:#161b21; }
QPushButton#tab:checked { color:#e8eaed; background:#1d2b3d; }
QPushButton#go { background:#1d4ed8; border:none; border-radius:9px;
  padding:11px 22px; font-weight:800; color:#eaf1ff; }
QPushButton#go:hover { background:#2563eb; }
QPushButton#go:checked { background:#17512f; }
QPushButton#link { background:#181c22; border:1px solid #2a2f38; border-radius:9px;
  padding:9px 16px; }
QPushButton#link:hover { background:#232a33; }
QWidget#card { background:#14181e; border:1px solid #20262e; border-radius:12px; }
QWidget#bar { background:#0c0f13; border-top:1px solid #1b2027; }
QWidget#top { background:#0c0f13; border-bottom:1px solid #1b2027; }
"""


class Engineer:
    """Инженер в фоновом потоке этого же процесса.

    Поток демонический: закрыли окно — умер вместе с приложением. Круги
    он дописывает сам по ходу дела, так что терять на выходе нечего.
    """

    def __init__(self):
        self.thread = None
        self.error = ""

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            import run
            run.main()
        except BaseException as e:                               # noqa: BLE001
            # Падение инженера не должно уносить окно: человек как минимум
            # должен УВИДЕТЬ, что случилось, а не остаться с пустым экраном.
            self.error = f"{type(e).__name__}: {e}"

    @property
    def alive(self):
        return bool(self.thread and self.thread.is_alive())


def card(*widgets, pad=16):
    w = QWidget(objectName="card")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(pad, pad, pad, pad)
    lay.setSpacing(6)
    for x in widgets:
        lay.addWidget(x) if isinstance(x, QWidget) else lay.addLayout(x)
    return w


def stat(value, label):
    box = QWidget(objectName="card")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(0)
    v = QLabel(str(value), objectName="big")
    lay.addWidget(v)
    lay.addWidget(QLabel(label, objectName="dim"))
    box.value_label = v
    return box


class Home(QWidget):
    """Что происходит прямо сейчас и что делать дальше."""

    def __init__(self, engineer, config):
        super().__init__()
        self.engineer = engineer
        self.config = config

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(14)
        lay.addWidget(QLabel("Race Engineer", objectName="h1"))
        self.sub = QLabel("Starting…", objectName="dim")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.s_laps = stat("—", "saved laps")
        self.s_over = stat("—", "in the layout")
        self.s_state = stat("—", "overlays")
        for s in (self.s_laps, self.s_over, self.s_state):
            row.addWidget(s)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addWidget(QLabel("NEXT", objectName="h2"))
        tips = QLabel(
            "1. Start iRacing in windowed or borderless mode — an overlay "
            "cannot draw over exclusive fullscreen.\n"
            "2. Open Overlays, tick what you want, then press Start overlays.\n"
            "3. Move and resize them with Ctrl+Shift+L while edit mode is on.")
        tips.setWordWrap(True)
        tips.setObjectName("dim")
        lay.addWidget(card(tips))
        lay.addStretch(1)

    def refresh(self):
        if self.engineer.error:
            self.sub.setText("The engineer stopped: " + self.engineer.error)
        elif self.engineer.alive:
            self.sub.setText(f"Engineer running · dashboard at {DASH}")
        else:
            self.sub.setText("Engineer is not running.")

        try:
            from ire.storage import laps as L
            n = len(L.list_laps(L.default_root()))
        except Exception:                                        # noqa: BLE001
            n = "—"
        self.s_laps.value_label.setText(str(n))
        on = sum(1 for k in (self.config.data.get("enabled") or {})
                 if self.config.is_enabled(k))
        self.s_over.value_label.setText(str(on))
        self.s_state.value_label.setText(
            "shown" if self.config.overlays_running() else "hidden")


class News(QWidget):
    """Свой чейнджлог внутри приложения.

    Он и так рендерится на /news, но открывать браузер ради «что нового»
    никто не станет. Читаем те же файлы docs/news/*.md — один источник,
    а не вторая копия, которая разойдётся с первой на первой же записи.
    """

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 8)
        outer.setSpacing(12)
        outer.addWidget(QLabel("What changed", objectName="h1"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(0, 0, 8, 0)
        self.lay.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        self._loaded = False

    def refresh(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            from ire.dashboard import site
            entries = site.read_news()
        except Exception:                                        # noqa: BLE001
            entries = []
        if not entries:
            self.lay.addWidget(QLabel("No entries yet.", objectName="dim"))
            return
        for e in entries[:20]:
            when = QLabel(e.get("date", ""), objectName="dim")
            title = QLabel(e.get("title", ""))
            title.setStyleSheet("font-size:16px;font-weight:700")
            body = QLabel(e.get("body", "").strip())
            body.setWordWrap(True)
            body.setObjectName("dim")
            self.lay.addWidget(card(when, title, body))
        self.lay.addStretch(1)


class Dashboard(QWidget):
    """Ссылка на дашборд, а не встроенное окно.

    Встроить значит утащить QtWebEngine — 150 МБ к сборке ради того, что
    у человека и так открыто на втором экране. Дашборд для того и сделан.
    """

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Dashboard", objectName="h1"))
        t = QLabel(f"The dashboard lives in your browser at {DASH} — it is meant "
                   f"for the second screen, next to the game rather than on top "
                   f"of it.\n\n63 cards across six tabs: solo, endurance, setup, "
                   f"records, strategy and race analysis.")
        t.setWordWrap(True)
        t.setObjectName("dim")
        lay.addWidget(card(t))
        btn = QPushButton("Open the dashboard", objectName="link")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: webbrowser.open(DASH))
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

    def refresh(self):
        return


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Race Engineer")
        self.setStyleSheet(QSS)
        self.resize(1220, 780)

        self.config = Config(str(paths.data_dir() / "overlay_config.json"))
        # Оверлеи при запуске всегда спрятаны, чем бы ни закончился прошлый
        # раз. Иначе приложение открывается, а поверх игры уже что-то висит —
        # ровно та неожиданность, от которой мы и уходим.
        self.config.set_overlays_running(False)

        self.store = Store(base=DASH)
        self.engineer = Engineer()
        self.engineer.start()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top())

        self.pages = QStackedWidget()
        self.panel = ControlPanel(self.store, self.config, WIDGETS, embedded=True)
        self.home = Home(self.engineer, self.config)
        self.dash = Dashboard()
        self.news = News()
        for w in (self.home, self.panel, self.dash, self.news):
            self.pages.addWidget(w)
        root.addWidget(self.pages, 1)
        root.addWidget(self._build_bottom())

        self.store.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)                       # ~30 кадров/сек, как было
        self._slow = QTimer(self)
        self._slow.timeout.connect(self._tick_slow)
        self._slow.start(1000)
        self.show_page(0)

    # ---------- каркас ----------
    def _build_top(self):
        bar = QWidget(objectName="top")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(4)
        h.addWidget(QLabel("🏁 RACE ENGINEER", objectName="logo"))
        h.addSpacing(18)
        self.tabs = []
        for i, name in enumerate(("Home", "Overlays", "Dashboard", "News")):
            b = QPushButton(name, objectName="tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=i: self.show_page(k))
            self.tabs.append(b)
            h.addWidget(b)
        h.addStretch(1)
        self.status = QLabel("● …")
        h.addWidget(self.status)
        return bar

    def _build_bottom(self):
        bar = QWidget(objectName="bar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(14)
        self.go = QPushButton("Start overlays", objectName="go")
        self.go.setCheckable(True)
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.toggled.connect(self.set_running)
        h.addWidget(self.go)
        self.count = QLabel("", objectName="dim")
        h.addWidget(self.count)
        h.addStretch(1)
        h.addWidget(QLabel(f"dashboard: {DASH}", objectName="dim"))
        return bar

    def show_page(self, i):
        self.pages.setCurrentIndex(i)
        for k, b in enumerate(self.tabs):
            b.setChecked(k == i)
        page = self.pages.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    # ---------- запуск оверлеев ----------
    def set_running(self, on):
        self.panel.set_overlays_running(on)
        self.go.setText("Overlays are shown" if on else "Start overlays")

    def _tick(self):
        self.panel.repaint_all()

    def _tick_slow(self):
        n = sum(1 for k in (self.config.data.get("enabled") or {})
                if self.config.is_enabled(k))
        self.count.setText(f"{n} in the layout" if n else "nothing picked yet")
        if self.engineer.error:
            self.status.setText("<span style='color:#e74c3c'>🔴 engineer stopped</span>")
        elif self.store.ok:
            self.status.setText("<span style='color:#2ecc71'>🟢 data flowing</span>")
        else:
            self.status.setText("<span style='color:#e0a800'>🟡 waiting for iRacing</span>")
        if self.pages.currentWidget() is self.home:
            self.home.refresh()

    def closeEvent(self, e):
        self.config.set_overlays_running(False)
        self.panel.close()
        e.accept()


def main():
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
