from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

app = FastAPI()
STATE = {"live": {}, "result": {}, "strategy": {}}

@app.get("/api/live")
def live(): return STATE["live"]

@app.get("/api/result")
def result(): return STATE["result"]

@app.get("/api/strategy")
def strategy(): return STATE["strategy"]

@app.get("/")
def index():
    # no-store: браузер не кеширует страницу — всегда свежий UI без Ctrl+F5
    return FileResponse(
        os.path.join(os.path.dirname(__file__), "static", "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )
