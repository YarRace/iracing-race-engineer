"""Каталог виджетов и карточек — собирается ИЗ КОДА, а не пишется руками.

Написанный руками список устаревает в тот же день. Docstring `overlay_app.py`
обещает 31 виджет, а в реестре `WIDGETS` их 42: список забыли обновить, и он
врёт уже неизвестно сколько времени.

Здесь наоборот: скрипт читает реестр виджетов оверлея и разметку дашборда и
кладёт результат в data/catalog.json. Сайт показывает то, что реально есть в
проекте на момент сборки.

Запуск:
    python tools/build_catalog.py
"""
import json
import os
import pathlib
import re
import sys

# Вывод у нас русский, а консоль на чужой машине бывает не в UTF-8 — на
# раннере GitHub это cp437, и первая же печатная строка роняла скрипт с
# UnicodeEncodeError. Из-за этого проверка падала НА КАЖДОМ коммите, ещё до
# тестов, и заметить это было нечем: локально консоль в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Каталог считает виджеты, а для этого импортирует overlay.widgets — то есть
# тянет Qt. На машине без экрана (CI) это падает, и падало: шаг «Rebuild the
# catalogue» был единственным, кому забыли передать QT_QPA_PLATFORM, и весь
# прогон валился ещё до тестов. Ставим сами: скрипт не должен зависеть от
# того, вспомнил ли о нём тот, кто его зовёт.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Подписи уезжают на сайт, а он английский — см. site.py.
GROUP_TITLES = {"solo": "Solo", "endur": "Endurance", "setup": "Setup"}
TAB_TITLES = {
    "solo": "Solo", "endur": "Endurance", "setup": "Setup",
    "records": "Records", "strategy": "Strategy", "analysis": "Race analysis",
}


def widgets():
    """Виджеты оверлея из реестра WIDGETS."""
    from overlay.widgets import WIDGETS

    out = []
    for cls in WIDGETS:
        size = getattr(cls, "DEFAULT", None) or (0, 0)
        out.append({
            "key": getattr(cls, "KEY", cls.__name__),
            "title": getattr(cls, "TITLE", cls.__name__),
            "group": getattr(cls, "GROUP", "solo"),
            "group_title": GROUP_TITLES.get(getattr(cls, "GROUP", "solo"), "Solo"),
            "width": size[0], "height": size[1],
            # источники данных: по ним видно, что виджет вообще показывает
            "endpoints": list(getattr(cls, "ENDPOINTS", ()) or ()),
            # подпись для сайта берём из BLURB, а не из докстринга:
            # докстринги русские и такими и останутся, сайт — английский
            "desc": getattr(cls, "BLURB", ""),
        })
    out.sort(key=lambda w: (list(GROUP_TITLES).index(w["group"]), w["title"].lower()))
    return out


def cards(html_path):
    """Карточки дашборда из разметки: id, заголовок и вкладка, на которой стоят."""
    html = pathlib.Path(html_path).read_text(encoding="utf-8")
    # разметка вкладок: <div id="tab-XXX" class="mpane"> … карточки … </div>
    panes = re.findall(r'<div id="tab-([a-z]+)" class="mpane"', html)
    starts = [(m.group(1), m.start()) for m in re.finditer(r'<div id="tab-([a-z]+)" class="mpane"', html)]

    def tab_of(pos):
        cur = None
        for name, at in starts:
            if at <= pos:
                cur = name
            else:
                break
        return cur

    out = []
    for m in re.finditer(r'data-card="([^"]+)"\s+data-title="([^"]+)"', html):
        tab = tab_of(m.start())
        out.append({"key": m.group(1), "title": m.group(2),
                    "tab": tab, "tab_title": TAB_TITLES.get(tab, tab or "—")})
    return out, panes


def endpoints(server_path):
    """Эндпоинты API — по декораторам в server.py."""
    src = pathlib.Path(server_path).read_text(encoding="utf-8")
    return sorted(set(re.findall(r'@app\.get\("(/api/[^"]+)"\)', src)))


def build():
    w = widgets()
    c, panes = cards(ROOT / "src/ire/dashboard/static/index.html")
    eps = endpoints(ROOT / "src/ire/dashboard/server.py")

    by_group = {}
    for x in w:
        by_group[x["group_title"]] = by_group.get(x["group_title"], 0) + 1
    by_tab = {}
    for x in c:
        by_tab[x["tab_title"]] = by_tab.get(x["tab_title"], 0) + 1

    return {
        "widgets": w, "cards": c, "endpoints": eps,
        "counts": {
            "widgets": len(w), "cards": len(c),
            "tabs": len(panes), "endpoints": len(eps),
            "by_group": by_group, "by_tab": by_tab,
        },
    }


def main():
    data = build()
    out = ROOT / "data" / "catalog.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    k = data["counts"]
    print(f"Каталог собран: {out}")
    print(f"  виджетов оверлея: {k['widgets']}  ({', '.join(f'{g} — {n}' for g, n in k['by_group'].items())})")
    print(f"  карточек дашборда: {k['cards']} на {k['tabs']} вкладках")
    print(f"  эндпоинтов API: {k['endpoints']}")


if __name__ == "__main__":
    main()
