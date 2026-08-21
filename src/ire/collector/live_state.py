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
    """Нормализованный кадр телеметрии из живого ir + мои температуры/баланс тормозов.
    Oil/Water/BrakeBias — каналы МОЕЙ машины (по чужим iRacing их не отдаёт)."""
    f = normalize_frame(make_get(ir))
    f["oil_temp"] = ir["OilTemp"]                      # °C, моя машина
    f["water_temp"] = ir["WaterTemp"]                  # °C
    f["brake_bias"] = ir["dcBrakeBias"]                # баланс тормозов, % вперёд
    return f


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


def infer_car_class(class_short, car_path, car_name):
    """Класс машины (GTP/GT3/GT4/LMP/Formula) для фильтров в рекордах.

    Сначала берём CarClassShortName из SDK; в практике/тесте он часто пуст —
    тогда выводим класс из пути/имени машины по ключевым словам."""
    if class_short:
        return class_short
    s = f"{car_path or ''} {car_name or ''}".lower()
    if "gtp" in s:
        return "GTP"
    if "gt3" in s:
        return "GT3"
    if "gt4" in s:
        return "GT4"
    if any(k in s for k in ("lmp", "oreca", "hpd", "prototype")):
        return "LMP"
    if any(k in s for k in ("formula", "indycar", "superformula", "dallara f", "skip barber")):
        return "Formula"
    return None


# цвета классов (int RGB) — схема IMSA: GTP жёлто-золотой, LMP2 синий, GT3 алый, GT4 зелёный
CLASS_COLOR_GTP = 0xF1C40F
CLASS_COLOR_LMP = 0x3EA6FF
CLASS_COLOR_GT3 = 0xE74C3C
CLASS_COLOR_GT4 = 0x2ECC71
CLASS_COLOR_FORMULA = 0x9B59B6


def class_color(class_short, car_path=None, car_name=None, fallback=None):
    """Цвет класса (int) по схеме: GTP=золотисто-жёлтый, LMP2=синий, GT3=алый, GT4=зелёный.
    Устойчив к вариациям названий (GTD=GT3, hypercar/LMDh=GTP, ORECA=LMP2)."""
    s = f"{class_short or ''} {car_path or ''} {car_name or ''}".upper()
    if "GTP" in s or "HYPERCAR" in s or "LMDH" in s or "LMH" in s:
        return CLASS_COLOR_GTP
    if "GT4" in s:
        return CLASS_COLOR_GT4
    if "GT3" in s or "GTD" in s:
        return CLASS_COLOR_GT3
    if "LMP" in s or "ORECA" in s or "PROTOTYPE" in s:
        return CLASS_COLOR_LMP
    if "FORMULA" in s or "INDYCAR" in s or "SUPERFORMULA" in s:
        return CLASS_COLOR_FORMULA
    return fallback


def session_identity(ir):
    """Кто/где едет: трасса (стабильный id + отображаемое имя + конфиг), машина,
    класс, тип сессии. Для привязки сохранённых кругов к трассе/машине (рекорды).
    Трасса — из WeekendInfo; машина/класс — из DriverInfo.Drivers[DriverCarIdx];
    тип сессии — из SessionInfo текущей сессии, иначе EventType."""
    wk = ir["WeekendInfo"] or {}
    di = ir["DriverInfo"] or {}
    drivers = di.get("Drivers") or []
    my = di.get(channels.DRIVER_CAR_IDX)
    car = car_path = car_class = None
    if my is not None and 0 <= my < len(drivers):
        d = drivers[my] or {}
        car = d.get("CarScreenName")
        car_path = d.get("CarPath")
        car_class = infer_car_class(d.get("CarClassShortName"), car_path, car)
    session_type = wk.get("EventType")
    try:
        sessions = (ir["SessionInfo"] or {}).get("Sessions") or []
        sn = ir["SessionNum"]
        if sn is not None and 0 <= sn < len(sessions):
            session_type = sessions[sn].get("SessionType") or session_type
    except Exception:
        pass
    return {
        "track": wk.get("TrackName"),
        "track_display": wk.get("TrackDisplayName"),
        "config": wk.get("TrackConfigName"),
        "car": car,
        "car_path": car_path,
        "car_class": car_class,
        "session_type": session_type,
    }


def tire_wear_by_corner(ir):
    """Мин. остаток протектора по каждому углу (0..1): худшая из 3 точек L/M/R."""
    out = {}
    for c, t in channels.TIRE_WEAR.items():
        vals = [ir[ch] for ch in t if ir[ch] is not None]
        out[c] = round(min(vals), 3) if vals else None
    return out


def session_info(ir):
    """Инфо о сессии: тип, всего/осталось кругов, время до конца, время суток."""
    ident = session_identity(ir)
    NO = 32767
    lr = ir["SessionLapsRemain"]
    tr = ir["SessionTimeRemain"]
    laps_total = None
    try:
        sessions = (ir["SessionInfo"] or {}).get("Sessions") or []
        sn = ir["SessionNum"]
        if sn is not None and 0 <= sn < len(sessions):
            sl = sessions[sn].get("SessionLaps")
            laps_total = sl if isinstance(sl, int) else None
    except Exception:
        pass
    return {
        "session_type": ident["session_type"],
        "track_display": ident["track_display"],
        "laps_remain": lr if (lr is not None and 0 <= lr < NO) else None,
        "laps_total": laps_total,
        "time_remain": tr if (tr is not None and 0 < tr < 1e6) else None,
        "time_of_day": ir["SessionTimeOfDay"],
    }


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
        "team_incidents": int(ir[D["team_incidents"]] or 0),   # инциденты команды (эндуранс)
        "damaged": (repair + opt) > 0,
    }
