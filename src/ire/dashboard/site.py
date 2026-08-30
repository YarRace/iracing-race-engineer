"""Сайт проекта: витрина, каталог виджетов и чейнджлог.

Текст сайта — на английском: конкуренты англоязычные, и проект метит
в продажу. Русскими остаются только комментарии и докстринги — их видит
один автор.

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

from ire import paths

# Ресурсы сборки: и чейнджлог, и каталог одинаковы у всех, кто поставил
# программу, — им место рядом с кодом, а не в данных пользователя.
ROOT = paths.res_root()
NEWS_DIR = ROOT / "docs" / "news"
CATALOG = ROOT / "data" / "catalog.json"

NAV = (("/", "Dashboard"), ("/about", "About"), ("/catalog", "Widgets"),
       ("/download", "Get it"), ("/news", "Changelog"))


def load_catalog():
    """Каталог из файла. Если его не собирали — пустой, страница не падает."""
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return {"widgets": [], "cards": [], "endpoints": [],
                "counts": {"widgets": 0, "cards": 0, "tabs": 0, "endpoints": 0,
                           "by_group": {}, "by_tab": {}}}


def plural(n, one, many):
    """Форма существительного после числа: 1 widget, 42 widgets.

    Английскому хватает двух форм — но выбирать всё равно надо: страница
    с «1 widgets» сразу выдаёт, что текст собрала машина и никто его
    не прочитал.
    """
    return one if abs(int(n)) == 1 else many


def e(s):
    return html.escape(str(s if s is not None else ""))


def shell(title, body, active=""):
    nav = "".join(
        f'<a href="{href}" class="{"on" if href == active else ""}">{e(name)}</a>'
        for href, name in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
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
    /* Hero shot. Both competitors lead with a screenshot rather than a
       paragraph — you see what the thing is before you read a word. */
    .hero-big{{padding:70px 0 20px;text-align:center}}
    .hero-big h1{{font-size:clamp(34px,6vw,64px);letter-spacing:-1.5px;
      text-transform:uppercase;font-weight:800;margin-bottom:18px}}
    .hero-big .lead{{margin:0 auto;font-size:18px}}
    .shot{{margin:38px 0 0;border-radius:16px;overflow:hidden;
      border:1px solid var(--line);box-shadow:0 30px 80px rgba(0,0,0,.45);
      background:var(--panel)}}
    .shot img{{display:block;width:100%;height:auto}}
    .shot figcaption{{padding:10px 16px;font-size:12px;color:var(--muted);
      border-top:1px solid var(--line)}}
    /* Showcase: list on the left, selected widget on the right. Switching
       runs on pure CSS — not a line of script on the page. */
    .show{{display:grid;grid-template-columns:230px 1fr;gap:20px;align-items:start}}
    .show-list{{max-height:520px;overflow:auto;padding-right:6px}}
    .show-list label{{display:block;padding:7px 10px;border-radius:8px;
      color:var(--muted);font-size:13.5px;cursor:pointer}}
    .show-list label:hover{{background:var(--panel);color:var(--txt)}}
    .show input{{position:absolute;opacity:0;pointer-events:none}}
    .show-stage{{background:var(--panel);border:1px solid var(--line);
      border-radius:var(--r-card);min-height:320px;display:flex;
      align-items:center;justify-content:center;padding:26px}}
    .show-stage figure{{display:none;text-align:center;max-width:100%}}
    .show-stage img{{max-width:100%;height:auto}}
    .show-stage figcaption{{margin-top:16px;color:var(--muted);font-size:13.5px}}
    .show-stage figcaption b{{display:block;color:var(--txt);font-size:16px;
      margin-bottom:4px}}
    img.th{{width:120px;height:auto;display:block;border-radius:6px;
      background:#0d1014;border:1px solid var(--line)}}
    td:first-child{{width:132px}}
    td .sub{{color:var(--muted);font-size:12.5px;margin-top:3px;max-width:34ch}}
    .sims{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
      gap:12px}}
    .sim{{border:1px solid var(--line);border-radius:var(--r-card);padding:14px 16px;
      background:var(--panel)}}
    .sim b{{display:block;font-size:14.5px;margin-bottom:3px}}
    .sim span{{color:var(--muted);font-size:12.5px}}
    /* Screenshot galleries (settings window, dashboard): numbered
       tabs, one shot at a time, no script. */
    .gal input{{position:absolute;opacity:0;pointer-events:none}}
    .gal-tabs{{display:flex;gap:8px;margin-bottom:12px}}
    .gal-tabs label{{width:30px;height:30px;display:flex;align-items:center;
      justify-content:center;border:1px solid var(--line);border-radius:8px;
      color:var(--muted);font-size:13px;cursor:pointer;
      font-variant-numeric:tabular-nums}}
    .gal-tabs label:hover{{color:var(--txt);border-color:var(--muted)}}
    .gal-stage figure{{display:none}}
    .gal-stage img{{display:block;width:100%;height:auto;border-radius:12px;
      border:1px solid var(--line);box-shadow:0 20px 60px rgba(0,0,0,.4)}}
    .gal-stage figcaption{{color:var(--muted);font-size:14px;margin-top:14px;
      max-width:680px}}
    /* Get-it page: numbered steps with the command under each one. */
    ol.steps{{list-style:none;counter-reset:s;display:grid;gap:14px}}
    ol.steps li{{counter-increment:s;background:var(--panel);
      border:1px solid var(--line);border-radius:var(--r-card);
      padding:16px 20px 16px 58px;position:relative}}
    ol.steps li::before{{content:counter(s);position:absolute;left:18px;top:16px;
      width:24px;height:24px;border-radius:50%;background:var(--accent);
      color:#08111c;font-weight:800;font-size:13px;display:flex;
      align-items:center;justify-content:center}}
    ol.steps b{{display:block;margin-bottom:6px}}
    ol.steps p{{color:var(--muted);font-size:14px;margin-top:6px}}
    pre.cmd{{background:#0b0e12;border:1px solid var(--line);border-radius:8px;
      padding:11px 14px;overflow-x:auto;font-family:ui-monospace,Consolas,monospace;
      font-size:12.5px;color:#cdd3dc;line-height:1.7}}
    .note{{border-left:2px solid var(--warn,#e0a800);padding:2px 0 2px 16px;
      color:var(--muted);font-size:14px;max-width:680px}}
    @media(max-width:760px){{.nums,.why{{grid-template-columns:1fr 1fr}}h1{{font-size:30px}}
      .show{{grid-template-columns:1fr}}.show-list{{max-height:200px}}}}
</style></head><body>
<header><div class="wrap">
  <span class="logo">RACE <b>ENGINEER</b></span>
  <nav>{nav}</nav>
</div></header>
<div class="wrap">{body}</div>
<footer><div class="wrap">A personal project for iRacing. These pages are built
from the code — no number here is typed by hand.</div></footer>
</body></html>"""


# ── страницы ────────────────────────────────────────────────────────────────

WHY = [
    ("Everything in one window",
     "Telemetry, strategy, lap history and analysis — instead of four apps "
     "with four subscriptions."),
    ("An overlay of your own",
     "Every widget is tuned on its own: colour, size and font of each number. "
     "Wheel buttons map to any action."),
    ("Nothing gets lost",
     "Every lap lands on disk with its telemetry. History survives between "
     "sessions, so progress shows across dates, not one drive."),
    ("No smoothing",
     "Raw values at a high refresh rate. Smoothing hides exactly what you open "
     "the numbers for — the scatter and the outliers."),
    ("Analysis in plain words",
     "After a stint the model explains what the car was doing and suggests "
     "setup changes, with the reasoning attached."),
    ("Works offline",
     "It all runs locally. No keys to anyone else's service, and no data "
     "leaves the machine."),
]


def load_shots(root=None):
    """Опись снимков виджетов из docs/widgets/index.json.

    Снимки делает tools/render_widgets.py на демо-данных. Если их нет —
    витрина просто не рисуется, а сайт остаётся рабочим: собирать картинки
    ради страницы «о проекте» никто не обязан.
    """
    base = pathlib.Path(root) if root else (
        ROOT / "docs" / "widgets")
    f = base / "index.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


def _load_index(folder, root=None):
    """Опись снимков из docs/<folder>/index.json.

    Нет файлов — раздел просто не рисуется, сайт остаётся рабочим: собирать
    картинки ради страницы «о проекте» никто не обязан.
    """
    base = pathlib.Path(root) if root else (
        ROOT / "docs" / folder)
    f = base / "index.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


def load_panel_shots(root=None):
    """Снимки панели настроек (tools/render_panel.py)."""
    return _load_index("panel", root)


def load_dashboard_shots(root=None):
    """Снимки дашборда (tools/render_dashboard.py)."""
    return _load_index("dashboard", root)


def gallery(shots, ident, heading, route, alt):
    """Раздел со снимками: пронумерованные вкладки, по одному кадру за раз.

    Переключение — те же радиокнопки и соседний селектор, что и в витрине,
    и с той же ловушкой: инпуты обязаны быть ПРЯМЫМИ детьми `.gal`. «~»
    связывает только элементы с общим родителем; спрячешь инпуты внутрь
    вкладок — и сцена молча останется пустой при правильной на вид разметке.
    """
    if not shots:
        return ""
    inputs, tabs, stage, rules = [], [], [], []
    for i, s in enumerate(shots):
        sel = " checked" if i == 0 else ""
        inputs.append(f'<input type="radio" name="{ident}" id="{ident}{i}"{sel}>')
        tabs.append(f'<label for="{ident}{i}">{i + 1}</label>')
        stage.append(
            f'<figure id="{ident}f{i}"><img src="/{route}/{e(s["file"])}" '
            f'alt="{e(alt)}" loading="lazy">'
            f'<figcaption>{e(s.get("caption") or "")}</figcaption></figure>')
        rules.append(f"#{ident}{i}:checked~.gal-stage #{ident}f{i}{{display:block}}")
        rules.append(f'#{ident}{i}:checked~.gal-tabs label[for="{ident}{i}"]'
                     f"{{background:var(--accent);color:#08111c;border-color:var(--accent)}}")
    return (f"<section><h2>{e(heading)}</h2>"
            f'<style>{"".join(rules)}</style>'
            f'<div class="gal">{"".join(inputs)}'
            f'<div class="gal-tabs">{"".join(tabs)}</div>'
            f'<div class="gal-stage">{"".join(stage)}</div></div></section>')


def panel_gallery(shots):
    """Как это настраивается.

    Витрина показывает, ЧТО видно в игре. На вопрос «а настраивать это как»
    она не отвечает, а у обоих конкурентов именно окно настроек занимает
    половину страницы: покупают не виджеты, а лёгкость подгонки под себя.
    """
    return gallery(shots, "pn", "How you set it up", "panel",
                   "The settings window")


def dashboard_gallery(shots):
    """Второй экран.

    Оверлей на сайте показан, панель настроек показана — а дашборда,
    ради которого половина проекта и написана, человек так и не видел.
    """
    return gallery(shots, "db", "The second screen", "dash",
                   "The dashboard")


