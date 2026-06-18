from ire.collector.race_state import decode_flags, decode_warnings


def test_decode_flags_picks_active():
    assert decode_flags(0) == []
    # зелёный (0x4) + синий (0x20)
    keys = [f["key"] for f in decode_flags(0x4 | 0x20)]
    assert "green" in keys and "blue" in keys
    # клетчатый
    assert any(f["key"] == "checkered" for f in decode_flags(0x1))


def test_decode_warnings_picks_active():
    assert decode_warnings(0) == []
    # перегрев воды (0x1) + отсечка (0x20)
    keys = [w["key"] for w in decode_warnings(0x1 | 0x20)]
    assert "water" in keys and "rev_limiter" in keys
    # пит-лимитер
    assert any(w["key"] == "pit_limiter" for w in decode_warnings(0x10))
