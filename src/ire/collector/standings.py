"""Таблица заездов (standings/timing tower): данные всех машин из SDK.

Объединяет статичную инфу пилотов (DriverInfo.Drivers: имя, номер, iRating,
лицензия, класс) с live-массивами по индексу машины (позиция, разрыв, круги).
"""


def _arr(ir, name):
    v = ir[name]
    return v if v else []


def build_standings(ir):
    """Список машин, отсортированный по позиции. Пейс-кар и зрители исключены."""
    di = ir["DriverInfo"] or {}
    drivers = di.get("Drivers") or []
    my_idx = di.get("DriverCarIdx")
    pos = _arr(ir, "CarIdxPosition")
    f2 = _arr(ir, "CarIdxF2Time")
    last = _arr(ir, "CarIdxLastLapTime")
    best = _arr(ir, "CarIdxBestLapTime")
    lap = _arr(ir, "CarIdxLap")
    pit = _arr(ir, "CarIdxOnPitRoad")

    def at(a, i, default=None):
        return a[i] if 0 <= i < len(a) else default

    rows = []
    for d in drivers:
        idx = d.get("CarIdx")
        if idx is None:
            continue
        if d.get("CarIsPaceCar") or d.get("IsSpectator"):
            continue
        p = at(pos, idx, 0) or 0
        if p <= 0:                                   # ещё нет позиции (не стартовал)
            continue
        lt = at(last, idx)
        bt = at(best, idx)
        rows.append({
            "pos": p,
            "number": d.get("CarNumber"),
            "name": d.get("UserName"),
            "irating": d.get("IRating"),
            "license": d.get("LicString"),
            "car": d.get("CarScreenNameShort"),
            "class_color": d.get("CarClassColor"),
            "gap": round(at(f2, idx, 0.0), 3),       # до лидера, сек
            "last": round(lt, 3) if isinstance(lt, (int, float)) and lt > 0 else None,
            "best": round(bt, 3) if isinstance(bt, (int, float)) and bt > 0 else None,
            "lap": at(lap, idx),
            "on_pit": bool(at(pit, idx, False)),
            "is_player": idx == my_idx,
        })
    rows.sort(key=lambda r: r["pos"])
    return rows
