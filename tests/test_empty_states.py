"""Пустая карточка обязана сказать, ЧТО СДЕЛАТЬ или почему она пуста.

Половина дашборда в любой момент пуста — это нормально: рекорды копятся
между сессиями, разбор появляется после стинта, undercut считается только
в гонке. Ненормально, когда заглушка просто повторяет название карточки:
«Strategy vs rivals around you» — и человек стоит перед пустотой, не
понимая, ждать ему или чинить.

Восемь заглушек из двадцати четырёх были именно такими.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "ire" / "dashboard" / "static" / "index.html"

# Слова, которыми заглушка отвечает на «а что мне сделать?» или «почему
# пусто?». Список короткий намеренно: он не должен превращаться в способ
# протащить любую фразу.
TELLS = ("drive", "put in", "enter", "answer", "come into", "appears",
         "appear", "get on", "set a lap", "needs", "coming", "checking",
         "not on", "no ", "once ")


def _placeholders():
    src = HTML.read_text(encoding="utf-8")
    out = {}
    for pat in (r'<div id="([^"]+)" class="empty">([^<]*)<',
                r'<div id="([^"]+)"><div class="empty">([^<]*)<'):
        for key, msg in re.findall(pat, src):
            out.setdefault(key, " ".join(msg.split()))
    return out


PLACEHOLDERS = _placeholders()


def test_there_are_placeholders_to_check():
    assert len(PLACEHOLDERS) > 15, PLACEHOLDERS


@pytest.mark.parametrize("key", sorted(PLACEHOLDERS))
def test_the_empty_card_says_what_to_do(key):
    msg = PLACEHOLDERS[key]
    assert msg, f"{key}: заглушка пустая — карточка выглядит сломанной"
    assert any(t in msg.lower() for t in TELLS), (
        f"{key}: «{msg}» повторяет название карточки, но не говорит, "
        "что сделать и почему пусто")


@pytest.mark.parametrize("key", sorted(PLACEHOLDERS))
def test_the_placeholder_is_a_sentence_not_a_label(key):
    """Подпись-перечисление читается как оглавление, а не как ответ."""
    msg = PLACEHOLDERS[key]
    assert len(msg) >= 18, f"{key}: «{msg}» слишком коротко, чтобы что-то сказать"
