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
    ``<- CHANGE (was …)``. Удобно держать рядом и внести в гараже.

    Args:
        setup: результат :func:`ire.setup.sto_reader.read_sto` (`{"fields", ...}`).
        delta: ``{плоский_путь: новое_значение}`` — рекомендованные правки.

    Returns:
        Многострочный текст, сгруппированный по секциям.
    """
    fields = setup["fields"]
    n = len(delta or {})
    lines = [
        "RECOMMENDED SETUP — Cadillac GTP",
        f"Changes: {n}. Enter the lines marked CHANGE by hand in the iRacing garage.",
        "(The .sto file is closed and cannot be loaded — this is a reference sheet.)",
        "",
    ]
    last_section = object()
    for path, val in fields.items():
        parts = path.split(".")
        section = ".".join(parts[:-1]) if len(parts) > 1 else "(other)"
        name = parts[-1]
        if section != last_section:
            lines.append(f"[{section}]")
            last_section = section
        if delta and path in delta:
            lines.append(f"  {name}: {delta[path]}   <- CHANGE (was {val})")
        else:
            lines.append(f"  {name}: {val}")
    return "\n".join(lines)


# Верхние секции CarSetup = вкладки, как в гараже iRacing (короткие подписи).
SECTION_TITLES = {
    "TiresAero": "Tires & aero",
    "Chassis": "Chassis",
    "BrakesDriveUnit": "Brakes & drive unit",
    "Dampers": "Dampers",
    "Suspension": "Suspension",
}


def build_setup_tabs(setup: dict[str, Any], delta: dict[str, Any]) -> list[dict[str, Any]]:
    """Сетап-лист по ВКЛАДКАМ (как экран настроек iRacing), а не простынёй.

    Группирует поля по верхней секции (вкладка) и подгруппе; в каждой строке —
    имя параметра, значение и, если поле в ``delta``, новое значение ``to``.
    Имена параметров оставляем как в iRacing (английские) — их же вводить в игре.

    Returns:
        Список вкладок:
        ``[{"section", "title", "changed", "groups": [{"group", "rows": [
            {"name", "value", "to", "changed"}]}]}]`` — в порядке появления полей.
    """
    fields = setup["fields"]
    delta = delta or {}
    order: list[str] = []
    tabs: dict[str, dict[str, Any]] = {}
    for path, val in fields.items():
        parts = path.split(".")
        if len(parts) < 2:
            continue                                   # мета-скаляр верхнего уровня (UpdateCount)
        section = parts[0]
        if len(parts) >= 3:
            group, name = parts[1], ".".join(parts[2:])
        else:
            group, name = "", parts[1]
        if section not in tabs:
            tabs[section] = {"section": section, "title": SECTION_TITLES.get(section, section),
                             "changed": 0, "_groups": {}, "_gorder": []}
            order.append(section)
        t = tabs[section]
        if group not in t["_groups"]:
            t["_groups"][group] = []
            t["_gorder"].append(group)
        changed = path in delta
        t["_groups"][group].append({"name": name, "value": val,
                                     "to": delta.get(path), "changed": changed})
        if changed:
            t["changed"] += 1
    out = []
    for section in order:
        t = tabs[section]
        groups = [{"group": g, "rows": t["_groups"][g]} for g in t["_gorder"]]
        out.append({"section": section, "title": t["title"],
                    "changed": t["changed"], "groups": groups})
    return out
