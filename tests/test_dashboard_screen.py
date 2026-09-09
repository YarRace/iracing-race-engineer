"""Что человек ВИДИТ на дашборде: нет ли там служебного мусора.

«undefined», «NaN», «null», «[object Object]» на экране означают одно и то
же: поле не пришло, а страница напечатала внутреннее имя вместо прочерка.
Отсутствие данных при этом выглядит как поломка программы, и человек идёт
искать, что сломалось, вместо того чтобы проехать круг.

Разовая проверка нашла 36 таких мест сразу: «stint ~undefined laps»,
«undefined L», «NaN% износа» на всех четырёх колёсах и «Time of day
NaN:NaN». Ни одно из них не ловил ни один тест — их видно только глазами,
поэтому смотрим машиной.

КАК. Одна загрузка страницы в безголовом браузере и разбор всего DOM:
скрытые вкладки лежат в нём тоже, поэтому шести заходов не нужно. Скрипты
из разбора выбрасываются — там «undefined» и «null» стоят по делу.

Нет браузера — пропуск с причиной. Он есть на раннере GitHub и обычно есть
у человека; молчаливого пропуска здесь быть не должно, иначе ноль тестов
снова сойдёт за ноль проблем.
"""
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import render_dashboard as RD                                    # noqa: E402

CHROME = RD.find_chrome()

# `null` намеренно НЕ ищем в тексте: слово встречается в английских
# подписях («null hypothesis» и подобных) и в наших пояснениях. Три
# оставшихся однозначны.
GARBAGE = re.compile(r"\bundefined\b|\bNaN\b|\[object Object\]")

needs_chrome = pytest.mark.skipif(
    not CHROME, reason="нет Chrome — страницу нечем отрисовать")


def _dom():
    """DOM живой страницы с демо-данными. Одна загрузка, все вкладки."""
    import uvicorn

    from ire.dashboard.server import STATE, app

    tmpdir = tempfile.mkdtemp(prefix="ire-screen-")
    old_db = os.environ.get("IRE_DB_PATH")
    os.environ["IRE_DB_PATH"] = os.path.join(tmpdir, "screen.db")
    feed = RD.seed(STATE)
    port = RD.free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    stop = threading.Event()
    threading.Thread(target=RD.pump, args=(STATE, feed, stop),
                     daemon=True).start()
    try:
        for _ in range(80):
            try:
                with socket.create_connection(("127.0.0.1", port), 0.2):
                    break
            except OSError:
                time.sleep(0.1)
        r = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu",
             "--virtual-time-budget=6000", "--dump-dom",
             f"http://127.0.0.1:{port}/"],
            capture_output=True, timeout=180)
        return r.stdout.decode("utf-8", errors="replace")
    finally:
        stop.set()
        server.should_exit = True
        time.sleep(0.3)
        if old_db is None:
            os.environ.pop("IRE_DB_PATH", None)
        else:
            os.environ["IRE_DB_PATH"] = old_db


@pytest.fixture(scope="module")
def screen():
    dom = _dom()
    # Внутри <script> «undefined» — это код, а не то, что видит человек.
    body = re.sub(r"(?is)<script.*?</script>", " ", dom)
    return re.sub(r"(?s)<[^>]+>", " ", body)


@needs_chrome
def test_the_page_shows_no_internal_words(screen):
    hits = []
    for m in GARBAGE.finditer(screen):
        a, b = max(0, m.start() - 60), m.end() + 60
        hits.append(" ".join(screen[a:b].split()))
    assert not hits, "служебные слова на экране:\n  " + "\n  ".join(hits[:10])


@needs_chrome
def test_the_page_actually_rendered(screen):
    """Иначе пустая страница пройдёт проверку выше не глядя."""
    assert "Race Engineer" in screen
    for word in ("Gauges", "Tire wear", "Fuel", "Standings"):
        assert word.lower() in screen.lower(), f"нет карточки {word}"


@needs_chrome
def test_the_wear_card_shows_numbers_not_dashes(screen):
    """NaN% чинили один раз и починили только одну из двух копий.

    Проверяем не отсутствие NaN (это выше), а наличие процентов: карточка,
    молча показывающая четыре прочерка, выглядит исправной.
    """
    i = screen.index("Tire wear")
    window = screen[i:i + 400]
    assert re.search(r"\d+%", window), window[:200]
