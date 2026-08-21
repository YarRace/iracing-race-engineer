"""Сайт проекта: витрина, каталог виджетов и чейнджлог.

Пока это страницы для себя — посмотреть со стороны, что вообще получилось,
и заставить себя описать продукт словами. Когда дойдёт до продажи, текст
отсюда станет основой для покупателей, а язык поменяется на английский.

Без шаблонизатора: три страницы не стоят новой зависимости, а Jinja2 в
проекте не используется. Стили берутся из того же tokens.css, что и
дашборд, — сайт и приложение выглядят одинаково по определению.

Цифры на страницах не пишутся руками. Они приходят из data/catalog.json,
который собирает tools/build_catalog.py прямо из кода: docstring оверлея
годами обещал 31 виджет, когда их было 42, и повторять эту ошибку смысла нет.
"""
import datetime
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
NEWS_DIR = ROOT / "docs" / "news"
CATALOG = ROOT / "data" / "catalog.json"

NAV = (("/", "Дашборд"), ("/about", "О проекте"),
       ("/catalog", "Виджеты"), ("/news", "Изменения"))


def load_catalog():
    """Каталог из файла. Если его не собирали — пустой, страница не падает."""
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return {"widgets": [], "cards": [], "endpoints": [],
                "counts": {"widgets": 0, "cards": 0, "tabs": 0, "endpoints": 0,
                           "by_group": {}, "by_tab": {}}}


def plural(n, one, few, many):
    """Русское склонение после числа: 1 виджет, 2 виджета, 5 виджетов.

    Без этого страница пишет «42 виджетов» и «6 вкладки» — мелочь, но она
    сразу выдаёт, что текст собран машиной и никто его не читал.
    """
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def e(s):
    return html.escape(str(s if s is not None else ""))


def shell(title, body, active=""):
    nav = "".join(
        f'<a href="{href}" class="{"on" if href == active else ""}">{e(name)}</a>'
        for href, name in NAV)
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} — Race Engineer</title>
<link rel="stylesheet" href="/tokens.css">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--txt);line-height:1.6;
    font:15px/1.6 -apple-system,"Segoe UI",Roboto,Arial,sans-serif}}
  a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
  .wrap{{max-width:1080px;margin:0 auto;padding:0 24px}}
  header{{border-bottom:1px solid var(--line);position:sticky;top:0;
    background:var(--bg);z-index:5}}
  header .wrap{{display:flex;align-items:center;gap:26px;height:60px}}
  .logo{{font-weight:800;letter-spacing:.5px;color:var(--txt)}}
  .logo b{{color:var(--accent)}}
  nav{{display:flex;gap:20px;margin-left:auto}}
  nav a{{color:var(--muted);font-size:14px}}
  nav a.on{{color:var(--txt);font-weight:600}}
  h1{{font-size:40px;line-height:1.15;letter-spacing:-.5px;margin-bottom:14px}}
  h1 span{{color:var(--accent)}}
  h2{{font-size:13px;text-transform:uppercase;letter-spacing:1.5px;
    color:var(--muted);margin:44px 0 16px;font-weight:600}}
  .lead{{color:var(--muted);font-size:17px;max-width:640px}}
  section{{padding:40px 0}}
  .hero{{padding:64px 0 40px}}
  .nums{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
  .num{{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-card);
    padding:18px 20px}}
  .num .v{{font-size:34px;font-weight:800;font-variant-numeric:tabular-nums;
    letter-spacing:-1px}}
  .num .k{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}}
  .why{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
  .why div{{background:var(--panel);border:1px solid var(--line);
    border-radius:var(--r-card);padding:20px}}
  .why h3{{font-size:15px;margin-bottom:8px}}
  .why p{{color:var(--muted);font-size:14px}}
  table{{width:100%;border-collapse:collapse;font-size:14px}}
  th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:1px;
    color:var(--muted);padding:10px 12px;border-bottom:1px solid var(--line);font-weight:600}}
  td{{padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
  tr:hover td{{background:var(--panel)}}
  .k{{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;color:var(--muted)}}
  .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;
    border:1px solid var(--line);color:var(--muted)}}
  .tag.solo{{color:var(--good);border-color:color-mix(in srgb,var(--good) 40%,transparent)}}
  .tag.endur{{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 40%,transparent)}}
  .tag.setup{{color:var(--best);border-color:color-mix(in srgb,var(--best) 40%,transparent)}}
  .post{{border-bottom:1px solid var(--line);padding:22px 0}}
  .post .d{{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}}
  .post h3{{font-size:19px;margin:4px 0 8px}}
  .post ul{{margin-left:20px;color:var(--muted)}}
  .empty{{color:var(--muted);padding:30px 0}}
  footer{{border-top:1px solid var(--line);margin-top:60px;padding:24px 0;
    color:var(--muted);font-size:13px}}
  @media(max-width:760px){{.nums,.why{{grid-template-columns:1fr 1fr}}h1{{font-size:30px}}}}
