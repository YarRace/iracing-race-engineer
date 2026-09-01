"""Статические проверки скрипта дашборда.

Дашборд — полторы тысячи строк JS в одном файле, и юнит-тестов у него нет:
это разметка и отрисовка, их проверяют глазами. Но один класс ошибок глазами
не ловится вообще, и он уже стоил работающей половины вкладки Solo.

30.08.2026: в файле оказались ДВЕ функции `renderProgress` — старая без
аргументов (график кругов сессии) и новая на два аргумента (карточка Progress
на вкладке Records, писавшая в тот же элемент). В JavaScript побеждает
последнее объявление, поэтому вызов `renderProgress()` без аргументов уходил
в новую версию, где `combos` — undefined, и падал на `combos.map`. Падение
внутри `tickRace` обрывало ВЕСЬ тик: позиция и разрывы, круги и сектора,
итоги сессии, полоса оборотов, погода, таблица и ERS оставались пустыми
каждый кадр. В консоли — молчаливая ошибка в промисе, на экране — «Appears
once on track» на живых данных.

Отсюда тест: имена функций верхнего уровня в этом файле обязаны быть
уникальными. Пустой раздел на экране не выглядит как ошибка, поэтому искать
такое приходится не там, где оно проявилось.
"""
import collections
import pathlib
import re

HTML = (pathlib.Path(__file__).resolve().parents[1] / "src" / "ire" /
        "dashboard" / "static" / "index.html")

# `function имя(` в начале строки — объявления верхнего уровня. Вложенные
# и стрелочные не ловим намеренно: перекрытие опасно именно у глобальных.
DECL = re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.M)


def test_no_duplicate_function_names():
    names = DECL.findall(HTML.read_text(encoding="utf-8"))
    dupes = {n: c for n, c in collections.Counter(names).items() if c > 1}
    assert not dupes, (
        f"одноимённые функции перекрывают друг друга: {dupes}. "
        f"Побеждает последняя, и вызовы старой сигнатуры падают молча")


BARE_CALL = re.compile(r"(?<![.\w])(render[A-Za-z]*)\(")


def test_render_calls_inside_ticks_are_guarded():
    """Один сломанный рендер не должен уносить весь тик.

    Тик — это два десятка `render*` подряд. Пока они идут голым списком,
    исключение в любом из них обрывает все следующие: падение renderProgress
    оставляло пустыми семь карточек, а на экране было только «Appears once
    on track» поверх живых данных.

    Проверять «есть ли где-то try» бесполезно — он и так стоит вокруг fetch
    в каждом тике, и тест проходил бы, ничего не гарантируя. Проверяем ровно
    нужное: незавёрнутых вызовов render* внутри тика не осталось.
    """
    src = HTML.read_text(encoding="utf-8")
    assert "const safe = (f, ...a) =>" in src, "обёртки safe() нет вовсе"
    for name in ("tickRace", "tickLive", "tickRelative"):
        i = src.index(f"async function {name}(")
        body = src[i:src.index("\n}\n", i)]
        # Завёрнутый вызов выглядит как «safe(renderX, ...)» — имя идёт
        # аргументом, и скобки сразу за ним НЕТ. Значит всё, что нашлось
        # этим шаблоном, вызвано напрямую.
        bare = sorted({m.group(1) for m in BARE_CALL.finditer(body)})
        assert not bare, f"{name}: незащищённые вызовы {bare}"


def test_the_sector_card_accounts_for_every_lap_of_the_run():
    """Круги другой длины набора (заезд, начатый до правки хранилища и
    продолженный после) считались в `dropped`, но на экран не выводились:
    человек проехал 24, видел «22 clean laps · 1 lap left out» — и один круг
    пропадал без объяснения. Ровно та беда, ради которой поле и заводили."""
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "src" / "ire" / "dashboard" / "static" / "index.html"
           ).read_text(encoding="utf-8")
    assert "r.dropped" in src, "поле dropped не доходит до карточки"
    assert "${drop}" in src, "строка про dropped собрана, но не вставлена"
