"""Логотипы марок машин для таблицы заезда.

Файлы кладутся в `data/logos/`. Имя — как угодно (регистр и пробелы не важны):
`porsche.png`, `Porsche.png`, `Aston Martin.png`, `aston-martin.png` — всё подхватится,
потому что имя нормализуется (только буквы/цифры, нижний регистр) и сверяется с маркой
из `standings.manufacturer_of` (astonmartin, bmw, ferrari, …).

Если файла нет — просто не рисуем, без падений. Кэш на время работы (новые файлы
подхватятся после перезапуска приложения).
"""
from __future__ import annotations

import os

def _logo_dir():
    """Папка с логотипами — РЯДОМ С ПРОГРАММОЙ, а не внутри её пакета.

    Путь строился от __file__, и в собранном приложении это уводило внутрь
    _internal: логотипы, положенные человеком рядом с .exe, не находились, а
    положить их «правильно» он не мог — папка внутри сборки исчезает при
    следующем обновлении. Через ire.paths адрес один и тот же и в исходниках,
    и в сборке.
    """
    try:
        from ire import paths
        return str(paths.data_dir() / "logos")
    except Exception:                                    # noqa: BLE001
        # Оверлей должен подниматься даже когда пакета инженера рядом нет.
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "data", "logos")


_DIR = _logo_dir()
_IMG_EXT = (".png", ".svg", ".jpg", ".jpeg", ".webp", ".bmp")
_cache = {}
_index = None


def dir_path():
    return _DIR


def _norm(s):
    """'Aston Martin' → 'astonmartin' (только буквы/цифры, нижний регистр)."""
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _build_index():
    """{нормализованное_имя_файла: путь} — один проход по папке."""
    idx = {}
    try:
        for fn in os.listdir(_DIR):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in _IMG_EXT:
                idx.setdefault(_norm(stem), os.path.join(_DIR, fn))
    except OSError:
        pass
    return idx


def logo(name):
    """QPixmap логотипа по марке (регистр/пробелы в имени файла не важны), или None."""
    global _index
    if not name:
        return None
    if name in _cache:
        return _cache[name]
    if _index is None:
        _index = _build_index()
    px = None
    key = _norm(name)
    path = _index.get(key)                               # точное совпадение
    if not path:                                         # запас: имя файла содержит марку
        hits = [p for k, p in _index.items() if k.startswith(key)] \
            or [p for k, p in _index.items() if key in k]
        path = hits[0] if hits else None
    if path:
        try:
            from PySide6.QtGui import QPixmap
            cand = QPixmap(path)
            if not cand.isNull():
                px = cand
        except Exception:
            px = None
    _cache[name] = px
    return px
