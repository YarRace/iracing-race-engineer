"""Таблица заездов (standings/timing tower): данные всех машин из SDK.

Объединяет статичную инфу пилотов (DriverInfo.Drivers: имя, номер, iRating,
лицензия, класс) с live-массивами по индексу машины (позиция, разрыв, круги).
"""
import math

from ire.collector.live_state import class_color

# Цвета лицензий как в iRacing: R красный, D оранжевый, C жёлтый, B зелёный, A синий
LICENSE_COLORS = {"R": "#e74c3c", "D": "#e67e22", "C": "#f1c40f",
                  "B": "#1f9e4a", "A": "#3e7bfa", "P": "#a55eea", "WC": "#a55eea"}


def _arr(ir, name):
    v = ir[name]
    return v if v else []


def parse_license(lic):
    """'B 4.15' → ('B', 4.15). Пусто/мусор → (None, None)."""
    if not isinstance(lic, str):
        return None, None
    parts = lic.strip().split()
    letter = parts[0].upper() if parts else None
    if letter not in LICENSE_COLORS:
        return None, None
    try:
        sr = float(parts[1]) if len(parts) > 1 else None
    except ValueError:
        sr = None
    return letter, sr


def strength_of_field(iratings):
    """SoF по формуле iRacing, а НЕ среднее арифметическое.

    SoF = k·ln(N / Σ exp(−iR/k)), где k = 1600/ln2. При равных рейтингах даёт
    ровно этот рейтинг, но слабые пилоты тянут SoF вниз сильнее, чем в среднем —
    поэтому цифра совпадает с той, что iRacing пишет на входе в сессию.
    """
    irs = [r for r in iratings if isinstance(r, (int, float)) and r > 0]
    if not irs:
        return None
    k = 1600 / math.log(2)
    total = sum(math.exp(-r / k) for r in irs)
    if total <= 0:
        return None
    return round(k * math.log(len(irs) / total))


def cars_in_class(rows):
    """Сколько машин ЕДЕТ в моём классе: сошедшие (нет в мире) не считаются."""
    live = [r for r in rows if not r.get("out")]
    me = next((r for r in rows if r.get("is_player")), None)
    if not me or not me.get("car_class"):
        return len(live)
    return len([r for r in live if r.get("car_class") == me["car_class"]])


_BRANDS = ("cadillac", "porsche", "ferrari", "lamborghini", "mercedesamg", "mercedes",
           "mclaren", "chevrolet", "corvette", "ford", "mustang", "astonmartin", "aston",
           "bentley", "bmw", "audi", "acura", "honda", "toyota", "supra", "nissan", "hyundai",
           "lexus", "subaru", "mazda", "volkswagen", "renault", "dodge", "ligier", "oreca",
           "dallara", "gibson", "radical", "ruf", "lotus")
# приводим к базовому имени файла логотипа
_BRAND_ALIAS = {"corvette": "chevrolet", "mustang": "ford", "supra": "toyota",
                "mercedesamg": "mercedes", "aston": "astonmartin"}


def manufacturer_of(car_path, car_name=None):
    """Марка машины (для логотипа) из CarPath/имени: 'porsche992rgt3' → 'porsche'. None если не нашли."""
    for src in (car_path, car_name):
        s = (src or "").lower().replace(" ", "").replace("-", "")
        for b in _BRANDS:
            if b in s:
                return _BRAND_ALIAS.get(b, b)
    return None


def predict_ir_changes(rows, is_race):
    """Прогноз изменения iRating «если гонка закончится сейчас» — ОЦЕНКА (не точное значение iRacing).
    Внутри класса: попарная ожидаемая вероятность обхода (та же экспонента, что в SoF),
    Δ ∝ (реально обошёл − ожидаемо). Пишет r['ir_gain'] (int) или None вне гонки."""
    for r in rows:
        r["ir_gain"] = None
    if not is_race:
        return
    B = 1600 / math.log(2)
    by_class = {}
    for r in rows:
        if isinstance(r.get("irating"), (int, float)) and r["irating"] > 0:
            by_class.setdefault(r.get("car_class"), []).append(r)
    for group in by_class.values():
        n = len(group)
        if n < 2:
            for r in group:
                r["ir_gain"] = 0
            continue
        ordered = sorted(group, key=lambda r: r.get("pos") or 9999)
        for idx, r in enumerate(ordered):
            ri = r["irating"]
            exp = 0.0
            for r2 in group:
                if r2 is r:
                    continue
                rj = r2["irating"]
                ai = (1 - math.exp(-ri / B)) * math.exp(-rj / B)
                aj = (1 - math.exp(-rj / B)) * math.exp(-ri / B)
                s = ai + aj
                if s > 0:
                    exp += ai / s                      # ожидаемо, что i финиширует впереди j
            actual = n - 1 - idx                        # реально обошёл в классе (idx0=лидер → n−1)
            r["ir_gain"] = round((actual - exp) * (200.0 / n))


