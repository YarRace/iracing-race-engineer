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


def _tire(get, corner):
    """Температуры кромок колеса: поверхность, а при её отсутствии — каркас.

    Поверхностные каналы дают тысячи значений за сессию, каркасные — два.
    Но на какой-нибудь машине поверхностных может не оказаться вовсе, и
    тогда лучше грубые числа, чем пустая карточка.
    """
    names = channels.TIRE_TEMP[corner]
    vals = [_safe(get, n) for n in names]
    if not any(isinstance(v, (int, float)) and v > 0 for v in vals):
        vals = [_safe(get, n) for n in channels.TIRE_TEMP_CARCASS[corner]]
    return {"tl": vals[0], "tm": vals[1], "tr": vals[2]}


def normalize_frame(get):
    """get(channel_name) -> value. Источник: pyirsdk (ir.__getitem__) или dict в тестах."""
    f = {}
    for k, v in channels.SCALAR.items():
        f[k] = _safe(get, v) if k in OPTIONAL else get(v)
    f["tires"] = {c: _tire(get, c) for c in channels.TIRE_TEMP}
    f["shock_defl"] = {c: get(v) for c, v in channels.SHOCK_DEFL.items()}
    f["track_temp"] = get(channels.WEEKEND_TRACK_TEMP)
    f["air_temp"] = get(channels.WEEKEND_AIR_TEMP)
    return f
