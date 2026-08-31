"""Одна кнопка «Старт» вместо двух запусков.

Порядок здесь не косметика. Оверлей, поднятый раньше сервера, показывает
красную точку и пустые виджеты — ровно то, из-за чего человек решает, что
программа сломана. Поэтому лаунчер ждёт, пока инженер ОТВЕТИТ по сети,
а не пока просто запустится процесс: процесс живёт и когда падает с
ошибкой порта.
"""
import os
import pathlib
import socket
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication                        # noqa: E402

import launcher                                                   # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeProc:
    """Подделка процесса: живой, пока не сказали обратное."""

    def __init__(self):
        self.terminated = self.killed = False
        self._code = None

    def poll(self):
        return self._code

    def terminate(self):
        self.terminated = True
        self._code = 0

    def kill(self):
        self.killed = True
        self._code = -9


@pytest.fixture()
def win(app, monkeypatch):
    spawned = []

    def fake_spawn(script, console):
        spawned.append((script["py"], console))
        return FakeProc()

    monkeypatch.setattr(launcher, "spawn", fake_spawn)
    w = launcher.Launcher()
    w._spawned = spawned
    yield w
    w.close()


def test_port_check_reports_a_closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert launcher.port_open(free) is False


def test_port_check_sees_a_listening_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        assert launcher.port_open(srv.getsockname()[1]) is True
    finally:
        srv.close()


def test_engineer_starts_first_and_the_overlay_waits(win, monkeypatch):
    """Оверлей раньше сервера — это красная точка и пустые виджеты."""
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: False)
    win.start()
    assert win._spawned == [("run.py", True)], "оверлей не должен стартовать сразу"
    assert win._timer.isActive(), "не ждём ответа сервера"


def test_the_overlay_starts_once_the_server_answers(win, monkeypatch):
    state = {"up": False}
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: state["up"])
    win.start()
    win._poll()
    assert [s for s, _ in win._spawned] == ["run.py"]
    state["up"] = True
    win._poll()
    assert [s for s, _ in win._spawned] == ["run.py", "overlay_app.py"]
    assert not win._timer.isActive()


def test_a_second_engineer_is_not_started_over_a_running_one(win, monkeypatch):
    """Инженер уже поднят вручную. Второй экземпляр только отобрал бы порт."""
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: True)
    win.start()
    assert [s for s, _ in win._spawned] == ["overlay_app.py"]


def test_a_crashed_engineer_is_reported_not_hidden(win, monkeypatch):
    """Тихо запустить оверлей поверх упавшего инженера — оставить человека
    гадать, почему всё пустое."""
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: False)
    win.start()
    win.engineer._code = 1                       # процесс завершился с ошибкой
    win._poll()
    assert not win._timer.isActive()
    assert "stopped on start-up" in win.state.text()
    assert [s for s, _ in win._spawned] == ["run.py"], "оверлей не должен подняться"


def test_it_gives_up_waiting_but_still_starts_the_overlay(win, monkeypatch):
    """Сервер может не ответить, а оверлей подключится позже сам —
    вечно ждать и не показать ничего хуже."""
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: False)
    win.start()
    win._waited = launcher.WAIT_SECONDS
    win._poll()
    assert [s for s, _ in win._spawned] == ["run.py", "overlay_app.py"]
    assert "did not answer" in win.state.text()


def test_stop_asks_before_it_kills(win, monkeypatch):
    """Инженер дописывает круги на диск: убивать его на полуслове — верный
    способ получить битый файл."""
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: False)
    win.start()
    win._waited = launcher.WAIT_SECONDS
    win._poll()
    eng, ov = win.engineer, win.overlay
    win.stop()
    assert eng.terminated and ov.terminated
    assert not eng.killed and not ov.killed
    assert win.engineer is None and win.overlay is None


def test_closing_the_launcher_leaves_the_race_running(win, monkeypatch):
    """Гонка не должна заканчиваться оттого, что кто-то прибрал окно."""
    monkeypatch.setattr(launcher, "port_open", lambda *a, **k: True)
    win.start()
    ov = win.overlay
    win.close()
    assert ov.poll() is None and not ov.terminated


def test_frozen_launcher_looks_for_its_neighbours_one_level_up(monkeypatch, tmp_path):
    """В сборке лаунчер лежит в dist/RaceEngineerLauncher/, а инженер —
    в dist/RaceEngineer/. Искать соседа В СВОЕЙ папке значит не найти его
    никогда и молча свалиться на python, которого рядом с .exe нет.
    """
    app_dir = tmp_path / "dist" / "RaceEngineerLauncher"
    eng_dir = tmp_path / "dist" / "RaceEngineer"
    app_dir.mkdir(parents=True)
    eng_dir.mkdir(parents=True)
    exe = eng_dir / "RaceEngineer.exe"
    exe.write_bytes(b"")

    calls = {}
    monkeypatch.setattr(launcher.paths, "frozen", lambda: True)
    monkeypatch.setattr(launcher, "ROOT", str(app_dir))
    monkeypatch.setattr(launcher, "NEIGHBOURS", str(app_dir.parent))
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda cmd, cwd=None, **kw: calls.update(cmd=cmd, cwd=cwd))

    launcher.spawn(launcher.ENGINEER, console=True)
    assert calls["cmd"] == [str(exe)], "запустился не собранный .exe"
    assert calls["cwd"] == str(eng_dir), "рабочая папка не рядом с .exe"


def test_from_sources_it_runs_the_scripts_next_to_itself(monkeypatch):
    calls = {}
    monkeypatch.setattr(launcher.paths, "frozen", lambda: False)
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda cmd, cwd=None, **kw: calls.update(cmd=cmd, cwd=cwd))
    launcher.spawn(launcher.OVERLAY, console=False)
    assert calls["cmd"][0] == sys.executable
    assert calls["cmd"][1].endswith("overlay_app.py")