</style></head><body>
<header><div class="wrap">
  <span class="logo">RACE <b>ENGINEER</b></span>
  <nav>{nav}</nav>
</div></header>
<div class="wrap">{body}</div>
<footer><div class="wrap">Личный проект для iRacing. Страницы собраны из кода —
цифры не переписываются руками.</div></footer>
</body></html>"""


# ── страницы ────────────────────────────────────────────────────────────────

WHY = [
    ("Всё в одном окне",
     "Телеметрия, стратегия, история кругов и разбор — вместо четырёх приложений "
     "с четырьмя подписками."),
    ("Свой оверлей поверх игры",
     "Виджеты настраиваются по одному: цвет, размер, шрифт каждой цифры. "
     "Кнопки руля назначаются на любое действие."),
    ("Данные не пропадают",
     "Каждый круг с телеметрией ложится на диск. История живёт между сессиями, "
     "прогресс виден по датам, а не по одной поездке."),
    ("Без сглаживания",
     "Показываем сырые значения на высокой частоте. Сглаживание прячет ровно то, "
     "ради чего смотришь цифры — разброс и выбросы."),
    ("Разбор словами",
     "После стинта модель объясняет, что происходило с машиной, и предлагает "
     "правки сетапа с обоснованием."),
    ("Работает без интернета",
     "Всё крутится локально. Ключи к чужим сервисам не нужны, данные никуда "
     "не уходят."),
]


def page_about(cat):
    k = cat["counts"]
    labels = (
        (k["widgets"], ("виджет оверлея", "виджета оверлея", "виджетов оверлея")),
        (k["cards"], ("карточка дашборда", "карточки дашборда", "карточек дашборда")),
        (k["tabs"], ("вкладка", "вкладки", "вкладок")),
        (k["endpoints"], ("эндпоинт API", "эндпоинта API", "эндпоинтов API")),
    )
    nums = "".join(
        f'<div class="num"><div class="v">{v}</div>'
        f'<div class="k">{e(plural(v, *forms))}</div></div>'
        for v, forms in labels)
    why = "".join(f"<div><h3>{e(t)}</h3><p>{e(d)}</p></div>" for t, d in WHY)
    groups = " · ".join(f"{e(g)} — {n}" for g, n in (k["by_group"] or {}).items())
    return shell("О проекте", f"""
<section class="hero">
  <h1>Гоночный инженер<br>для <span>iRacing</span></h1>
  <p class="lead">Дашборд на втором экране, свой оверлей поверх игры и разбор
  заездов. Собственный проект, не подписка: данные лежат у меня, работает локально.</p>
</section>
<section>
  <h2>Что внутри</h2>
  <div class="nums">{nums}</div>
  <p class="lead" style="margin-top:14px;font-size:14px">Виджеты по группам: {groups}.
  Цифры собраны из кода командой <span class="k">python tools/build_catalog.py</span>.</p>
</section>
<section>
  <h2>Почему так</h2>
  <div class="why">{why}</div>
</section>
<section>
  <h2>Дальше</h2>
  <p class="lead">Ближайшее: разбор круга по поворотам с ценой ошибки в секундах,
  сравнение кругов по дистанции, командная стратегия на эндуранс.
  Полный план — в <span class="k">docs/roadmap-overlay-2026-08.md</span>.</p>
</section>""", active="/about")


def page_catalog(cat):
    if not cat["widgets"]:
        body = ('<section><h1>Виджеты</h1><div class="empty">Каталог не собран. '
                'Запусти <span class="k">python tools/build_catalog.py</span>.</div></section>')
        return shell("Виджеты", body, active="/catalog")

    rows = "".join(
        f"<tr><td>{e(w['title'])}</td>"
        f'<td><span class="tag {e(w["group"])}">{e(w["group_title"])}</span></td>'
        f'<td class="k">{e(w["key"])}</td>'
        f'<td class="k">{w["width"]}×{w["height"]}</td>'
        f'<td class="k">{e(", ".join(w["endpoints"]) or "—")}</td></tr>'
        for w in cat["widgets"])
    cards = "".join(
        f"<tr><td>{e(c['title'])}</td><td>{e(c['tab_title'])}</td>"
        f'<td class="k">{e(c["key"])}</td></tr>' for c in cat["cards"])
    k = cat["counts"]
    return shell("Виджеты", f"""
