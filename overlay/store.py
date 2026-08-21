"""Общий кэш данных с ФОНОВЫМ опросом — чтобы GUI не лагал.

Опрос сети идёт в отдельном потоке (не блокирует отрисовку). Держим одно
keep-alive соединение (httpx.Client) и опрашиваем ТОЛЬКО те эндпоинты, что нужны
включённым сейчас виджетам (panel.set_active). GUI просто читает готовые данные.
"""
from __future__ import annotations

import threading
import time

import httpx

DASH = "http://localhost:8000"
ENDPOINTS = ("live", "race", "strategy", "standings", "relative",
             "wear", "session", "damage", "trackmap", "result")


class Store:
    def __init__(self, base: str = DASH):
        self.base = base
        self._d = {}
        self._client = httpx.Client(timeout=0.6)          # keep-alive, а не новое соединение
        self._active = set()                              # какие эндпоинты реально опрашивать
        self._lock = threading.Lock()
        self._run = True
        self.ok = False

    def set_active(self, endpoints):
        """Опрашивать только эти эндпоинты (объединение по включённым виджетам)."""
        with self._lock:
            self._active = set(endpoints)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False

    def _loop(self):
        while self._run:
            with self._lock:
                eps = set(self._active)
            eps.add("live")                               # heartbeat: связь проверяем всегда
            ok = False
            for ep in eps:
                try:
                    self._d[ep] = self._client.get(f"{self.base}/api/{ep}").json()
                    ok = True
                except Exception:
                    pass
            self.ok = ok                                  # достучались ли до инженера
            time.sleep(0.05)                              # ~20 опросов/сек — свежо и легко (в фоне, GUI не трогает)

    def get(self, ep: str):
        v = self._d.get(ep)
        if v is None:
            return [] if ep == "standings" else {}
        return v