def showcase(shots):
    """Витрина всех виджетов: список слева, выбранный справа.

    Переключение сделано на радиокнопках и соседних селекторах CSS — без
    скриптов. Страница статическая, и тащить ради галереи джаваскрипт,
    который надо потом поддерживать, незачем.
    """
    if not shots:
        return ""
    # Радиокнопки лежат ПРЯМЫМИ детьми .show, а не внутри списка. Соседний
    # селектор «~» работает только между элементами с общим родителем: пока
    # инпуты были внутри .show-list, правило #sN:checked~.show-stage ни разу
    # не срабатывало и сцена оставалась пустой.
    inputs, items, stage, rules = [], [], [], []
    for i, w in enumerate(shots):
        sel = ' checked' if i == 0 else ''
        inputs.append(f'<input type="radio" name="shot" id="s{i}"{sel}>')
        items.append(f'<label for="s{i}">{e(w["title"])}</label>')
        doc = w.get("doc") or ""
        stage.append(
            f'<figure id="f{i}"><img src="/w/{e(w["file"])}" '
            f'alt="{e(w["title"])}" loading="lazy">'
            f'<figcaption><b>{e(w["title"])}</b>{e(doc)}</figcaption></figure>')
        rules.append(f"#s{i}:checked~.show-stage #f{i}{{display:block}}")
        rules.append(f'#s{i}:checked~.show-list label[for="s{i}"]'
                     f"{{background:var(--panel);color:var(--txt);font-weight:600}}")
    return (f'<section><h2>What it looks like — {len(shots)}</h2>'
            f'<style>{"".join(rules)}</style>'
            f'<div class="show">{"".join(inputs)}'
            f'<div class="show-list">{"".join(items)}</div>'
            f'<div class="show-stage">{"".join(stage)}</div></div>'
            f'<p class="lead" style="margin-top:14px;font-size:13px">'
            f'Shots rendered by '
            f'<span class="k">python tools/render_widgets.py</span> on demo '
            f'data: the numbers and driver names are made up.</p></section>')


def page_about(cat, shots=None, panels=None, dash=None):
    k = cat["counts"]
    labels = (
        (k["widgets"], ("overlay widget", "overlay widgets")),
        (k["cards"], ("dashboard card", "dashboard cards")),
        (k["tabs"], ("tab", "tabs")),
        (k["endpoints"], ("API endpoint", "API endpoints")),
    )
    nums = "".join(
        f'<div class="num"><div class="v">{v}</div>'
        f'<div class="k">{e(plural(v, *forms))}</div></div>'
        for v, forms in labels)
    why = "".join(f"<div><h3>{e(t)}</h3><p>{e(d)}</p></div>" for t, d in WHY)
    groups = " · ".join(f"{e(g)} — {n}" for g, n in (k["by_group"] or {}).items())
    hero_img = ""
    if (ROOT / "docs" / "hero.png").exists():
        hero_img = ('<figure class="shot"><img src="/hero.png" '
                    'alt="The overlay over the game">'
                    '<figcaption>The overlay over the game: standings, delta, track '
                    'map, fuel, pedals and relative gaps. Built from the real '
                    'widgets on demo data.</figcaption></figure>')
    # Полоса совместимости в духе Go Fast: у них строка логотипов симуляторов.
    # Чужие логотипы не берём — это чужие товарные знаки, а сайт метит
    # в продажу. Поэтому свои плашки: заголовок и пояснение под ним.
    sims = "".join(
        f'<div class="sim"><b>{e(t)}</b><span>{e(d)}</span></div>'
        for t, d in (
            ("iRacing", "the one sim supported"),
            ("Windows 10 · 11", "tested on both"),
            ("Offline", "everything is computed locally"),
            ("One screen or two", "overlay and dashboard run apart"),
            ("Wheel and gamepad", "buttons map to actions"),
        ))
    return shell("About", f"""
<section class="hero-big">
  <h1>A race engineer<br>for <span>iRacing</span></h1>
  <p class="lead">A dashboard on the second screen, an overlay of your own over the
  game, and analysis once you climb out. A project, not a subscription: the data
  stays on your machine and everything runs locally.</p>
  {hero_img}
</section>
<section>
  <h2>Where it runs</h2>
  <div class="sims">{sims}</div>
</section>
{showcase(shots or [])}
{panel_gallery(panels or [])}
{dashboard_gallery(dash or [])}
<section>
  <h2>What is inside</h2>
  <div class="nums">{nums}</div>
  <p class="lead" style="margin-top:14px;font-size:14px">Widgets by group: {groups}.
  The numbers come from the code, via <span class="k">python tools/build_catalog.py</span>.</p>
</section>
<section>
  <h2>Why it works this way</h2>
  <div class="why">{why}</div>
</section>
<section>
  <h2>What comes next</h2>
  <p class="lead">Up soon: a corner-by-corner lap breakdown with the cost of every
  mistake in seconds, lap comparison by distance, and team strategy for endurance.
  The full plan lives in <span class="k">docs/roadmap-overlay-2026-08.md</span>.</p>
</section>""", active="/about")


