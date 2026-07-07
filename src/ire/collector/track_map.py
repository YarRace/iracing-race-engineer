"""Построение карты трассы из телеметрии (SDK не отдаёт геометрию трека).

За один круг интегрируем курс (по YawRate) и путь (по Speed) → получаем форму
трассы как ломаную {pct, x, y}. Нормализуем в бокс 0..100 и кэшируем на диск
per-track (проехал круг один раз — карта сохранена навсегда). Машины потом
ставятся на карту по их LapDistPct.

Чистая математика (TrackMapBuilder, normalize_path) тестируется без сима.
"""
from __future__ import annotations

import json
import math
import os
import re


def normalize_path(pts):
    """[(pct, x, y)] сырого пути → [{pct,x,y}] в боксе 0..100 (с полями), по pct."""
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = (maxx - minx) or 1.0
    h = (maxy - miny) or 1.0
    scale = 90.0 / max(w, h)                       # вписать в ~90 с полями
    ox = (100 - w * scale) / 2
    oy = (100 - h * scale) / 2
    out = [{"pct": round(pct, 4),
            "x": round(ox + (x - minx) * scale, 2),
            "y": round(oy + (y - miny) * scale, 2)}
           for pct, x, y in pts]
    out.sort(key=lambda p: p["pct"])
    return out


class TrackMapBuilder:
    """Копит путь за круг и на его завершении строит нормализованную карту."""

    def __init__(self, min_points=50):
        self.min_points = min_points
        self.map = None            # готовая карта: [{pct,x,y}]
        self.new = False           # флаг: карта только что построена (для сохранения)
        self._reset()

    def _reset(self):
        self._pts = []
        self._x = self._y = self._h = 0.0
        self._last_t = None
        self._last_pct = None

    def load(self, cached):
        """Подставить готовую карту (из кэша на диске)."""
        if cached:
            self.map = cached

    def update(self, pct, speed, yaw_rate, t):
        """Один кадр на трассе. Интегрирует курс и позицию; на wrap круга — финализ."""
        if pct is None or speed is None or yaw_rate is None or t is None:
            return
        if self._last_t is None:
            self._last_t, self._last_pct = t, pct
            self._pts.append((pct, 0.0, 0.0))
            return
        dt = t - self._last_t
        if dt <= 0 or dt > 1.0:                    # пауза/скачок — не интегрируем
            self._last_t, self._last_pct = t, pct
            return
        if self._last_pct is not None and pct + 0.5 < self._last_pct:   # круг завершён
            self._finalize()
            self._reset()
            self._last_t, self._last_pct = t, pct
            self._pts.append((pct, 0.0, 0.0))
            return
        self._h += yaw_rate * dt
        self._x += speed * math.cos(self._h) * dt
        self._y += speed * math.sin(self._h) * dt
        self._pts.append((pct, self._x, self._y))
        self._last_t, self._last_pct = t, pct

    def _finalize(self):
        if len(self._pts) >= self.min_points:
            self.map = normalize_path(self._pts)
            self.new = True

    def snapshot(self):
        return {"points": self.map} if self.map else None


# --- кэш карт на диске (per-track) ---
def _maps_dir():
    from ire.storage.history import default_path
    return os.path.join(os.path.dirname(default_path()), "trackmaps")


def _safe(track):
    return re.sub(r"[^a-z0-9]+", "_", (track or "unknown").lower()).strip("_") or "unknown"


def save_map(track, points):
    if not points:
        return
    d = _maps_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, _safe(track) + ".json"), "w", encoding="utf-8") as f:
        json.dump(points, f)


def load_map(track):
    path = os.path.join(_maps_dir(), _safe(track) + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
