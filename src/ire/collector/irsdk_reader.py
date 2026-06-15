from config import channels

def normalize_frame(get):
    """get(channel_name) -> value. Источник: pyirsdk (ir.__getitem__) или dict в тестах."""
    f = {k: get(v) for k, v in channels.SCALAR.items()}
    f["tires"] = {
        c: {"tl": get(t[0]), "tm": get(t[1]), "tr": get(t[2])}
        for c, t in channels.TIRE_TEMP.items()
    }
    f["shock_defl"] = {c: get(v) for c, v in channels.SHOCK_DEFL.items()}
    f["track_temp"] = get(channels.WEEKEND_TRACK_TEMP)
    f["air_temp"] = get(channels.WEEKEND_AIR_TEMP)
    return f
