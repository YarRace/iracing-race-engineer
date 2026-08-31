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


@app.get("/api/corners")
def corners_analysis(lap: str = Query(""), ref: str = Query("")):
    """Разбор круга по поворотам: где потеряно время и почему.

    Без параметров берём последний сохранённый круг и лучший на той же
    трассе и машине. Явные пути нужны, чтобы сравнить любые два круга
    из истории, а не только свежий с рекордом.
    """
    from ire.metrics import corners as C
    from ire.storage import laps as L

    root = L.default_root()
    meta = L.list_laps(root)
    if not meta:
        return {"ok": False, "reason": "no saved laps yet"}

    def pick(path, fallback):
        if not path:
            return fallback
        safe = os.path.basename(path)
        hit = next((m for m in meta if os.path.basename(m["path"]) == safe), None)
        return hit                       # чужой путь сюда не пройдёт: только имя

    latest = max(meta, key=lambda m: m.get("ts") or "")
    lap_meta = pick(lap, latest)
    if lap_meta is None:
        return {"ok": False, "reason": "lap not found"}
    # Эталон с Garage 61: ref=g61 (лучший подходящий) или ref=g61:<id>.
    if ref.startswith("g61"):
        from ire.collector import garage61 as G
        mine = L.load_lap(lap_meta["path"])
        _, _, want = ref.partition(":")
        if want:
            g = G.download_lap({"id": want, "track": mine.get("track"),
                                "car": mine.get("car")})
            why = "Garage 61 did not hand over that lap"
        else:
            g, why = G.best_reference(mine.get("track"), mine.get("car"),
                                      slower_than=mine.get("lap_time"))
        if not g:
            return {"ok": False, "reason": why or "no Garage 61 lap"}
        res = C.analyse(mine, g)
        res["lap_file"] = os.path.basename(lap_meta["path"])
        res["ref_file"] = f"g61:{g.get('g61_id')}"
        res["ref_driver"] = g.get("driver")
        res["ref_source"] = "Garage 61"
        return res

    ref_meta = pick(ref, C.pick_reference(meta, lap_meta))
    if ref_meta is None:
        return {"ok": False, "reason": "no second lap on this track and car yet"}

    mine = L.load_lap(lap_meta["path"])
    res = C.analyse(mine, L.load_lap(ref_meta["path"]))

    # Свой эталон не подошёл (у одного из кругов обрезана телеметрия) —
    # пробуем Garage 61, прежде чем показать отказ. Отказ верен, но это
    # тупик: рядом лежит круг, с которым сравнение получится.
    if not res.get("ok") and not ref:
        from ire.collector import garage61 as G
        if G.available():
            g, _ = G.best_reference(mine.get("track"), mine.get("car"),
                                    slower_than=mine.get("lap_time"))
            if g:
                alt = C.analyse(mine, g)
                if alt.get("ok"):
                    alt["lap_file"] = os.path.basename(lap_meta["path"])
                    alt["ref_file"] = f"g61:{g.get('g61_id')}"
                    alt["ref_driver"] = g.get("driver")
                    alt["ref_source"] = "Garage 61"
                    alt["fell_back"] = res.get("reason", "")
                    return alt

    # Какие круги ВЗЯЛИ на самом деле. Без этого выпадашки на странице
    # показывают первый круг списка, пока человек не выбрал сам, — и врут:
    # в шапке одно время, в выборе другое.
    res["lap_file"] = os.path.basename(lap_meta["path"])
    res["ref_file"] = os.path.basename(ref_meta["path"])
    return res


@app.get("/api/corners/line")
def corner_line(seg: int = Query(0), lap: str = Query(""), ref: str = Query("")):
    """Две траектории в одном повороте: твоя и эталонная.

    Отдельным запросом, а не внутри разбора: линия нужна только когда её
    смотрят, а весит она больше, чем весь остальной ответ.
    """
    from ire.metrics import corners as C

    res = corners_analysis(lap=lap, ref=ref)
    if not res.get("ok") or not res.get("has_line"):
        return {"ok": False, "reason": res.get("reason") or "no coordinates in these laps"}
    segs = res.get("segments") or []
    if not segs:
        return {"ok": False, "reason": "no corners"}
    i = max(0, min(int(seg), len(segs) - 1))
    ln = _line_for(lap, ref, segs[i])
    if not ln:
        return {"ok": False, "reason": "could not build the line"}
    return {"ok": True, "corner": segs[i]["index"], **ln}


def _line_for(lap, ref, seg):
    """Достаёт оба круга ещё раз и строит линию. Дублирует загрузку, но
    делает это ТОЛЬКО когда линию действительно попросили."""
    from ire.metrics import corners as C
    from ire.storage import laps as L

    meta = L.list_laps(L.default_root())
    if not meta:
        return None

    def load(which, fallback):
        if which.startswith("g61:"):
            from ire.collector import garage61 as G
            return G.load_cached(which.split(":", 1)[1])
        safe = os.path.basename(which) if which else ""
        hit = next((m for m in meta if os.path.basename(m["path"]) == safe), fallback)
        return L.load_lap(hit["path"]) if hit else None

    latest = max(meta, key=lambda m: m.get("ts") or "")
    a = load(lap, latest)
    if ref.startswith("g61"):
        from ire.collector import garage61 as G
        _, _, want = ref.partition(":")
        b = G.load_cached(want) if want else None
        if b is None:
            b, _ = G.best_reference(a.get("track"), a.get("car"),
                                    slower_than=a.get("lap_time"))
    else:
        b = load(ref, C.pick_reference(meta, {**(a or {}), "path": ""}))
    if not a or not b:
        return None
    return C.line(a, b, seg)


