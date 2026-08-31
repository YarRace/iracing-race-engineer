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
        # Набор НЕ подтягивается за текущей раскладкой. Раньше подтягивался, и
        # это молча уничтожало сохранённое: собрал «Endurance night», один раз
        # подвигал виджеты под спринт — и набора больше нет, вернуть нечем.
        # Обратная неприятность («подвинул, а в набор не попало») чинится одним
        # нажатием «сохранить» и видна сразу. Текущая раскладка при этом
        # ложится на диск как и раньше — на выходе из программы ничего не
        # теряется, теряется только молчаливая перезапись.
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

    # ---- «включены» и «запущены» — разные вещи ----
    # У Kapps галочка сразу выбрасывает виджет на экран, и настроить раскладку
    # спокойно нельзя: половина экрана уже занята. У RaceLab сначала собирают
    # набор, потом жмут «Start». Разводим одно и другое: галочка = «входит
    # в раскладку», кнопка = «показать всё это поверх игры».
    def overlays_running(self) -> bool:
        return bool(self.data.get("running", False))

    def set_overlays_running(self, val: bool):
        self.data["running"] = bool(val)
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

    def reset_all(self):
        """Вернуть к заводскому виду ВСЕ виджеты разом.

        Стираем оформление, позиции и общую прозрачность. НЕ трогаем то,
        что человек выбирал, а не подгонял: какие оверлеи включены,
        избранное, сохранённые раскладки и пресеты. «Сбросить вид» и
        «забыть, чем я пользуюсь» — разные желания, и второе никто
        не заказывал.
        """
        self.data["opts"] = {}
        self.data["geo"] = {}
        self.data["opacity"] = 1.0
        self.save()

    def reset_widget(self, key: str):
        """Вернуть виджет к заводскому виду: оформление И размер с позицией.

        Одного `clear_widget_opts` мало. Растянутый виджет остаётся растянутым,
        и «сброс» выглядит наполовину сделанным: цвета вернулись, а рамка нет.
        Позиция стирается вместе с размером — иначе виджет останется висеть
        там, куда его утащили, но уже другого размера.
        """
        self.data.get("opts", {}).pop(key, None)
        self.data.get("geo", {}).pop(key, None)
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

    # ---- раскладка одним файлом ----
    # Профили живут внутри overlay_config.json и никуда из него не уезжают.
    # Перенести настроенную раскладку на другой компьютер можно было только
    # копированием всего файла — вместе с чужими профилями и избранным.
    # Отсюда отдельный обмен: один файл = одна раскладка.
    EXPORT_FORMAT = "race-engineer-layout"
    EXPORT_VERSION = 1

    def export_layout(self, path: str, name: str = "") -> str:
        """Сохранить текущую (или названную) раскладку отдельным файлом."""
        snap = (self.data.get("profiles", {}).get(name) if name else None) or self._snapshot()
        bundle = {
            "format": self.EXPORT_FORMAT,
            "version": self.EXPORT_VERSION,
            "name": name or self.active_profile() or "layout",
            "layout": copy.deepcopy(snap),
            # избранное и пресеты виджетов — часть настроенного вида, без них
            # на новой машине пришлось бы накликивать всё заново
            "favourites": list(self.data.get("favourites") or []),
            "wpresets": copy.deepcopy(self.data.get("wpresets", {})),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=1, ensure_ascii=False)
        return bundle["name"]

    BACKUP_DIR = "layout-backups"
    BACKUP_KEEP = 10

    def backup_layout(self, today: str = "") -> str:
        """Снимок раскладки рядом с конфигом — один файл на день.

        Настройки правятся понемногу и каждый день; заметить, что вчера
        было лучше, обычно получается уже назавтра. Отката не было вовсе:
        конфиг перезаписывается на каждое движение ползунка.

        Один файл на дату, а не на запуск: иначе за месяц накопится триста
        снимков и найти в них нужный нельзя. Старые подрезаются до
        BACKUP_KEEP — папка не должна расти без предела.

        Возвращает путь к файлу или "" — молча, если записать не вышло:
        уронить выход из приложения из-за резервной копии нельзя.
        """
        import datetime
        import glob

        stamp = today or datetime.date.today().isoformat()
        d = os.path.join(os.path.dirname(os.path.abspath(self.path)), self.BACKUP_DIR)
        try:
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, f"layout-{stamp}.json")
            self.export_layout(path)
            old = sorted(glob.glob(os.path.join(d, "layout-*.json")))
            for f in old[:-self.BACKUP_KEEP]:
                try:
                    os.remove(f)
                except OSError:
                    pass
            return path
        except OSError:
            return ""

    def import_layout(self, path: str, name: str = "") -> str:
        """Прочитать файл раскладки, сохранить её профилем и применить.

        Проверяем поле format: подсунуть сюда любой JSON легко, а молча
        принять чужой файл — значит потерять свою раскладку без объяснений.
        Незнакомые ключи виджетов не мешают: раскладка читается по ключу,
        а лишние записи никто не спрашивает.
        """
        with open(path, encoding="utf-8") as f:
            bundle = json.load(f)
        if not isinstance(bundle, dict) or bundle.get("format") != self.EXPORT_FORMAT:
            raise ValueError("not a Race Engineer layout file")
        layout = bundle.get("layout")
        if not isinstance(layout, dict):
            raise ValueError("layout file has no layout")

        for k in _PROFILE_KEYS:
            if k in layout:
                self.data[k] = copy.deepcopy(layout[k])
        if isinstance(bundle.get("favourites"), list):
            self.data["favourites"] = list(bundle["favourites"])
        if isinstance(bundle.get("wpresets"), dict):
            # свои пресеты не выбрасываем: сливаем, чужие поверх одноимённых
            merged = copy.deepcopy(self.data.get("wpresets", {}))
            for wkey, presets in bundle["wpresets"].items():
                if isinstance(presets, dict):
                    merged.setdefault(wkey, {}).update(copy.deepcopy(presets))
            self.data["wpresets"] = merged

        final = (name or bundle.get("name") or "imported").strip() or "imported"
        self.data.setdefault("profiles", {})[final] = self._snapshot()
        self.data["active"] = final
        self.save()
        return final
