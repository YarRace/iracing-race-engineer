"""Настройки виджетов против того, как они на самом деле читаются.

Сорок семь виджетов, у каждого до двадцати настроек — руками это не
проверял никто ни разу. Ищем расхождения, которые видно только если
открыть настройки КОНКРЕТНОГО виджета и сравнить с его поведением:

  • разные умолчания в панели и в коде — ползунок показывает 12, а виджет
    ведёт себя как 8, пока ползунок не тронули;
  • мёртвая настройка: объявлена, не читается — крутится и ничего не
    меняет;
  • невидимая: читается, а в панели её нет — поменять нельзя (так и было
    у Laptime spread с числом кругов);
  • два контрола на один ключ;
  • умолчание вне диапазона ползунка — он никогда его не покажет;
  • две одинаковые подписи в одном виджете.
"""
import ast
import collections
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "overlay" / "widgets.py"

# (метод -> позиция имени, позиция умолчания) среди аргументов после self.
DECL = {"opt_slider": (2, 5), "opt_number": (2, 5),
        "opt_check": (2, 3), "opt_choice": (2, None), "opt_color": (2, 3)}

# Настройки, общие для всех виджетов: их объявляет общий диалог
# (`overlay/settings_dialog.py`), а не сам виджет.
COMMON = {"bg_alpha", "bg_bright", "radius", "text_shadow", "font_style",
          "font_size", "font_family", "colour_blind", "colorblind", "cb",
          "value_color", "opacity", "scale", "hidden", "order", "line_color"}


def _const(n):
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_const(x) for x in n.elts]
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
        v = _const(n.operand)
        return -v if isinstance(v, (int, float)) else None
    return "<expr>"


def _scan(cls):
    reads, decls, dups, labels, ranges = {}, {}, [], collections.Counter(), []
    for node in ast.walk(cls):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)):
            continue
        m, a = node.func.attr, node.args
        if m == "_opt" and a:
            name = _const(a[0])
            if isinstance(name, str):
                reads.setdefault(name, set()).add(
                    repr(_const(a[1]) if len(a) > 1 else None))
        elif m in DECL and len(a) > DECL[m][0]:
            npos, dpos = DECL[m]
            name = _const(a[npos])
            if not isinstance(name, str):
                continue
            if name in decls:
                dups.append(name)
            if dpos is not None and len(a) > dpos:
                decls[name] = repr(_const(a[dpos]))
            else:
                # opt_choice: умолчания в объявлении нет, зато есть список
                # вариантов — по нему проверяем, что умолчание из кода
                # вообще предлагается человеку.
                opts = _const(a[3]) if len(a) > 3 else None
                decls[name] = ("CHOICE:" + repr(
                    [o[0] for o in opts if isinstance(o, list) and o]
                    if isinstance(opts, list) else []))
            labels[_const(a[1])] += 1
            if m in ("opt_slider", "opt_number") and len(a) >= 6:
                ranges.append((_const(a[1]), _const(a[3]), _const(a[4]),
                               _const(a[5])))
    return reads, decls, dups, labels, ranges


CLASSES = [n for n in ast.parse(SRC.read_text(encoding="utf-8")).body
           if isinstance(n, ast.ClassDef)]


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.name)
def test_the_panel_and_the_code_agree_on_the_default(cls):
    """Ползунок показывает одно, виджет ведёт себя как другое."""
    reads, decls, _, _, _ = _scan(cls)
    for name, shown in decls.items():
        if name not in reads:
            continue
        got = reads[name]
        if shown.startswith("CHOICE:"):
            # Умолчание кода обязано быть среди вариантов, иначе выпадашка
            # открывается не на том, что виджет сейчас делает.
            offered = ast.literal_eval(shown[len("CHOICE:"):])
            for d in got:
                val = ast.literal_eval(d)
                if val is not None and offered:
                    assert val in offered, (
                        f"{name}: код по умолчанию {val!r}, "
                        f"а в списке только {offered}")
            continue
        assert len(got) == 1, f"{name}: draw читает с разными умолчаниями {got}"
        assert shown in got, f"{name}: в панели {shown}, в коде {sorted(got)[0]}"


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.name)
def test_no_setting_is_dead(cls):
    """Объявлена и не читается — крутится и ничего не меняет."""
    reads, decls, _, _, _ = _scan(cls)
    dead = [n for n in decls if n not in reads]
    assert not dead, f"{cls.name}: {dead}"


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.name)
def test_no_setting_is_unreachable(cls):
    """Читается, а в панели её нет — поменять нельзя.

    Ровно так было у Laptime spread: он читал число кругов, а ползунка не
    было ни одного.
    """
    reads, decls, _, _, _ = _scan(cls)
    hidden = [n for n in reads
              if n not in decls and n not in COMMON and n != "<expr>"]
    assert not hidden, f"{cls.name}: {hidden}"


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.name)
def test_one_control_per_key(cls):
    _, _, dups, _, _ = _scan(cls)
    assert not dups, f"{cls.name}: два контрола на {dups}"


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.name)
def test_the_slider_can_reach_its_own_default(cls):
    _, _, _, _, ranges = _scan(cls)
    for title, lo, hi, d in ranges:
        if all(isinstance(x, (int, float)) for x in (lo, hi, d)):
            assert lo <= d <= hi, f"{cls.name} «{title}»: {d} вне {lo}..{hi}"


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.name)
def test_no_two_settings_share_a_label(cls):
    _, _, _, labels, _ = _scan(cls)
    same = [t for t, n in labels.items() if n > 1 and isinstance(t, str)]
    assert not same, f"{cls.name}: {same}"
