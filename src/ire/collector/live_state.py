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


def strategy_inputs(ir):
    """Считывает стратегические каналы из живого ir для StrategyTracker.update()."""
    S = channels.STRATEGY_SCALAR
    wear = {
        c: {"wl": ir[t[0]], "wm": ir[t[1]], "wr": ir[t[2]]}
        for c, t in channels.TIRE_WEAR.items()
    }
    return {
        "lap": ir[S["lap"]], "t": ir[S["t"]], "fuel": ir[S["fuel"]],
        "laps_remain": ir[S["laps_remain"]], "time_remain": ir[S["time_remain"]],
        "tire_wear": wear,
    }


def fuel_capacity(ir, default=89.0):
    """Ёмкость бака из DriverInfo (DriverCarFuelMaxLtr), с запасным значением."""
    di = ir["DriverInfo"] or {}
    return di.get(channels.DRIVER_FUEL_MAX, default)


def damage_status(ir):
    """Состояние повреждений из SDK. iRacing даёт только время ремонта (сек),
    не карту по зонам. damaged=True, если требуется обязательный/опц. ремонт."""
    D = channels.DAMAGE_SCALAR
    repair = ir[D["repair_sec"]] or 0.0
    opt = ir[D["opt_repair_sec"]] or 0.0
    return {
        "repair_sec": round(repair, 1),
        "opt_repair_sec": round(opt, 1),
        "fast_repair_available": int(ir[D["fast_repair_available"]] or 0),
        "fast_repair_used": int(ir[D["fast_repair_used"]] or 0),
        "incidents": int(ir[D["incidents"]] or 0),
        "damaged": (repair + opt) > 0,
    }
