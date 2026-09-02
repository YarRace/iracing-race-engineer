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

from PySide6.QtCore import Qt

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
PROBE = 200          # сторона уменьшенной копии для поиска рамки
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
                px = _trim(cand)
        except Exception:
            px = None
    _cache[name] = px
    return px


def _trim(px):
    """Обрезать прозрачные поля вокруг знака.

    В скачанных логотипах знак занимает малую часть холста: у Ferrari — 229
    на 366 внутри картинки 640 на 426, то есть 31%. Виджет масштабирует
    КАРТИНКУ ЦЕЛИКОМ, поэтому сам щит выходил 21 на 34 точки вместо честных
    40 в высоту — и выглядел мыльным пятном.

    Рамку ищем по УМЕНЬШЕННОЙ копии. Первая версия обходила все точки, и на
    Aston Martin (6000 на 3000, восемнадцать миллионов точек) это заняло 3.3
    секунды — оверлей замер бы посреди гонки, когда рядом окажется такая
    машина. По копии в 200 точек выходит меньше миллисекунды, а поля мы
    режем с запасом, так что разницы в картинке нет.
    """
    img = px.toImage()
    if img.isNull() or not img.hasAlphaChannel():
        return px
    w, h = img.width(), img.height()
    if w < 2 or h < 2:
        return px

    probe = img.scaled(min(w, PROBE), min(h, PROBE),
                       Qt.KeepAspectRatio, Qt.FastTransformation)
    pw, ph = probe.width(), probe.height()
    if pw < 1 or ph < 1:
        return px

    # Порог 8, а не 0: по краю остаётся почти прозрачная кайма от сглаживания,
    # и по нулю обрезка не сработала бы вовсе.
    left, right, top, bottom = pw, -1, ph, -1
    for y in range(ph):
        for x in range(pw):
            if (probe.pixel(x, y) >> 24) & 0xFF > 8:
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                bottom = y
    if right < left or bottom < top:
        return px

    kx, ky = w / pw, h / ph
    # Запас в одну точку уменьшенной копии с каждой стороны: рамка найдена
    # приблизительно, и лучше оставить лишний пиксель поля, чем срезать знак.
    x0 = max(0, int((left - 1) * kx))
    y0 = max(0, int((top - 1) * ky))
    x1 = min(w - 1, int((right + 2) * kx))
    y1 = min(h - 1, int((bottom + 2) * ky))
    if (x1 - x0 + 1) * (y1 - y0 + 1) >= w * h * 0.98:
        return px                                   # полей и так нет
    return px.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
