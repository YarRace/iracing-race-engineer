"""Режим «ручной ввод» изменений сетапа.

Современный iRacing ``.sto`` — закрытый бинарный формат, записывать его нельзя.
Поэтому этот модуль ничего не пишет на диск: вместо правки исходного файла он
вычисляет дельту ``from -> to`` относительно прочитанного сетапа и возвращает
список изменений для дашборда. Гонщик переносит эти значения в игру вручную.
Исходный сетап остаётся неизменным.
"""

from __future__ import annotations

from typing import Any


def build_manual_changes(
    setup: dict[str, Any], delta: dict[str, Any]
) -> list[dict[str, Any]]:
    """Собирает список ручных изменений ``from -> to`` по дельте.

    Args:
        setup: результат :func:`ire.setup.sto_reader.read_sto` с ключом
            ``"fields"`` (плоский dict ``{путь_через_точку: значение}``).
        delta: ``{плоский_путь: новое_значение}`` — что нужно изменить.

    Returns:
        Список dict-ов ``{"field": путь, "from": текущее, "to": новое}``.
        Никаких файловых операций не выполняется; ``setup`` не мутируется.
    """
    fields = setup["fields"]
    return [
        {"field": field, "from": fields.get(field), "to": to}
        for field, to in delta.items()
    ]
