"""Инструмент перепроверки порогов Tyre Tool.

Настоящих .ibt в репозитории нет и на чужой машине не будет — они лежат в
Documents\\iRacing. Поэтому здесь проверяется не «сойдутся ли числа с моей
телеметрией» (такой тест был бы вечно жёлтым у покупателя), а то, что
ломается молча: арифметика процентилей и — главное — что инструмент берёт
соглашение о кромках из рабочего кода, а не переписывает его у себя.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tools import measure_tyres as MT                            # noqa: E402


def test_percentiles_are_computed_the_ordinary_way():
    v = list(range(1, 101))
    assert MT._pct(v, 0.5) == 50
    assert MT._pct(v, 0.05) == 5
    assert MT._pct(v, 0.95) == 95


def test_an_empty_set_does_not_crash_the_table():
    """Машина без пригодных сессий — обычное дело, а не повод падать."""
    assert "нет данных" in MT._row("никого", [])


def test_the_tool_does_not_invent_its_own_idea_of_which_edge_is_inner():
    """Соглашение о кромках уже путали однажды, и совет по развалу выходил
    обратным. Инструмент, который держит собственную копию соглашения,
    разъедется с рабочим кодом — и будет уверенно мерить не то.
    """
    src = (ROOT / "tools" / "measure_tyres.py").read_text(encoding="utf-8")
    assert "from ire.metrics.tire import edges" in src, "своё понятие кромки"
    assert "from config import channels" in src, "имена каналов собраны строкой"
    # Ни одного самодельного имени канала: только через channels.
    assert 'tempL"' not in src and "tempCL" not in src


def test_the_thresholds_come_from_the_modules_not_from_a_copy():
    """Иначе таблица «как часто срабатывают пороги» однажды начнёт показывать
    частоты для чисел, которых в программе уже нет."""
    src = (ROOT / "tools" / "measure_tyres.py").read_text(encoding="utf-8")
    assert "from ire.metrics.tire import CAMBER_MUCH, CAMBER_NOISE" in src
    assert "from ire.metrics.tyres import CROWN_BAND" in src


def test_a_missing_folder_explains_itself_instead_of_a_traceback(capsys, monkeypatch):
    """Запускать это будет человек, а не программа. Трассировка стека ему
    ничего не скажет о том, что надо включить запись телеметрии."""
    monkeypatch.setattr(sys, "argv", ["measure_tyres.py", "--dir", "Z:\\нет-такой"])
    assert MT.main() == 1
    out = capsys.readouterr().out
    assert "Папки нет" in out and "telemetry" in out
