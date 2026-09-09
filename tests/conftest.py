"""Общие для тестов заготовки.

ГЛАВНОЕ ЗДЕСЬ — карта трассы. Мои первые тесты на повороты читали
`data/trackmaps/*.json`, а папка `data/` в .gitignore: на машине Ярослава
эти файлы есть, на чистой копии их нет. Локально всё зелёное, на прогоне
девять падений — ровно тот же сорт ошибки, что уже стоил недели с Pillow.

Ещё четыре теста при этом не падали, а МОЛЧА ПРОПУСКАЛИСЬ: они
параметризованы по списку файлов, и на пустом списке параметров не
остаётся вовсе. Ноль тестов выглядит как ноль проблем.

Поэтому здесь строится трасса, которая едет с кодом: замкнутый контур с
известным числом поворотов, посчитанный, а не срисованный. А настоящие
карты, если они у человека есть, проверяются отдельно и с явным skip,
когда их нет.
"""
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHED_MAPS = sorted((ROOT / "data" / "trackmaps").glob("official_v3_*.json"))


def make_circuit(corners=8, points=260, radius=38.0):
    """Замкнутый контур с заданным числом поворотов.

    Форма — окружность, на которую наложена волна: получается кольцо с
    `corners` выступами, то есть с `corners` поворотами в одну сторону и
    столькими же в другую. Точки идут по ходу движения и несут `pct`, как
    настоящая карта.
    """
    pts = []
    for i in range(points):
        t = 2 * math.pi * i / points
        r = radius * (1.0 + 0.28 * math.sin(corners * t))
        pts.append({"x": 50 + r * math.cos(t),
                    "y": 50 + r * math.sin(t),
                    "pct": i / points})
    return pts


@pytest.fixture
def circuit():
    """Трасса для тестов — своя, а не из папки человека."""
    return make_circuit()


def load_cached_map(path):
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return d.get("points") if isinstance(d, dict) else d


#: Пропуск с ПРИЧИНОЙ. Молчаливый пропуск неотличим от «всё хорошо».
needs_cached_maps = pytest.mark.skipif(
    not CACHED_MAPS,
    reason="нет кэша карт в data/trackmaps — проверка настоящих трасс "
           "работает только там, где человек уже ездил")


@pytest.fixture
def no_network(monkeypatch):
    """Запретить выход наружу на время теста.

    Тесты ходили в интернет: профиль iRacing и три адреса Garage 61 —
    7.3 секунды из 8.8 в одном тесте и результат, зависящий от чужого
    сервера. Прогон, который краснеет из-за чужого downtime, перестают
    читать.

    Заглушка стоит на `urllib`, а не на конкретном сборщике: так её не
    обойдёт новый код, который тоже решит сходить наружу.
    """
    import urllib.request

    def blocked(*a, **kw):
        raise OSError("сеть в тестах запрещена")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", blocked)
    return blocked
