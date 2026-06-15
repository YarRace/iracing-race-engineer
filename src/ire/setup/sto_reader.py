"""Чтение сетапа из CarSetup (SDK ``ir["CarSetup"]``).

Современный iRacing ``.sto`` — закрытый бинарный формат, парсить его нельзя.
Источник сетапа в проекте — открытый вложенный dict ``ir["CarSetup"]`` либо его
JSON-дамп на диске. Этот модуль расплющивает вложенные секции в плоский словарь
``fields`` с путём-ключом через точку.
"""

from __future__ import annotations

import json
from typing import Any


def _flatten(node: dict[str, Any], prefix: str, out: dict[str, Any]) -> None:
    """Рекурсивно расплющивает вложенные dict-ы в плоский ``out``.

    Рекурсия идёт по dict-ам; как только значение не dict (строка/число) — это
    лист, и он пишется в ``out`` под накопленным путём.
    """
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten(value, path, out)
        else:
            out[path] = value


def read_sto(source: str | dict[str, Any]) -> dict[str, Any]:
    """Читает сетап из CarSetup и возвращает плоское представление.

    Args:
        source: путь к JSON-файлу дампа CarSetup (``str``) либо уже готовый
            вложенный dict (живой ``ir["CarSetup"]``).

    Returns:
        ``{"fields": <плоский dict>, "raw": <исходная вложенная структура>}``,
        где ключи ``fields`` — пути через точку,
        напр. ``"TiresAero.LeftFront.StartingPressure"``.
    """
    if isinstance(source, str):
        with open(source, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = source

    fields: dict[str, Any] = {}
    _flatten(raw, "", fields)

    return {"fields": fields, "raw": raw}