def fmt_gap(gap, laps_down=0, leader=False):
    """Отрыв по-человечески, чтобы не считать в уме:
    «лидер» · «+2L» (кругов) · «+0.312» · «+12.4» · «+3:18.5» (за минутой — м:сс.д)."""
    if leader:
        return "leader"
    if laps_down and laps_down >= 1:
        return f"+{laps_down}L"
    if not isinstance(gap, (int, float)) or gap <= 0:
        return "—"
    if gap < 1:
        return f"+{gap:.3f}"                             # в ближнем бою важны тысячные
    if gap < 60:
        return f"+{gap:.1f}"
    m, s = divmod(gap, 60)
    return f"+{int(m)}:{s:04.1f}"


def _session_type(ir):
    """Тип текущей сессии ('Race'/'Practice'/'Qualify') — на круги отстают только в гонке."""
    si = ir["SessionInfo"] or {}
    n = ir["SessionNum"]
    for s in (si.get("Sessions") or []):
        if s.get("SessionNum") == n:
            return s.get("SessionType") or ""
    return ""


def _dist(lapc_v, pct_v):
    """Пройдено кругов = завершённые + доля текущего. Так отставание на круг
    считается по положению на трассе и не «мигает» на линии старт/финиша."""
    if not isinstance(lapc_v, (int, float)) or lapc_v < 0:
        return None
    p = pct_v if isinstance(pct_v, (int, float)) and 0.0 <= pct_v <= 1.0 else 0.0
    return lapc_v + p


def _add_gaps(rows, is_race):
    """Проставляет laps_down + готовую строку gap_txt (лидер сверху = rows[0])."""
    lead = rows[0] if rows else None
    ld = lead.get("_d") if lead else None
    for r in rows:
        n = 0
        if is_race and ld is not None and r.get("_d") is not None:
            n = max(0, int(ld - r["_d"]))
        r["laps_down"] = n
        r["gap_txt"] = fmt_gap(r.get("gap"), n, leader=(r is lead))
        r.pop("_d", None)


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
    lapc = _arr(ir, "CarIdxLapCompleted")
    pct = _arr(ir, "CarIdxLapDistPct")
    surf = _arr(ir, "CarIdxTrackSurface")
    pit = _arr(ir, "CarIdxOnPitRoad")
    is_race = "race" in _session_type(ir).lower()

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
        if p <= 0:                                       # ещё нет позиции (не стартовал)
            continue
        lt = at(last, idx)
        bt = at(best, idx)
        letter, sr = parse_license(d.get("LicString"))
        rows.append({
            "pos": p,
            "number": d.get("CarNumber"),
            "name": d.get("UserName"),
            "irating": d.get("IRating"),
            "license": d.get("LicString"),
            "lic": letter,                               # буква лицензии (A/B/C/D/R)
            "sr": sr,                                    # safety rating числом
            "lic_color": LICENSE_COLORS.get(letter, "#9099a6"),
            "car": d.get("CarScreenNameShort"),
            "car_path": d.get("CarPath"),
            "manufacturer": manufacturer_of(d.get("CarPath"), d.get("CarScreenNameShort")),
            "car_class": d.get("CarClassShortName"),
            "class_color": class_color(d.get("CarClassShortName"), d.get("CarPath"),
                                       d.get("CarScreenNameShort"), d.get("CarClassColor")),
            "gap": round(at(f2, idx, 0.0) or 0.0, 3),    # до лидера, сек
            "last": round(lt, 3) if isinstance(lt, (int, float)) and lt > 0 else None,
            "best": round(bt, 3) if isinstance(bt, (int, float)) and bt > 0 else None,
            "lap": at(lap, idx),
            "on_pit": bool(at(pit, idx, False)),
            "out": at(surf, idx, 3) == -1,               # сошёл: машины нет в мире
            "is_player": idx == my_idx,
            "_d": _dist(at(lapc, idx), at(pct, idx)),
        })
    rows.sort(key=lambda r: r["pos"])
    _add_gaps(rows, is_race)
    predict_ir_changes(rows, is_race)                    # прогноз ± iRating (оценка)
    return rows
