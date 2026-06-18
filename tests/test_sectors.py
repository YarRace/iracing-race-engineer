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