<section class="hero" style="padding:44px 0 20px">
  <h1>Виджеты и карточки</h1>
  <p class="lead">{k['widgets']} {plural(k['widgets'], 'виджет', 'виджета', 'виджетов')}
  поверх игры и {k['cards']} {plural(k['cards'], 'карточка', 'карточки', 'карточек')}
  на дашборде. Список читается из кода, поэтому не устаревает.</p>
</section>
<section>
  <h2>Оверлей — {k['widgets']}</h2>
  <table><tr><th>Название</th><th>Группа</th><th>Ключ</th><th>Размер</th>
  <th>Данные</th></tr>{rows}</table>
</section>
<section>
  <h2>Дашборд — {k['cards']}</h2>
  <table><tr><th>Карточка</th><th>Вкладка</th><th>Ключ</th></tr>{cards}</table>
</section>""", active="/catalog")


# ── чейнджлог ───────────────────────────────────────────────────────────────

def read_news(d=None):
    """Записи из docs/news/*.md, новые сверху.

    Имя файла — ГГГГ-ММ-ДД-что-то.md, первая строка «# Заголовок», дальше текст.
    Такой формат правится в любом редакторе и читается глазами без рендера.
    """
    d = pathlib.Path(d or NEWS_DIR)
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.md"), reverse=True):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
        text = f.read_text(encoding="utf-8").strip()
        lines = text.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else f.stem
        out.append({"date": m.group(1) if m else "", "title": title,
                    "body": "\n".join(lines[1:]).strip(), "slug": f.stem})
    return out


def _md_lite(text):
    """Минимальный markdown: абзацы, списки, `код`, **жирный**.

    Полноценный markdown здесь не нужен — записи короткие, а лишняя
    зависимость ради трёх страниц не окупается.
    """
    blocks = []
    for raw in re.split(r"\n\s*\n", text):
        block = raw.strip()
        if not block:
            continue
        if all(l.lstrip().startswith(("- ", "* ")) for l in block.splitlines()):
            items = "".join(f"<li>{_inline(l.lstrip()[2:])}</li>" for l in block.splitlines())
            blocks.append(f"<ul>{items}</ul>")
        else:
            blocks.append(f"<p>{_inline(block)}</p>")
    return "".join(blocks)


def _inline(s):
    s = e(s)
    s = re.sub(r"`([^`]+)`", r'<span class="k">\1</span>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def page_news(entries):
    if not entries:
        body = ('<section><h1>Изменения</h1><div class="empty">Записей пока нет. '
                'Добавь файл в <span class="k">docs/news/</span>.</div></section>')
        return shell("Изменения", body, active="/news")
    posts = "".join(
        f'<div class="post"><div class="d">{e(p["date"])}</div>'
        f'<h3>{e(p["title"])}</h3>{_md_lite(p["body"])}</div>' for p in entries)
    return shell("Изменения", f"""
<section class="hero" style="padding:44px 0 10px">
  <h1>Что изменилось</h1>
  <p class="lead">Свой чейнджлог. <a href="/news/rss.xml">RSS</a></p>
</section>
<section>{posts}</section>""", active="/news")


def news_rss(entries, base="http://localhost:8000"):
    items = ""
    for p in entries:
        try:
            dt = datetime.datetime.strptime(p["date"], "%Y-%m-%d")
            pub = dt.strftime("%a, %d %b %Y 00:00:00 +0000")
        except ValueError:
            pub = ""
        items += (f"<item><title>{e(p['title'])}</title>"
                  f"<link>{base}/news#{e(p['slug'])}</link>"
                  f"<guid isPermaLink=\"false\">{e(p['slug'])}</guid>"
                  f"<pubDate>{pub}</pubDate>"
                  f"<description>{e(p['body'][:600])}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel>'
            "<title>Race Engineer — изменения</title>"
            f"<link>{base}/news</link>"
            "<description>Чейнджлог личного проекта гоночного инженера</description>"
            f"{items}</channel></rss>")