REPO = "https://github.com/YarRace/iracing-race-engineer"

# Шаги установки. Список, а не кусок текста: человек ставит по одному
# и должен видеть, где он сейчас. Команды — ровно те, что работают на
# Windows; ничего «примерно такого» здесь быть не должно.
STEPS = [
    ("Get the code",
     f"git clone {REPO}\ncd iracing-race-engineer",
     "Windows 10 or 11, on the machine where iRacing runs. The telemetry "
     "SDK is a Windows memory-mapped file — there is no way around that."),
    ("Set up Python",
     "python -m venv .venv\n.venv\\Scripts\\activate\n"
     "pip install -r requirements.txt",
     "Python 3.12. The virtual environment keeps these packages out of "
     "your system Python."),
    ("Start the engineer",
     "python run.py",
     "This is the part that reads the sim and serves the dashboard on "
     "http://localhost:8000. Leave it running."),
    ("Start the overlay",
     "python overlay_app.py",
     "The settings window opens. Tick the overlays you want, place them "
     "with Ctrl+Shift+L, and go drive."),
]

NEEDS = [
    ("iRacing", "running on the same PC"),
    ("Windows 10 · 11", "the SDK is Windows-only"),
    ("Python 3.12", "with pip"),
    ("A second screen", "optional — the dashboard is nicer there"),
]


def page_download(cat, panels=None):
    """Как это взять и запустить.

    Готового установщика нет, и писать «Download» кнопкой поверх пустоты
    нечестно. Поэтому страница говорит прямо: это исходники, ставится
    четырьмя командами, вот они.
    """
    k = cat.get("counts", {})
    needs = "".join(f'<div class="sim"><b>{e(t)}</b><span>{e(d)}</span></div>'
                    for t, d in NEEDS)
    steps = "".join(
        f"<li><b>{e(title)}</b><pre class=\"cmd\">{e(cmd)}</pre>"
        f"<p>{e(note)}</p></li>" for title, cmd, note in STEPS)
    return shell("Get it", f"""
<section class="hero" style="padding:44px 0 10px">
  <h1>Get it running</h1>
  <p class="lead">Four commands and you are on track with
  {k.get('widgets', 0)} {plural(k.get('widgets', 0), 'overlay', 'overlays')}
  and a dashboard. It runs entirely on your own machine.</p>
</section>
<section>
  <h2>What you need</h2>
  <div class="sims">{needs}</div>
</section>
<section>
  <h2>Four steps</h2>
  <ol class="steps">{steps}</ol>
  <p class="note" style="margin-top:20px">There is no download link here on
  purpose: nothing is published yet, and a button over an empty file is worse
  than four honest commands.</p>
</section>
<section>
  <h2>Or build it standalone</h2>
  <p class="lead">If you would rather not keep Python around, build the two
  apps once and run them by double-click afterwards.</p>
  <pre class="cmd">pip install pyinstaller
python tools/build_exe.py</pre>
  <p class="note">You get <span class="k">dist/RaceEngineer</span> and
  <span class="k">dist/RaceEngineerOverlay</span> — a folder each, not a single
  file. One-file builds unpack 120 MB into a temp directory on every launch and
  trip antivirus heuristics doing it. Your data lives next to the app, so
  replacing the folder never touches your lap history.</p>
</section>
{panel_gallery(panels or [])}
<section>
  <h2>If something does not start</h2>
  <p class="lead">The overlays read their data from the engineer. If
  <span class="k">run.py</span> is not running, the panel shows a red dot and
  every widget sits empty — that is the first thing to check. The source and
  the issue tracker live on <a href="{REPO}">GitHub</a>.</p>
</section>""", active="/download")


def _thumb(shot):
    """Миниатюра виджета в таблице каталога.

    Таблица из одних названий не отвечает на главный вопрос — «а как это
    выглядит». Картинка отвечает мгновенно, а места занимает строку.
    """
    if not shot:
        return ""
    return (f'<img class="th" src="/w/{e(shot["file"])}" '
            f'alt="{e(shot["title"])}" loading="lazy">')


def page_catalog(cat, shots=None):
    if not cat["widgets"]:
        body = ('<section><h1>Widgets</h1><div class="empty">The catalogue has not '
                'been built. Run <span class="k">python tools/build_catalog.py</span>.'
                '</div></section>')
        return shell("Widgets", body, active="/catalog")

    shot_by_key = {x["key"]: x for x in (shots or [])}
    # Название плюс ключ ничего не говорят о том, ЧТО виджет показывает.
    # Правый край таблицы всё равно пустовал — там теперь строка описания.
    rows = "".join(
        f"<tr><td>{_thumb(shot_by_key.get(w['key']))}</td>"
        f"<td>{e(w['title'])}<div class=\"sub\">{e(w.get('desc') or '')}</div></td>"
        f'<td><span class="tag {e(w["group"])}">{e(w["group_title"])}</span></td>'
        f'<td class="k">{e(w["key"])}</td>'
        f'<td class="k">{w["width"]}×{w["height"]}</td>'
        f'<td class="k">{e(", ".join(w["endpoints"]) or "—")}</td></tr>'
        for w in cat["widgets"])
    cards = "".join(
        f"<tr><td>{e(c['title'])}</td><td>{e(c['tab_title'])}</td>"
        f'<td class="k">{e(c["key"])}</td></tr>' for c in cat["cards"])
    k = cat["counts"]
    return shell("Widgets", f"""
<section class="hero" style="padding:44px 0 20px">
  <h1>Widgets and cards</h1>
  <p class="lead">{k['widgets']} {plural(k['widgets'], 'widget', 'widgets')} over the
  game and {k['cards']} {plural(k['cards'], 'card', 'cards')} on the dashboard.
  The list is read from the code, so it cannot go stale.</p>
</section>
<section>
  <h2>Overlay — {k['widgets']}</h2>
  <table><tr><th>Name</th><th>Group</th><th>Key</th><th>Size</th>
  <th>Data</th></tr>{rows}</table>
</section>
<section>
  <h2>Dashboard — {k['cards']}</h2>
  <table><tr><th>Card</th><th>Tab</th><th>Key</th></tr>{cards}</table>
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
        body = ('<section><h1>Changelog</h1><div class="empty">No entries yet. '
                'Add a file to <span class="k">docs/news/</span>.</div></section>')
        return shell("Changelog", body, active="/news")
    posts = "".join(
        f'<div class="post"><div class="d">{e(p["date"])}</div>'
        f'<h3>{e(p["title"])}</h3>{_md_lite(p["body"])}</div>' for p in entries)
    return shell("Changelog", f"""
<section class="hero" style="padding:44px 0 10px">
  <h1>What changed</h1>
  <p class="lead">The project changelog. <a href="/news/rss.xml">RSS</a></p>
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
            "<title>Race Engineer — changelog</title>"
            f"<link>{base}/news</link>"
            "<description>Changelog of the Race Engineer project</description>"
            f"{items}</channel></rss>")
