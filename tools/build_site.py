"""Статическая витрина в docs/ — та же страница, но без запущенной программы.

ЗАЧЕМ. Витрина живёт по адресу localhost:8000/about, то есть показать её можно
только тому, кто сначала поставит и запустит программу. Для проекта, который
метит в продажу, это ровно наоборот: сначала человек смотрит, потом ставит.

GitHub Pages умеет отдавать папку `docs/` как сайт, а снимки виджетов, панели и
дашборда там уже лежат — их собирают tools/render_*.py. Не хватало только
самих HTML-страниц и относительных путей вместо серверных.

ЧТО ЗДЕСЬ ВАЖНО. Страницы берутся из того же `dashboard/site.py`, что и живые.
Второй копии вёрстки нет и не будет: две копии разъезжаются, и через месяц сайт
показывает не то, что программа. Отличаются они ровно на переписанные адреса —
их список ниже, и он проверяется тестом.

Запуск:
    python tools/build_site.py                  собрать в docs/
    python tools/build_site.py --out путь       в другое место
    python tools/build_site.py --check          только проверить, не писать
"""
import argparse
import pathlib
import re
import shutil
import sys

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

# Серверный адрес → путь в статической папке. Порядок важен: сначала длинные,
# иначе «/w/» съест кусок «/widgets/».
REWRITES = [
    ('href="/tokens.css"', 'href="tokens.css"'),
    ('src="/w/', 'src="widgets/'),
    ('src="/panel/', 'src="panel/'),
    ('src="/dash/', 'src="dashboard/'),
    ('src="/hero.png"', 'src="hero.png"'),
    # RSS на статике нет: фид собирает живой сервер. Ссылка на файл,
    # которого не будет, — это 404 в одно нажатие, поэтому кнопка
    # ведёт на сам журнал.
    ('<a href="/news/rss.xml">RSS</a>', '<a href="changelog.html">every entry</a>'),
]

# Страница → имя файла. `about` становится index.html: с него начинают.
PAGES = [("about", "index.html"), ("catalog", "widgets.html"),
         ("download", "get.html"), ("news", "changelog.html")]

# Навигация. «/» на статическом сайте вела бы в никуда — дашборд это живая
# программа, а не страница. Вместо неё ссылка на исходники.
NAV_MAP = {
    'href="/"': 'href="https://github.com/YarRace/iracing-race-engineer"',
    'href="/about"': 'href="index.html"',
    'href="/catalog"': 'href="widgets.html"',
    'href="/download"': 'href="get.html"',
    'href="/news"': 'href="changelog.html"',
}

REPO = "https://github.com/YarRace/iracing-race-engineer"


def to_static(html):
    """Переписать серверные адреса на относительные."""
    for src, dst in REWRITES:
        html = html.replace(src, dst)
    for src, dst in NAV_MAP.items():
        html = html.replace(src, dst)
    # Якоря вида href="/news#slug" остаются после NAV_MAP, ловим отдельно.
    html = html.replace('href="/news#', 'href="changelog.html#')
    # Подпись «Dashboard» в шапке на сайте означала бы страницу, которой нет.
    html = html.replace(">Dashboard</a>", ">Source</a>")
    return html


def leftover_absolute(html):
    """Оставшиеся серверные адреса. Пустой список — значит всё переписано.

    Проверка нужна именно здесь: пропущенный `/w/fuel.png` на GitHub Pages
    даёт битую картинку, и заметить это можно только открыв сайт глазами.
    Внешние ссылки (http, //) и якоря (#) не трогаем.
    """
    bad = set()
    for m in re.finditer(r'(?:href|src)="(/[^"]*)"', html):
        bad.add(m.group(1))
    return sorted(bad)


def build(out_dir, check=False):
    from ire.dashboard import site

    cat = site.load_catalog()
    shots = site.load_shots()
    panels = site.load_panel_shots()
    dash = site.load_dashboard_shots()

    made = {
        "about": lambda: site.page_about(cat, shots, panels, dash),
        "catalog": lambda: site.page_catalog(cat, shots),
        "download": lambda: site.page_download(cat, panels),
        "news": lambda: site.page_news(site.read_news()),
    }

    out = pathlib.Path(out_dir)
    problems, written = [], []
    for name, fname in PAGES:
        maker = made.get(name)
        if maker is None:
            continue
        try:
            html = to_static(maker())
        except Exception as exc:                             # noqa: BLE001
            problems.append(f"{fname}: {type(exc).__name__}: {exc}")
            continue
        left = leftover_absolute(html)
        if left:
            problems.append(f"{fname}: не переписаны адреса — {', '.join(left)}")
        if not check:
            (out / fname).write_text(html, encoding="utf-8")
        written.append((fname, len(html)))

    # tokens.css лежит в статике дашборда — на сайте он нужен рядом со
    # страницами, иначе всё поедет без единой переменной цвета.
    css = ROOT / "src" / "ire" / "dashboard" / "static" / "tokens.css"
    if css.exists() and not check:
        shutil.copy(css, out / "tokens.css")
    elif not css.exists():
        problems.append("нет tokens.css — страницы выйдут без стилей")

    if not check:
        # .nojekyll: без него GitHub Pages прогоняет папку через Jekyll и
        # выбрасывает всё, что начинается с подчёркивания. Наши файлы так не
        # называются, но правило это молчаливое и лучше его отключить.
        (out / ".nojekyll").write_text("", encoding="utf-8")

    return written, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs"))
    ap.add_argument("--check", action="store_true",
                    help="только проверить, ничего не записывать")
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    written, problems = build(out, check=a.check)

    for fname, size in written:
        print(f"  ok  {fname:<16}{size:>8} символов")
    if problems:
        print("\n  ПРОБЛЕМЫ:")
        for p in problems:
            print("   ·", p)
        return 1
    if a.check:
        print("\n  Проверка пройдена, ничего не записано.")
        return 0

    print(f"\n  Папка: {out}")
    print(f"  Открыть локально: {out / 'index.html'}")
    print("\n  Чтобы страница появилась в интернете, включи GitHub Pages один раз:")
    print(f"     {REPO}/settings/pages")
    print("     Source: Deploy from a branch · Branch: main · Folder: /docs")
    print(f"  После этого адрес будет: https://yarrace.github.io/"
          f"{REPO.rsplit('/', 1)[-1]}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
