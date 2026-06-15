from fastapi import FastAPI
from fastapi.responses import FileResponse
import os

app = FastAPI()
STATE = {"live": {}, "result": {}}

@app.get("/api/live")
def live(): return STATE["live"]

@app.get("/api/result")
def result(): return STATE["result"]

@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))
