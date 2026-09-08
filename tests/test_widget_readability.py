"""Что видно на экране: обрезанные имена, фиолетовый круг, пустые квадраты.

Три ошибки, найденные ГЛАЗАМИ по витрине, а не тестом. Все три одного
рода: программа считала верно, а показывала не то.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from overlay import widgets as W

ROOT = pathlib.Path(__file__).resolve().parents[1]
_app = QApplication.instance() or QApplication([])


# --- фиолетовый круг -------------------------------------------------------
#
# Фиолетовый в гонках означает ОДНО: быстрейший круг. Таблица красила им
# столбец BEST у всех подряд — признак, существующий затем, чтобы выделить
# одного, не выделял никого.

def test_the_fastest_is_one_per_class():
    rows = [{"best": 91.0, "car_class": "GTP"}, {"best": 92.0, "car_class": "GTP"},
            {"best": 94.0, "car_class": "GT3"}, {"best": 95.0, "car_class": "GT3"}]
    assert W.fastest_laps(rows) == {"GTP": 91.0, "GT3": 94.0}


def test_a_slower_class_still_gets_its_own_purple():
    """В мультиклассе GT3 никогда не побьёт LMP2 по времени круга.

    Общий фиолетовый на всю сетку означал бы «ты не прототип» — а он
    должен означать «быстрейший в своём классе».
    """
    fast = W.fastest_laps([{"best": 88.0, "car_class": "LMP2"},
                           {"best": 99.0, "car_class": "GT3"}])
    assert fast["GT3"] == 99.0, "класс без своего быстрейшего круга"


@pytest.mark.parametrize("bad", [None, 0, -1, "1:31.0", float("nan")])
def test_a_missing_lap_is_not_the_fastest(bad):
    got = W.fastest_laps([{"best": bad, "car_class": "X"},
                          {"best": 95.0, "car_class": "X"}])
    assert got == {"X": 95.0}


def test_no_class_means_everyone_in_one():
    assert W.fastest_laps([{"best": 93.0}, {"best": 91.5}]) == {"": 91.5}


def test_nothing_to_colour_is_not_a_crash():
    assert W.fastest_laps([]) == {}
    assert W.fastest_laps(None) == {}


def test_the_table_asks_who_is_fastest_before_painting():
    """Иначе столбец снова покрасится целиком, и это не увидит ни один тест."""
    src = (ROOT / "overlay" / "widgets.py").read_text(encoding="utf-8")
    body = src[src.index("class StandingsWidget"):]
    body = body[:body.index("\nclass ", 10)]
    assert "fastest_laps(rows)" in body
    assert "dim or self._cb(PURPLE), 10)" not in body, "снова красит всех"


# --- обрезанные имена ------------------------------------------------------
#
# Резали по числу букв: nm[:12]. «Marek Ostrowski» превращался в
# «Marek Ostrowsk» — не в обрезанное имя, а в ДРУГОЕ, и человека по нему в
# таблице не узнать.

def _widget():
    class Cfg:
        def geometry(self, key):
            return None

        def widget_opt(self, key, name, default=None):
            return default

        def set_widget_opt(self, *a):
            pass

        def set_geometry(self, *a):
            pass

        def opacity(self):
            return 1.0

        def edit_mode(self):
            return False

    class Store:
        def get(self, k):
            return {}

    w = W.StandingsWidget(Store(), Cfg())
    w.resize(600, 300)
    return w


def _advance(text):
    """Ширина строки в тех же единицах, в которых её резали."""
    w = _widget()
    px = QPixmap(600, 60)
    p = QPainter(px)
    try:
        p.setFont(w._font_for(None, 11, False))
        return p.fontMetrics().horizontalAdvance(text)
    finally:
        p.end()


def _elide(text, width):
    w = _widget()
    px = QPixmap(600, 60)
    p = QPainter(px)
    try:
        return w.elide(p, text, width, 11)
    finally:
        p.end()


def test_a_name_that_fits_is_left_alone():
    assert _elide("Yuto Shibata", 400) == "Yuto Shibata"


def test_a_long_name_is_cut_with_a_sign_that_it_was_cut():
    got = _elide("Marek Ostrowski-Wilkinson", 60)
    assert got != "Marek Ostrowski-Wilkinson"
    assert got.endswith("…"), f"обрезано молча: {got!r}"


def test_the_cut_is_by_width_not_by_letters():
    """Буква не равна букве: «iiii» и «WWWW» занимают разную ширину."""
    long_name = "Wolfgang Bergqvist-Ostrowski"
    for width in (40, 80, 160, 240):
        got = _elide(long_name, width)
        assert _advance(got) <= width + 1, (width, got, _advance(got))
    # Чем шире колонка, тем больше помещается — иначе это не обрезка
    # по ширине, а обрезка по числу букв под другим именем.
    assert len(_elide(long_name, 240)) > len(_elide(long_name, 60))


def test_no_widget_still_cuts_a_name_by_letter_count():
    """Ровно этот приём и рисовал «Marek Ostrowsk»."""
    src = (ROOT / "overlay" / "widgets.py").read_text(encoding="utf-8")
    import re

    left = re.findall(r"nm\[:\d+", src)
    assert not left, f"осталась обрезка по буквам: {left}"


# --- пустые квадраты вместо значков ---------------------------------------

def test_the_gallery_loads_the_symbol_font():
    """Segoe UI НЕ содержит блок геометрических фигур.

    На машине человека Qt подберёт Segoe UI Symbol сам, а безголовому
    раннеру подбирать не из чего: витрина показывала товар с пустыми
    квадратами вместо значков.
    """
    src = (ROOT / "tools" / "render_widgets.py").read_text(encoding="utf-8")
    assert "seguisym.ttf" in src


def test_the_tyre_widget_says_which_edge_not_which_side():
    """«◀8°» требует сообразить, левое это колесо или правое.

    «inner +8°» отвечает сразу: горячая внутренняя кромка — избыток
    развала. И перестаёт зависеть от символьного шрифта.
    """
    src = (ROOT / "overlay" / "widgets.py").read_text(encoding="utf-8")
    body = src[src.index("class TireTempsWidget"):]
    body = body[:body.index("\nclass ", 10)]
    # Комментарии на экран не попадают — а объяснение, почему
    # треугольников больше нет, само их содержит.
    drawn = "".join(ln.split("#")[0] for ln in body.splitlines())
    assert "◀" not in drawn and "▶" not in drawn
    assert '"inner"' in body and '"outer"' in body


@pytest.mark.parametrize("corner,inner_is", [("LF", "tr"), ("LR", "tr"),
                                             ("RF", "tl"), ("RR", "tl")])
def test_the_overlay_edge_convention_matches_the_metrics_one(corner, inner_is):
    """Соглашение о кромках уже путали один раз, и совет по развалу выходил
    ровно обратным. Оно обязано быть одно на всю программу."""
    from ire.metrics.tire import edges

    tl, tr = 90.0, 80.0
    assert W._edges(corner, tl, tr) == edges(corner, tl, tr)
    assert W._edges(corner, tl, tr)[0] == (tr if inner_is == "tr" else tl)


# --- витрина: демо-данные обязаны быть возможными -------------------------
#
# Снимки на сайте — это шкаф с товаром. Три вещи в нём показывали то, чего
# в природе не бывает, и заметить это можно было только глазами.

def test_the_demo_car_is_physically_possible():
    """Отрицательный развал стоит на ОБЕИХ сторонах и греет внутреннюю кромку.

    Градиент tl→tr был одинаковым у всех четырёх колёс, а tl/tr — это
    стороны в координатах МАШИНЫ. Выходило, что слева греется внутренняя
    кромка, а справа внешняя: такой машины не бывает.
    """
    from ire.metrics.tire import edges
    from overlay.demo import DemoFeed

    tires = DemoFeed().get("live")["tires"]
    for c in ("LF", "RF", "LR", "RR"):
        inner, outer = edges(c, tires[c]["tl"], tires[c]["tr"])
        assert inner > outer, f"{c}: внешняя кромка горячее внутренней"


def test_the_demo_table_fills_every_column_it_shows():
    """SR и GAP стояли пустыми: витрина показывала таблицу с дырами."""
    from overlay.demo import DemoFeed

    rows = DemoFeed().get("standings")
    assert rows
    for r in rows:
        for field in ("pos", "number", "lic", "sr", "gap_txt", "best", "last",
                      "irating", "car_class"):
            assert r.get(field) not in (None, ""), f"P{r.get('pos')}: нет {field}"


def test_the_demo_gap_is_to_the_leader_not_to_me():
    """У боевого сборщика разрыв до лидера и всегда ≥ 0.

    Демо считало его от игрока, и у тех, кто впереди, выходило
    отрицательное число — `_add_gaps` печатал «—».
    """
    from overlay.demo import DemoFeed

    rows = DemoFeed().get("standings")
    assert rows[0]["gap_txt"] == "leader"
    assert all(r["gap_txt"].startswith("+") for r in rows[1:]), \
        [r["gap_txt"] for r in rows]


def test_only_one_demo_row_holds_the_fastest_lap():
    from overlay.demo import DemoFeed

    rows = DemoFeed().get("standings")
    fast = W.fastest_laps(rows)
    winners = [r for r in rows if r["best"] <= fast.get(r.get("car_class") or "", 0)]
    assert len(winners) == 1, [r["name"] for r in winners]


def test_the_two_tyre_cards_describe_the_same_car():
    """Tire temps и Tyre Tool стояли на разных числах.

    В живой телеметрии демо было 90–105 °C, а в Tyre Tool — 60 °C, снятые
    с настоящей сессии на другой трассе. В одном шкафу с товаром стояли две
    разные машины, и вердикт «too much camber» относился к колёсам, которых
    на соседней карточке нет.
    """
    from overlay.demo import DemoFeed

    f = DemoFeed()
    live = f.get("live")["tires"]
    tool = f.get("tyres")
    assert tool["ok"]
    for c in ("LF", "RF", "LR", "RR"):
        assert abs(tool["corners"][c]["middle"] - live[c]["tm"]) < 0.05, c


def test_the_demo_shows_the_tool_telling_wheels_apart():
    """Одинаковый перекос на всех четырёх — и Tyre Tool ругается всегда.

    Ради того он и нужен, чтобы отличать колесо, где развал работает, от
    колеса, где его перебор. Витрина обязана это показывать.
    """
    from overlay.demo import DemoFeed

    corners = DemoFeed().get("tyres")["corners"]
    verdicts = {c: corners[c]["camber"] for c in ("LF", "RF", "LR", "RR")}
    assert len(set(verdicts.values())) > 1, verdicts
    assert "working" in verdicts.values()
    assert "too_much" in verdicts.values()


def test_no_tyre_has_more_tread_than_a_new_one():
    """Карточка печатала «105%»: протектора больше, чем у новой шины, нет.

    Ошибка была видна ровно там, где на неё смотрят, — и ровно поэтому её
    никто не искал.
    """
    from overlay.demo import DemoFeed

    for corner, zones in DemoFeed().get("wear").items():
        for k, v in zones.items():
            assert 0.0 <= v <= 1.0, f"{corner}.{k} = {v}"
