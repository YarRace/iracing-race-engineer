from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

from ire.storage import history

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

@app.get("/")
def index():
    # no-store: браузер не кеширует страницу — всегда свежий UI без Ctrl+F5
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )
