"""Конфиг оверлея: какие виджеты включены, их геометрия, глобальная блокировка.

Чистый (без PySide6) — тестируется. Хранится JSON-файлом на диске, чтобы
раскладка виджетов переживала перезапуск.
"""
from __future__ import annotations

import json
import os


class Config:
    def __init__(self, path: str):
        self.path = path
        self.data = {"enabled": {}, "geo": {}, "locked": False}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.data.update(d)
        except (OSError, ValueError):
            pass
        self.data.setdefault("enabled", {})
        self.data.setdefault("geo", {})
        self.data.setdefault("locked", False)

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except OSError:
            pass

    def is_enabled(self, key: str, default: bool = False) -> bool:
        return bool(self.data["enabled"].get(key, default))

    def set_enabled(self, key: str, val: bool):
        self.data["enabled"][key] = bool(val)
        self.save()

    def geometry(self, key: str):
        g = self.data["geo"].get(key)
        return tuple(g) if (isinstance(g, list) and len(g) == 4) else None

    def set_geometry(self, key: str, x, y, w, h):
        self.data["geo"][key] = [int(x), int(y), int(w), int(h)]
        self.save()

    def locked(self) -> bool:
        return bool(self.data.get("locked", False))

    def set_locked(self, val: bool):
        self.data["locked"] = bool(val)
        self.save()
