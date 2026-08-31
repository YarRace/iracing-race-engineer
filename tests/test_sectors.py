from ire.collector.race_state import SectorTimer


def test_sector_timer_measures_three_sectors():
    st = SectorTimer([0.0, 0.34, 0.67])
    t = 0.0
    # проезжаем круг: сектор 0 (0..0.34) ~30с, сектор 1 (0.34..0.67) ~33с, сектор 2 ~30с
    for pct in [0.0, 0.1, 0.2, 0.33]:
        st.update(pct, t); t += 10
    for pct in [0.4, 0.5, 0.66]:
        st.update(pct, t); t += 11
    for pct in [0.7, 0.8, 0.99]:
        st.update(pct, t); t += 10
    st.update(0.0, t)  # пересекли финиш → закрылся сектор 2
    secs = st.lap_sectors()
    assert len(secs) == 3
    assert secs == [40.0, 33.0, 30.0]   # вход с0 в t=0→40; с1 40→73; с2 73→103


def test_empty_starts_is_safe():
    st = SectorTimer([])
    st.update(0.5, 1.0)      # не должно падать
    assert st.lap_sectors() == []


# ── живая дельта по секторам ────────────────────────────────────────────────
# Смысл виджета в том, чтобы отставание было видно НА ПРЯМОЙ. Поэтому здесь
# проверяется не «посчиталось ли в конце», а что видно посреди круга.

from ire.collector.race_state import sector_view                    # noqa: E402

LOG = [
    {"lap": 1, "time": 103.0, "sectors": [40.0, 33.0, 30.0]},
    {"lap": 2, "time": 101.5, "sectors": [39.5, 32.5, 29.5]},   # лучший круг
    {"lap": 3, "time": 102.0, "sectors": [39.0, 33.5, 29.5]},   # лучший 1-й сектор
]


def _mid_lap_timer():
    """Первый сектор проехан за 39.0, во втором едем уже 12 секунд."""
    st = SectorTimer([0.0, 0.34, 0.67])
    st.update(0.0, 0.0)
    st.update(0.40, 39.0)                    # закрылся сектор 0
    st.update(0.50, 51.0)                    # едем во втором
    return st


def test_the_delta_is_there_before_the_lap_ends():
    v = sector_view(_mid_lap_timer(), 51.0, LOG)
    assert v["delta"][0] == -0.5, "первый сектор посчитан не сразу"
    assert v["delta"][1] is None, "второй ещё не проехан, а число уже есть"
    assert v["now"] == 1 and v["elapsed"] == 12.0


def test_the_reference_is_the_best_lap_not_the_best_pieces():
    """Отставание к сумме лучших кусков от разных кругов ни к чему не ведёт:
    такого круга никто не ехал. Опора — лучший КРУГ."""
    v = sector_view(_mid_lap_timer(), 51.0, LOG)
    assert v["ref"] == [39.5, 32.5, 29.5], "опорой взяли не лучший круг"
    assert v["best"] == [39.0, 32.5, 29.5], "лучшие сектора по отдельности потерялись"


def test_a_personal_best_sector_is_marked():
    """Как на табло: свой рекорд сектора видно сразу, а не в итогах."""
    v = sector_view(_mid_lap_timer(), 51.0, LOG)
    assert v["record"][0] is True, "39.0 — повтор личного рекорда, не отмечен"
    assert v["record"][1] is False


def test_a_lap_with_a_missing_sector_is_not_used_as_reference():
    """У выезда из боксов первого сектора нет. Взять такой круг за лучший —
    значит показать отставание к кругу, которого не было."""
    log = LOG + [{"lap": 4, "time": 60.0, "sectors": [None, 30.0, 30.0]}]
    v = sector_view(_mid_lap_timer(), 51.0, log)
    assert v["ref"] == [39.5, 32.5, 29.5], "круг с дырой попал в опорные"


def test_no_laps_yet_still_shows_where_you_are():
    """Первый круг сессии: сравнивать не с чем, но номер сектора и время в
    нём — уже польза. Пустой виджет читался бы как поломка."""
    v = sector_view(_mid_lap_timer(), 51.0, [])
    assert v["have_ref"] is False
    assert v["now"] == 1 and v["elapsed"] == 12.0
    assert v["delta"] == [None, None, None]


def test_a_track_without_sectors_gives_nothing_rather_than_zeros():
    assert sector_view(SectorTimer([]), 10.0, LOG) == {}
    assert sector_view(None, 10.0, LOG) == {}
