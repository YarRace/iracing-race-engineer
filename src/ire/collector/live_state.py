"""Адаптер живого pyirsdk → нормализованный кадр + статус трассы.

Решает нюанс контракта: скалярные каналы читаются как ir[name], но темп. трассы и
воздуха лежат в YAML-секции WeekendInfo строками вида "39.82 C" — их надо распарсить.
Чистые функции (_parse_temp, on_track-логика) тестируются без сима через fake-ir.
"""
from config import channels
from ire.collector.irsdk_reader import normalize_frame


def parse_temp(value):
    """'39.82 C' -> 39.82 ; число -> float(число) ; None -> None."""
    if value is None:
        return None
    if isinstance(value, str):
        return float(value.split()[0])
    return float(value)


def make_get(ir):
    """Строит get(channel) поверх живого ir: temp-каналы тянет из WeekendInfo."""
    weekend = ir["WeekendInfo"] or {}

    def get(name):
        if name in (channels.WEEKEND_TRACK_TEMP, channels.WEEKEND_AIR_TEMP):
            return parse_temp(weekend.get(name))
        return ir[name]

    return get


def live_frame(ir):
    """Нормализованный кадр телеметрии из живого ir."""
    return normalize_frame(make_get(ir))


def is_on_track(ir):
    """True, если машина на трассе и не на пит-лейне (граница стинта)."""
    return bool(ir["IsOnTrack"]) and not bool(ir["OnPitRoad"])
