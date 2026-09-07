"""Фотография трассы под картой — фон, а не украшение.

Кладётся в `data/trackphotos/`. Имя файла — как угодно: `lemans.jpg`,
`Le Mans.png`, `circuit-de-la-sarthe.webp`. Имя нормализуется (только
буквы и цифры, нижний регистр) и сверяется с названием трассы из SDK,
поэтому попасть в него точь-в-точь не нужно.

Нет файла — карта просто рисуется на своём обычном фоне. Ронять оверлей
из-за картинки нельзя: она ничего не сообщает, она фон.

Тот же приём, что в `logos.py`: один проход по папке, кэш на время
работы. Новые файлы подхватятся после перезапуска.
"""
from __future__ import annotations

import os

from PySide6.QtGui import QPixmap

_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
_cache = {}
_index = None


def _dir():
    try:
        from ire import paths
        return str(paths.data_dir() / "trackphotos")
    except Exception:                                    # noqa: BLE001
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "trackphotos")


DIR = _dir()


def _norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _build_index():
    idx = {}
    try:
        for fn in os.listdir(DIR):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in _EXT:
                idx.setdefault(_norm(stem), os.path.join(DIR, fn))
    except OSError:
        pass
    return idx


def photo(track, config=None):
    """QPixmap для трассы или None.

    Сначала ищем связку «трасса + конфигурация» — у Ле-Мана и Спа
    конфигураций несколько, и фон от другой выглядит как чужая трасса.
    Потом просто трассу.
    """
    global _index
    if not track:
        return None
    if _index is None:
        _index = _build_index()
    for key in ([_norm(f"{track} {config}")] if config else []) + [_norm(track)]:
        if key in _cache:
            if _cache[key] is not None:
                return _cache[key]
            continue
        path = _index.get(key)
        if not path:
            hits = [p for k, p in _index.items() if k.startswith(key)] \
                or [p for k, p in _index.items() if key and key in k]
            path = hits[0] if hits else None
        px = None
        if path:
            got = QPixmap(path)
            px = got if not got.isNull() else None
        _cache[key] = px
        if px is not None:
            return px
    return None
