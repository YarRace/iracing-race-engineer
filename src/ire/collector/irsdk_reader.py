from config import channels

# Каналы, которых в сессии может не быть. Координаты машины iRacing
# публикует, но проверить это без живого сима нельзя, а падать из-за
# отсутствующего канала посреди гонки — недопустимо: кадр читается
# шестьдесят раз в секунду.
OPTIONAL = ("lat", "lon")


def _safe(get, name):
    """Значение канала или None. pyirsdk на незнакомое имя отдаёт None сам,
    но контракт «get(name) -> value» этого не обещает, и тесты подают
    словарь, который на незнакомый ключ честно бросает KeyError."""
    try:
        return get(name)
    except Exception:                                    # noqa: BLE001
        return None


def normalize_frame(get):
    """get(channel_name) -> value. Источник: pyirsdk (ir.__getitem__) или dict в тестах."""
    f = {}
    for k, v in channels.SCALAR.items():
        f[k] = _safe(get, v) if k in OPTIONAL else get(v)
    f["tires"] = {
        c: {"tl": get(t[0]), "tm": get(t[1]), "tr": get(t[2])}
        for c, t in channels.TIRE_TEMP.items()
    }
    f["shock_defl"] = {c: get(v) for c, v in channels.SHOCK_DEFL.items()}
    f["track_temp"] = get(channels.WEEKEND_TRACK_TEMP)
    f["air_temp"] = get(channels.WEEKEND_AIR_TEMP)
    return f
