"""Что видно, когда связь пропала — с симом или с инженером.

Это худший вид поломки из возможных: СТАРЫЕ ДАННЫЕ, НЕОТЛИЧИМЫЕ ОТ ЖИВЫХ.
Человек закрывает сим, смотрит на оверлей и видит 54 литра, которых нет
уже минуту, и разрывы до соперников, которых уже нет на трассе. Пустая
карточка честнее старой: по ней хотя бы понятно, что смотреть не на что.

Два разрыва, и они разные:
  • сим закрыли, инженер жив — чистить обязан инженер (`run.py`);
  • инженер упал, оверлей жив — заметить обязан оверлей (`store`).
"""
import time

import pytest

from overlay.store import Store


class _Client:
    """Подставной HTTP: отвечает, пока `alive`, потом рвётся."""

    def __init__(self):
        self.alive = True

    def get(self, url):
        if not self.alive:
            raise OSError("engineer is gone")
        ep = url.rsplit("/", 1)[-1]
        return _Resp({"fuel": 54.6} if ep != "standings" else [{"pos": 1}])


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


@pytest.fixture
def store():
    s = Store()
    s._client = _Client()
    return s


def _poll(store, times=1):
    """Один проход того же цикла, что крутится в фоне."""
    for _ in range(times):
        store._run = True
        store._active = {"race", "standings"}
        # вызываем тело цикла один раз, без потока
        eps = {"race", "standings", "live"}
        ok = False
        for ep in eps:
            try:
                store._d[ep] = store._client.get(f"{store.base}/api/{ep}").json()
                ok = True
            except Exception:
                pass
        store.ok = ok
        if ok:
            store._ok_at = time.monotonic()


def test_while_the_engineer_answers_the_data_flows(store):
    _poll(store)
    assert store.get("race") == {"fuel": 54.6}
    assert store.get("standings") == [{"pos": 1}]


def test_when_the_engineer_goes_quiet_the_data_goes_empty(store, monkeypatch):
    _poll(store)
    assert store.get("race"), "сначала данные должны быть"

    store._client.alive = False
    # Проматываем время: три секунды молчания — это шестьдесят пропущенных
    # попыток подряд, связи точно нет.
    store._ok_at = time.monotonic() - (Store.STALE_AFTER + 0.5)
    assert store.get("race") == {}, "показывает вчерашние числа как живые"
    assert store.get("standings") == [], "таблица тоже"


def test_a_short_hiccup_does_not_blank_the_screen(store):
    """Один потерянный ответ — не повод гасить экран посреди поворота."""
    _poll(store)
    store._ok_at = time.monotonic() - 0.2
    assert store.get("race") == {"fuel": 54.6}


def test_before_the_first_answer_there_is_nothing_to_show(store):
    assert store.get("race") == {}
    assert store.get("standings") == []


def test_the_engineer_clears_everything_when_the_sim_is_gone():
    """Раньше пропадал только `live`, а таблица, разрывы, топливо и шины
    оставались — и выглядели живыми."""
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[1].joinpath("run.py").read_text(
        encoding="utf-8")
    i = src.index("if not _connected(ir):")
    block = src[i:i + 1200]
    for key in ("race", "standings", "relative", "strategy", "wear", "tyres"):
        assert f'"{key}"' in block, f"{key} остаётся жить после ухода сима"
    # Одно сообщение, а не на каждый круг ожидания.
    assert "stale_cleared" in block
