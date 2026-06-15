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
    setup: dict[str, Any], delta: dict[str, Any], setup_changes=None
) -> list[dict[str, Any]]:
    """Собирает список ручных изменений ``from -> to`` по дельте.

    Args:
        setup: результат :func:`ire.setup.sto_reader.read_sto` с ключом
            ``"fields"`` (плоский dict ``{путь_через_точку: значение}``).
        delta: ``{плоский_путь: новое_значение}`` — что нужно изменить.
        setup_changes: список ``{"field", "why", ...}`` из ответа модели —
            берём из него пояснение ``why`` для каждого поля (опционально).

    Returns:
        Список dict-ов ``{"field", "from", "to", "why"}``.
        Никаких файловых операций не выполняется; ``setup`` не мутируется.
    """
    fields = setup["fields"]
    why_by_field = {c.get("field"): c.get("why", "") for c in (setup_changes or [])}
    return [
        {"field": field, "from": fields.get(field), "to": to,
         "why": why_by_field.get(field, "")}
        for field, to in delta.items()
    ]


def build_setup_sheet(setup: dict[str, Any], delta: dict[str, Any]) -> str:
    """Полный читаемый лист сетапа: ВСЕ поля по секциям, изменённые помечены.

    `.sto` загрузить в iRacing нельзя (формат закрыт), поэтому это «шпаргалка» —
    текст со всеми текущими значениями, где правки видны как
    ``← ИЗМЕНИТЬ (было …)``. Удобно держать рядом и внести в гараже.

    Args:
        setup: результат :func:`ire.setup.sto_reader.read_sto` (`{"fields", ...}`).
        delta: ``{плоский_путь: новое_значение}`` — рекомендованные правки.

    Returns:
        Многострочный текст, сгруппированный по секциям.
    """
    fields = setup["fields"]
    n = len(delta)
    lines = [
        "РЕКОМЕНДОВАННЫЙ СЕТАП — Cadillac GTP",
        f"Изменений: {n}. Строки с пометкой ИЗМЕНИТЬ внести в гараже iRacing вручную.",
        "(.sto-файл закрыт и не загружается — это справочный лист.)",
        "",
    ]
    last_section = object()
    for path, val in fields.items():
        parts = path.split(".")
        section = ".".join(parts[:-1]) if len(parts) > 1 else "(прочее)"
        name = parts[-1]
        if section != last_section:
            lines.append(f"[{section}]")
            last_section = section
        if path in delta:
            lines.append(f"  {name}: {delta[path]}   <- ИЗМЕНИТЬ (было {val})")
        else:
            lines.append(f"  {name}: {val}")
    return "\n".join(lines)
