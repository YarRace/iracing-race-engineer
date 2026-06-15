from ire.collector.live_state import parse_temp, make_get, is_on_track
from config import channels


def test_parse_temp_handles_string_and_number():
    assert parse_temp("39.82 C") == 39.82
    assert parse_temp(25.0) == 25.0
    assert parse_temp(None) is None


class _FakeIR:
    """Имитация pyirsdk: WeekendInfo как dict, скаляры по ключу."""
    def __init__(self, scalars, weekend):
        self._s = scalars
        self._s["WeekendInfo"] = weekend
    def __getitem__(self, k):
        return self._s[k]


def test_make_get_reads_temps_from_weekendinfo():
    ir = _FakeIR(
        {"Speed": 60.0},
        {channels.WEEKEND_TRACK_TEMP: "39.82 C", channels.WEEKEND_AIR_TEMP: "25.57 C"},
    )
    get = make_get(ir)
    assert get("Speed") == 60.0
    assert get(channels.WEEKEND_TRACK_TEMP) == 39.82
    assert get(channels.WEEKEND_AIR_TEMP) == 25.57


def test_is_on_track_excludes_pitlane():
    on = _FakeIR({"IsOnTrack": True, "OnPitRoad": False}, {})
    pit = _FakeIR({"IsOnTrack": True, "OnPitRoad": True}, {})
    garage = _FakeIR({"IsOnTrack": False, "OnPitRoad": False}, {})
    assert is_on_track(on) is True
    assert is_on_track(pit) is False
    assert is_on_track(garage) is False
