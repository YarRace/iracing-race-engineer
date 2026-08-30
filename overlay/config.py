"""Конфиг оверлея: какие виджеты включены, их геометрия, режим правки.

Чистый (без PySide6) — тестируется. Хранится JSON-файлом на диске, чтобы
раскладка виджетов переживала перезапуск. `edit` по умолчанию False — значит
клики проходят СКВОЗЬ оверлеи (в игру); True — можно двигать/менять размер.
"""
from __future__ import annotations

import copy
import json
import os

# что входит в профиль-снимок (раскладка): включённые оверлеи, их геометрия,
# оформление и прозрачность. Режим правки (edit) — не входит (он временный).
_PROFILE_KEYS = ("enabled", "geo", "opts", "opacity")


class Config:
    def __init__(self, path: str):
        self.path = path
        self.data = {"enabled": {}, "geo": {}, "edit": False, "opts": {}, "opacity": 1.0,
                     "profiles": {}, "active": ""}
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
        self.data.setdefault("edit", False)
        self.data.setdefault("opts", {})
        self.data.setdefault("opacity", 1.0)
        self.data.setdefault("profiles", {})
        self.data.setdefault("active", "")

    def save(self):
        # активный профиль всегда отражает текущую раскладку (авто-синхрон)
        name = self.data.get("active")
        if name:
            self.data.setdefault("profiles", {})[name] = self._snapshot()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except OSError:
            pass

    # ---------- профили раскладок (как пресеты Kapps) ----------
    def _snapshot(self):
        return {k: copy.deepcopy(self.data.get(k)) for k in _PROFILE_KEYS}

    def profiles(self):
        return list(self.data.get("profiles", {}).keys())

    def active_profile(self) -> str:
        return self.data.get("active", "") or ""

    def save_profile(self, name: str):
        """Сохранить текущую раскладку как профиль <name> и сделать его активным."""
        self.data.setdefault("profiles", {})[name] = self._snapshot()
        self.data["active"] = name
        self.save()

    def load_profile(self, name: str) -> bool:
        """Применить сохранённый профиль к текущей раскладке."""
        p = self.data.get("profiles", {}).get(name)
        if p is None:
            return False
        for k in _PROFILE_KEYS:
            if k in p:
                self.data[k] = copy.deepcopy(p[k])
        self.data["active"] = name
        self.save()
        return True

    def delete_profile(self, name: str):
        self.data.get("profiles", {}).pop(name, None)
        if self.data.get("active") == name:
            self.data["active"] = ""
        self.save()

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

    def edit_mode(self) -> bool:
        return bool(self.data.get("edit", False))

    def set_edit_mode(self, val: bool):
        self.data["edit"] = bool(val)
        self.save()

    def opacity(self) -> float:
        try:
            return max(0.3, min(1.0, float(self.data.get("opacity", 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def set_opacity(self, val: float):
        self.data["opacity"] = max(0.3, min(1.0, float(val)))
        self.save()

    def hide_offtrack(self) -> bool:
        return bool(self.data.get("hide_offtrack", False))

    def set_hide_offtrack(self, val: bool):
        self.data["hide_offtrack"] = bool(val)
        self.save()

    # ---- оформление конкретного виджета (фон/шрифт/цвет) ----
    def widget_opt(self, key: str, name: str, default=None):
        return self.data.get("opts", {}).get(key, {}).get(name, default)

    def set_widget_opt(self, key: str, name: str, val):
        self.data.setdefault("opts", {}).setdefault(key, {})[name] = val
        self.save()

    def clear_widget_opts(self, key: str):
        self.data.get("opts", {}).pop(key, None)
        self.save()

    # ---- избранное: сорок четыре строки в списке — это много ----
    def is_favourite(self, key: str) -> bool:
        return key in (self.data.get("favourites") or [])

    def set_favourite(self, key: str, val: bool):
        fav = list(self.data.get("favourites") or [])
        if val and key not in fav:
            fav.append(key)
        elif not val and key in fav:
            fav.remove(key)
        self.data["favourites"] = fav
        self.save()

    def favourites(self):
        return list(self.data.get("favourites") or [])

    # ---- пресеты ОДНОГО виджета ----
    # Профиль запоминает всю раскладку целиком. Но подобрать вид одного
    # виджета и переносить его между раскладками профилем нельзя: он утащит
    # с собой позиции и включённость всех остальных.
    def widget_presets(self, key: str):
        return list((self.data.get("wpresets", {}).get(key) or {}).keys())

    def save_widget_preset(self, key: str, name: str):
        import copy as _copy
        opts = _copy.deepcopy(self.data.get("opts", {}).get(key, {}))
        self.data.setdefault("wpresets", {}).setdefault(key, {})[name] = opts
        self.save()

    def load_widget_preset(self, key: str, name: str) -> bool:
        import copy as _copy
        p = (self.data.get("wpresets", {}).get(key) or {}).get(name)
        if p is None:
            return False
        self.data.setdefault("opts", {})[key] = _copy.deepcopy(p)
        self.save()
        return True

    def delete_widget_preset(self, key: str, name: str):
        (self.data.get("wpresets", {}).get(key) or {}).pop(name, None)
        self.save()