@app.get("/api/garage61")
def garage61_laps(track: str = Query(""), car: str = Query("")):
    """Круги других пилотов на этой трассе — эталоны из Garage 61.

    Свой лучший круг показывает, где ты хуже СЕБЯ. Чужой быстрый — где
    вообще можно быстрее, а это другой вопрос и куда более полезный.
    """
    from ire.collector import garage61 as G

    if not G.available():
        return {"ok": False, "laps": [],
                "reason": "no Garage 61 token — put it in data/garage61_token.txt"}
    if not track:
        # Без явной трассы берём ту, где стоим. До выезда её нет, и это
        # не ошибка: просто ещё нечего спрашивать.
        from ire.storage import laps as L
        saved = L.list_laps(L.default_root())
        if saved:
            latest = max(saved, key=lambda m: m.get("ts") or "")
            track, car = latest.get("track") or "", car or latest.get("car") or ""
    if not track:
        return {"ok": False, "laps": [], "reason": "no track yet — drive a lap first"}
    return G.list_laps(track, car or None, limit=25)


@app.get("/api/iracing/profile")
def iracing_profile():
    """Имя, iRating и лицензия из официального API iRacing.

    Garage 61 отдаёт имя и круги, но рейтинг — данные самого iRacing.
    Вход требует логина и пароля, которые кладёт САМ человек в
    data/iracing_auth.json; сюда они не попадают и в логи не пишутся.
    """
    from ire.collector import iracing_api as IR
    return IR.profile()


@app.get("/api/garage61/board")
def garage61_board(track: str = Query(""), car: str = Query(""),
                   season: int = Query(0), clean: int = Query(1)):
    """Таблица времён: место, пилот, круг, отставание от лидера.

    Тот вопрос, ради которого Garage 61 и нужен: не «где я хуже себя»,
    а «на каком я месте среди всех и сколько до первого».
    """
    from ire.collector import garage61 as G

    if not G.available():
        return {"ok": False, "rows": [],
                "reason": "no Garage 61 token — put it in data/garage61_token.txt"}
    if not track:
        from ire.storage import laps as L
        saved = L.list_laps(L.default_root())
        if saved:
            latest = max(saved, key=lambda m: m.get("ts") or "")
            track, car = latest.get("track") or "", car or latest.get("car") or ""
    if not track:
        return {"ok": False, "rows": [], "reason": "no track yet — drive a lap first"}
    return G.leaderboard(track, car or None, season or None, clean_only=bool(clean))


@app.get("/api/laps")
def saved_laps(track: str = Query(""), car: str = Query("")):
    """Список сохранённых кругов — для выбора, что с чем сравнивать."""
    from ire.storage import laps as L
    out = []
    for m in L.list_laps(L.default_root(), track or None, car or None):
        m["file"] = os.path.basename(m.pop("path", ""))
        out.append(m)
    return out


@app.get("/api/laps/broken")
def broken_laps_api():
    """Круги, по которым нельзя сравнивать. Только СПИСОК, без удаления."""
    from ire.storage import laps as L
    out = []
    for m in L.broken_laps(L.default_root()):
        m["file"] = os.path.basename(m.pop("path", ""))
        out.append(m)
    return {"ok": True, "laps": out}


@app.post("/api/laps/broken")
def delete_broken_laps():
    """Удалить их. POST, а не GET: GET не должен ничего стирать — по нему
    ходят и предзагрузчики браузера, и случайное обновление страницы."""
    from ire.storage import laps as L
    root = L.default_root()
    bad = L.broken_laps(root)
    n = L.delete_laps([m["path"] for m in bad])
    return {"ok": True, "deleted": n}


@app.get("/api/stintplan")
def stint_plan_api(drivers: str = Query(""), start: str = Query(""),
                   pit: float = Query(60.0), offsets: str = Query(""),
                   max_stint: float = Query(0.0), free: str = Query(""),
                   fmt: str = Query("")):
    """Командный план стинтов: кто, когда и сколько едет.

    Пилоты и время старта приходят от человека — их взять неоткуда;
    темп, расход и объём бака берутся из живой гонки.
    """
    from ire.metrics import stint_plan as SP

    names = [d.strip() for d in drivers.split(",") if d.strip()]
    off = {}
    for pair in offsets.split(","):
        if ":" in pair:
            who, _, hours = pair.partition(":")
            try:
                off[who.strip()] = float(hours)
            except ValueError:
                pass
    res = SP.from_live(STATE.get("strategy"), STATE.get("session"), names,
                       pit_seconds=pit, start=start or None, offsets=off,
                       max_stint_minutes=max_stint or None,
                       availability=SP.parse_availability(free))
    if fmt == "text":
        # Отдаём файлом: план уносят в Discord, а не читают в адресной строке.
        return Response(SP.as_text(res), media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition":
                                 'attachment; filename="stint-plan.txt"'})
    return res

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
