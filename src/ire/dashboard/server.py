from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
import os

from ire import paths
from ire.storage import history
from . import site

app = FastAPI()
STATE = {"live": {}, "result": {}, "strategy": {}, "damage": {}, "race": {}, "standings": [],
         "relative": {}, "wear": {}, "session": {}, "trackmap": {}}

@app.get("/api/live")
def live(): return STATE["live"]

@app.get("/api/records")
def records():
    # рекорды по трассам из истории (Фаза 1). Читатель открывает свой коннект —
    # SQLite (WAL) разводит одновременные чтение из API и запись из live-цикла.
    conn = history.connect()
    try:
        return history.records(conn)
    finally:
        conn.close()

def _clamp(n, lo, hi):
    return max(lo, min(int(n), hi))


@app.get("/api/history")
def lap_history(track: str = Query(""), car: str = Query(""), limit: int = Query(500)):
    """Круги на трассе+машине по времени — для графика прогресса.

    Без трассы и машины отдаём пусто, а не ошибку: карточка дашборда дёргает
    эндпоинт ещё до того, как появится сессия и станет известно, где мы едем.
    """
    if not track or not car:
        return []
    conn = history.connect()          # свой коннект: SQLite (WAL) разводит
    try:                              # чтение из API и запись из live-цикла
        return history.track_history(conn, track, car, _clamp(limit, 0, 2000))
    finally:
        conn.close()


@app.get("/api/stints")
def stints(limit: int = Query(20)):
    """Последние стинты — сводка по каждому выезду."""
    conn = history.connect()
    try:
        return history.recent_stints(conn, _clamp(limit, 0, 500))
    finally:
        conn.close()


@app.get("/api/result")
def result(): return STATE["result"]

@app.get("/api/strategy")
def strategy(): return STATE["strategy"]

@app.get("/api/damage")
def damage(): return STATE["damage"]

@app.get("/api/race")
def race(): return STATE["race"]

@app.get("/api/standings")
def standings(): return STATE["standings"]

@app.get("/api/relative")
def relative(): return STATE["relative"]

@app.get("/api/wear")
def wear(): return STATE["wear"]

@app.get("/api/session")
def session(): return STATE["session"]

@app.get("/api/trackmap")
def trackmap(): return STATE["trackmap"]

@app.get("/wheels/{name}")
def wheel_image(name: str):
    # фото рулей (MOZA KS/ES/RS/FSR/GS) для виджета «Руль» — статик из static/wheels/
    safe = os.path.basename(name)
    path = os.path.join(STATIC, "wheels", safe)
    if not (safe.endswith(".png") and os.path.exists(path)):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/png")

DOCS = paths.res("docs")            # ресурсы сборки, не данные пользователя
STATIC = paths.res("src", "ire", "dashboard", "static")


@app.get("/hero.png")
def hero():
    """Главная картинка сайта — оверлей поверх игры (tools/render_hero.py)."""
    path = os.path.abspath(os.path.join(DOCS, "hero.png"))
    if not os.path.exists(path):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/w/{name}")
def widget_shot(name: str):
    """Снимок виджета для витрины (tools/render_widgets.py).

    basename и проверка расширения — чтобы «/w/../../secret» не увёл
    за пределы каталога снимков.
    """
    safe = os.path.basename(name)
    path = os.path.abspath(os.path.join(DOCS, "widgets", safe))
    if not (safe.endswith(".png") and os.path.exists(path)):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/dash/{name}")
def dashboard_shot(name: str):
    """Снимок дашборда (tools/render_dashboard.py). Защита как у /w/ и /panel/."""
    safe = os.path.basename(name)
    path = os.path.abspath(os.path.join(DOCS, "dashboard", safe))
    if not (safe.endswith(".png") and os.path.exists(path)):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/panel/{name}")
def panel_shot(name: str):
    """Снимок панели настроек (tools/render_panel.py).

    Та же защита, что и у /w/: basename плюс проверка расширения, иначе
    «/panel/../../secret» уводит за пределы каталога снимков.
    """
    safe = os.path.basename(name)
    path = os.path.abspath(os.path.join(DOCS, "panel", safe))
    if not (safe.endswith(".png") and os.path.exists(path)):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/png")


@app.get("/about", response_class=HTMLResponse)
def about():
    """Витрина проекта: что внутри и почему сделано именно так."""
    return site.page_about(site.load_catalog(), site.load_shots(),
                           site.load_panel_shots(), site.load_dashboard_shots())


@app.get("/download", response_class=HTMLResponse)
def download():
    """Как это взять и запустить. Сайт рассказывал про продукт, но не давал его."""
    return site.page_download(site.load_catalog(), site.load_panel_shots())


@app.get("/catalog", response_class=HTMLResponse)
def catalog():
    """Каталог виджетов и карточек — читается из собранного data/catalog.json."""
    return site.page_catalog(site.load_catalog(), site.load_shots())


@app.get("/news", response_class=HTMLResponse)
def news():
    """Свой чейнджлог из docs/news/*.md."""
    return site.page_news(site.read_news())


@app.get("/news/rss.xml")
def news_rss():
    return Response(site.news_rss(site.read_news()), media_type="application/rss+xml")


@app.get("/tokens.css")
def tokens():
    """Палитра проекта. Отдельным файлом, чтобы цвета правились в одном месте."""
    return FileResponse(
        os.path.join(STATIC, "tokens.css"),
        media_type="text/css",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/")
def index():
    # no-store: браузер не кеширует страницу — всегда свежий UI без Ctrl+F5
    return FileResponse(
        os.path.join(STATIC, "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )
