"""Снимки ДАШБОРДА для сайта.

Оверлей на сайте показан, панель настроек показана — а второго экрана,
ради которого половина проекта и написана, человек так и не видел.

Дашборд — живая HTML-страница: чтобы её снять, нужен запущенный сервер
с данными. Поднимаем его здесь же, на свободном порту, кормим тем же
демо-потоком, что и предпросмотр в панели, и снимаем headless-браузером.

База истории уводится в ВРЕМЕННУЮ через IRE_DB_PATH. Настоящая
data/history.db — это шестьсот с лишним кругов пользователя, и трогать
её ради картинки нельзя ни на чтение, ни тем более на запись.

Нужен установленный Chrome. Без него скрипт честно скажет, что снять
нечем, и выйдет с ошибкой — молча положить старую картинку хуже.

Запуск:
    python tools/render_dashboard.py            → docs/dashboard/
"""
import argparse
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

# Вывод у нас русский, а консоль на чужой машине бывает не в UTF-8 — на
# раннере GitHub это cp437, и первая же печатная строка роняла скрипт с
# UnicodeEncodeError. Из-за этого проверка падала НА КАЖДОМ коммите, ещё до
# тестов, и заметить это было нечем: локально консоль в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

# (файл, вкладка, высота окна, подпись)
SHOTS = [
    ("dashboard-solo.png", "solo", 2000,
     "The solo tab: gauges, delta, fuel, tyres, the track map and the field — "
     "everything from one lap in one place."),
    ("dashboard-endur.png", "endur", 1500,
     "Endurance: who is in the car, how long is left, and what the team's "
     "incident count looks like while someone else drives."),
    ("dashboard-setup.png", "setup", 1500,
     "Setup: what the car did on entry, mid-corner and exit — and the change "
     "the numbers ask for."),
]


def find_chrome():
    for p in CHROME:
        if os.path.exists(p):
            return p
    return shutil.which("chrome") or shutil.which("msedge")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(state):
    """Кладём демо-поток в STATE сервера — те же данные, что в предпросмотре."""
    from overlay.demo import DemoFeed
    feed = DemoFeed()
    for key in list(state):
        data = feed.get(key)
        if data:
            state[key] = data
    return feed


def pump(state, feed, stop):
    """Кадры идут дальше, пока браузер грузит страницу: иначе на снимке
    застывшая одна и та же секунда, и графики выходят плоскими."""
    while not stop.is_set():
        for key in list(state):
            data = feed.get(key)
            if data:
                state[key] = data
        time.sleep(0.1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "dashboard"))
    ap.add_argument("--width", type=int, default=1600)
    args = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        print("  Chrome не найден — снимать нечем.")
        return 1

    tmpdir = tempfile.mkdtemp(prefix="ire-shot-")
    os.environ["IRE_DB_PATH"] = os.path.join(tmpdir, "shot.db")

    import uvicorn

    from ire.dashboard.server import STATE, app

    feed = seed(STATE)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    stop = threading.Event()
    threading.Thread(target=pump, args=(STATE, feed, stop), daemon=True).start()

    for _ in range(60):                                  # ждём, пока поднимется
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                break
        except OSError:
            time.sleep(0.1)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index, failed = [], []
    try:
        for fname, tab, height, caption in SHOTS:
            path = out / fname
            # ?tab= читает сама страница: без него всегда снимался бы Solo
            url = f"http://127.0.0.1:{port}/#tab={tab}"
            r = subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                 f"--window-size={args.width},{height}",
                 "--virtual-time-budget=4000",
                 f"--screenshot={path}", url],
                capture_output=True, timeout=120)
            if not path.exists():
                failed.append((fname, (r.stderr or b"").decode(errors="replace")[-200:]))
                continue
            index.append({"file": fname, "tab": tab, "caption": caption})
    finally:
        stop.set()
        server.should_exit = True
        time.sleep(0.3)
        shutil.rmtree(tmpdir, ignore_errors=True)

    (out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in out.glob("*.png"))
    print(f"  снято: {len(index)} из {len(SHOTS)}")
    for name, err in failed:
        print(f"  ПРОВАЛ {name}: {err}")
    print(f"  каталог: {out}")
    print(f"  вес: {total // 1024} КБ, опись в index.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
