#!/usr/bin/env python3
"""Одна кнопка «Старт»: поднимает инженера и оверлей вместе.

Запускать приходилось два процесса по отдельности, в правильном порядке и
из правильной папки. Забыл `run.py` — оверлей открывается с красной точкой
и пустыми виджетами, и человек решает, что программа сломана. Забыл
`overlay_app.py` — дашборд есть, а поверх игры пусто.

Порядок здесь не случаен: сначала инженер, потом ждём, пока он реально
ответит по сети, и только тогда оверлей. Иначе оверлей стартует раньше
сервера, первые секунды показывает прочерки и красную точку — то самое,
из-за чего люди и решают, что оно не работает.

Окно намеренно крошечное: это не второй пульт управления, у оверлея своя
панель. Здесь только «идёт/не идёт» и кнопка «Стоп».

Запуск:
    python launcher.py            открыть окно и ждать нажатия
    python launcher.py --start    сразу поднять оба — так зовёт ярлык
"""
import os
import pathlib
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ire import preflight                                        # noqa: E402
preflight.check(extra=preflight.OVERLAY + [("irsdk", "pyirsdk")])

from PySide6.QtCore import Qt, QTimer                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton,  # noqa: E402
                               QVBoxLayout, QWidget)

from ire import paths                                          # noqa: E402

# Из исходников соседи лежат рядом с launcher.py. В собранном виде лаунчер
# живёт в dist/RaceEngineerLauncher/, а инженер — в dist/RaceEngineer/,
# то есть на уровень ВЫШЕ. Плюс __file__ внутри .exe указывает не туда,
# где лежит сам .exe, — отсюда user_root().
ROOT = str(paths.user_root())
NEIGHBOURS = str(pathlib.Path(ROOT).parent) if paths.frozen() else ROOT
PORT = int(os.environ.get("IRE_PORT", "8000"))
WAIT_SECONDS = 25

QSS = """
QWidget { background:#0f1216; color:#e8eaed; font-family:'Segoe UI'; font-size:13px; }
QLabel#title { font-size:16px; font-weight:800; }
QLabel#state { color:#9099a6; }
QPushButton { background:#1d4ed8; border:none; border-radius:9px; padding:11px;
  font-weight:700; color:#eaf1ff; }
QPushButton:hover { background:#2563eb; }
QPushButton#stop { background:#181c22; border:1px solid #2a2f38; color:#e8eaed; }
QPushButton#stop:hover { background:#232a33; }
"""


def port_open(port=PORT, host="127.0.0.1", timeout=0.25):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def spawn(script, console):
    """Запуск дочернего процесса.

    В собранном .exe рядом лежат готовые приложения, а интерпретатора нет —
    поэтому сначала ищем .exe и только потом падаем на python.
    """
    exe = os.path.join(NEIGHBOURS, script["exe"])
    if paths.frozen() and os.path.exists(exe):
        cmd = [exe]
        cwd = os.path.dirname(exe)
    else:
        cmd = [sys.executable, os.path.join(ROOT, script["py"])]
        cwd = ROOT

    flags = 0
    if os.name == "nt":
        # Инженеру своё окно нужно: он печатает, что видит в симе, и это
        # единственное место, куда можно посмотреть, когда что-то не так.
        flags = subprocess.CREATE_NEW_CONSOLE if console else 0
    return subprocess.Popen(cmd, cwd=cwd, creationflags=flags)


ENGINEER = {"py": "run.py", "exe": os.path.join("RaceEngineer", "RaceEngineer.exe")}
OVERLAY = {"py": "overlay_app.py",
           "exe": os.path.join("RaceEngineerOverlay", "RaceEngineerOverlay.exe")}


class Launcher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Race Engineer")
        self.setStyleSheet(QSS)
        self.setFixedWidth(320)
        self.engineer = None
        self.overlay = None
        self._waited = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("🏁 Race Engineer", objectName="title"))
        self.state = QLabel("Ready. Start iRacing first if you can.",
                            objectName="state")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)

        self.start_btn = QPushButton("Start")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start)
        lay.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop", objectName="stop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setVisible(False)
        lay.addWidget(self.stop_btn)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    # ---------- запуск ----------
    def start(self):
        self.start_btn.setEnabled(False)
        if port_open():
            # Инженер уже поднят вручную или прошлым запуском — второй
            # экземпляр только отобрал бы порт и запутал.
            self.state.setText(f"Engineer already running on :{PORT}. "
                               f"Starting the overlay…")
            self._launch_overlay()
            return
        self.state.setText("Starting the engineer…")
        self.engineer = spawn(ENGINEER, console=True)
        self._waited = 0
        self._timer.start(400)

    def _poll(self):
        """Ждём, пока сервер ОТВЕТИТ, а не просто пока процесс запустился."""
        self._waited += 0.4
        if self.engineer is not None and self.engineer.poll() is not None:
            self._timer.stop()
            self.state.setText("The engineer stopped on start-up. "
                               "Look at its window for the reason.")
            self.start_btn.setEnabled(True)
            return
        if port_open():
            self._timer.stop()
            self._launch_overlay()
            return
        if self._waited >= WAIT_SECONDS:
            self._timer.stop()
            # Предупреждение обязано ПЕРЕЖИТЬ запуск оверлея: иначе оно
            # мелькнёт на полсекунды и его затрёт бодрое «Running», а человек
            # так и не узнает, что сервер не ответил.
            self._launch_overlay(
                note=f"The engineer did not answer on :{PORT} in "
                     f"{WAIT_SECONDS}s — the overlay will connect when it is up.")

    def _launch_overlay(self, note=""):
        self.overlay = spawn(OVERLAY, console=False)
        self.state.setText(note or (f"Running. Dashboard: http://localhost:{PORT}\n"
                                    f"The overlay panel is opening."))
        self.stop_btn.setVisible(True)
        self.start_btn.setText("Restart")
        self.start_btn.setEnabled(True)

    # ---------- остановка ----------
    def stop(self):
        for p in (self.overlay, self.engineer):
            if p is not None and p.poll() is None:
                p.terminate()
        # Даём закрыться самим: инженер дописывает круги на диск, и убивать
        # его на полуслове — верный способ получить битый файл.
        deadline = time.monotonic() + 5.0
        for p in (self.overlay, self.engineer):
            if p is None:
                continue
            while p.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if p.poll() is None:
                p.kill()
        self.overlay = self.engineer = None
        self.stop_btn.setVisible(False)
        self.start_btn.setText("Start")
        self.state.setText("Stopped.")

    def closeEvent(self, e):
        # Закрыли лаунчер — оставляем всё работать: гонка не должна
        # заканчиваться оттого, что кто-то прибрал окно с экрана.
        e.accept()


def main():
    app = QApplication(sys.argv)
    w = Launcher()
    w.show()
    if "--start" in sys.argv:
        # Ярлык на столе должен запускать гонку одним двойным щелчком, а не
        # открывать окно, где надо ещё что-то нажать. Кнопки остаются —
        # окно нужно и для «Стоп», и чтобы поднять всё заново.
        QTimer.singleShot(0, w.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
