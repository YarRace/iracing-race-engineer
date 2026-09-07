"""Пересобрать всё, что генерируется из кода, одной командой.

Каталог, снимки виджетов, снимки панели, снимки дашборда, герой, иконка.
Раньше это были шесть команд, и порядок имел значение: сайт читает
`data/catalog.json`, а каталог собирается из кода. Забыл одну — картинки
на сайте отстают от кода, и заметно это только глазами на странице.

Запуск:
    python tools/refresh_assets.py           всё
    python tools/refresh_assets.py --fast    без снимков (только каталог)
"""
import argparse
import os
import pathlib
import subprocess
import sys
import time

# Вывод у нас русский, а консоль на чужой машине бывает не в UTF-8 — на
# раннере GitHub это cp437, и первая же печатная строка роняла скрипт с
# UnicodeEncodeError. Из-за этого проверка падала НА КАЖДОМ коммите, ещё до
# тестов, и заметить это было нечем: локально консоль в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Порядок важен: каталог первым — снимки и сайт опираются на него.
STEPS = [
    ("каталог", "build_catalog.py", True),
    ("иконка", "make_icon.py", True),
    ("виджеты", "render_widgets.py", False),
    ("панель", "render_panel.py", False),
    ("дашборд", "render_dashboard.py", False),
    ("герой", "render_hero.py", False),
    # Опись релиза — до сайта: страница Get it решает по ней, дать
    # ссылку на скачивание или честно сказать, что скачивать нечего.
    ("релиз", "fetch_release.py", True),
    # Витрина собирается ПОСЛЕДНЕЙ: она берёт снимки и каталог, которые
    # делают шаги выше. Соберёшь раньше — на сайт уедет вчерашний набор.
    ("сайт", "build_site.py", True),
]


def _annotate(script, err):
    """Вынести ошибку в аннотацию GitHub — единственное, что видно снаружи.

    Журнал прогона отдаётся только владельцу репозитория: запрос к
    /actions/jobs/<id>/logs отвечает 403 даже для открытого репозитория.
    Из-за этого причину падения приходилось УГАДЫВАТЬ по имени шага — три
    догадки подряд, каждая ценой круга «поправил, запушил, подождал».

    А вот аннотации открыты всем: /check-runs/<id>/annotations отдаёт их без
    токена. Значит настоящий текст ошибки надо класть именно туда.

    Перевод строки внутри команды Actions кодируется как %0A: иначе
    аннотация обрежется на первой строке, а нужен как раз хвост с
    исключением.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    esc = err.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::error title={script}::{esc[:4000] or 'без вывода'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true",
                    help="без снимков — только то, что считается мгновенно")
    args = ap.parse_args()

    failed, skipped = [], []
    for title, script, fast_ok in STEPS:
        if args.fast and not fast_ok:
            continue
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(ROOT / "tools" / script)],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        dt = time.monotonic() - t0
        # Код 2 — «нечем сделать на этой машине» (нет браузера для
        # снимков). Это предупреждение, а не поломка: ронять из-за
        # него сборку релиза значит требовать браузер там, где он
        # не нужен.
        mark = {0: "ok  ", 2: "ПРОП"}.get(r.returncode, "СБОЙ")
        print(f"  {mark} {title:<9} {dt:5.1f}с   {script}")
        if r.returncode == 2:
            skipped.append(script)
        elif r.returncode != 0:
            failed.append((script, ((r.stdout or "") + (r.stderr or "")).strip()))

    for script, err in failed:
        print(f"\n  {script}:\n{err}")
        _annotate(script, err)
    for script in skipped:
        print(f"  пропущено: {script} — нечем выполнить на этой машине")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
