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
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Порядок важен: каталог первым — снимки и сайт опираются на него.
STEPS = [
    ("каталог", "build_catalog.py", True),
    ("иконка", "make_icon.py", True),
    ("виджеты", "render_widgets.py", False),
    ("панель", "render_panel.py", False),
    ("дашборд", "render_dashboard.py", False),
    ("герой", "render_hero.py", False),
    # Витрина собирается ПОСЛЕДНЕЙ: она берёт снимки и каталог, которые
    # делают шаги выше. Соберёшь раньше — на сайт уедет вчерашний набор.
    ("сайт", "build_site.py", True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true",
                    help="без снимков — только то, что считается мгновенно")
    args = ap.parse_args()

    failed = []
    for title, script, fast_ok in STEPS:
        if args.fast and not fast_ok:
            continue
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(ROOT / "tools" / script)],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        dt = time.monotonic() - t0
        mark = "ok " if r.returncode == 0 else "СБОЙ"
        print(f"  {mark} {title:<9} {dt:5.1f}с   {script}")
        if r.returncode != 0:
            failed.append((script, (r.stderr or r.stdout or "")[-400:]))

    for script, err in failed:
        print(f"\n  {script}:\n{err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
