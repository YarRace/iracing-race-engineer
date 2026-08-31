"""Телеметрия круга на диске — то, без чего невозможен разбор круга.

Раньше кадры жили только в памяти `run.py` и обнулялись при смене сессии.
В историю писалось лишь время круга и три сектора, а формы торможения,
точки первого газа и скорости в апексе не оставалось нигде. Поэтому «где
я потерял время в седьмом повороте» ответить было не из чего.

Каждый круг ресемплится на сетку ПО ДИСТАНЦИИ и кладётся отдельным файлом.
Сетка по дистанции, а не по времени, принципиальна: два круга с разным
временем нужно сравнивать в одной и той же точке трассы, иначе к концу
круга графики разъезжаются и разница читается как ошибка там, где её нет.

Сетка задана в долях круга, а не в метрах: SDK не отдаёт длину трассы.
POINTS=1000 — это 0.1% дистанции, около пяти метров на пятикилометровой
трассе, чего хватает даже для точки начала торможения.

Формат — gzip поверх JSON: без внешних зависимостей, читается любым
инструментом, круг весит порядка 30 КБ. Файлы лежат в data/laps/, папка
уже в .gitignore.
"""
import gzip
import json
import os
import pathlib
import threading
import time

from . import history

POINTS = 1000
MIN_COVERAGE = 0.92        # доля круга, которую телеметрия обязана покрыть

# Каналы, которые нужны для разбора круга. Температуры и износ сюда не
# попадают: они меняются на масштабе стинта, а не поворота, и хранятся
# в метаданных одним значением.
CHANNELS = ("speed", "throttle", "brake", "steer", "gear",
            "lat_accel", "long_accel", "yaw_rate")


def default_root():
    """data/laps рядом с базой истории."""
    return pathlib.Path(history.default_path()).parent / "laps"


def split_laps(frames):
    """Режет поток кадров на круги. Возвращает [(номер, кадры), …].

    Неполные круги отбрасываются. Первый круг почти всегда начинается
    с середины (выезд из боксов), последний обрывается на входе в них —
    сравнивать по ним нельзя, а испортить статистику они могут.
    """
    if not frames:
        return []
    out, cur, num = [], [], frames[0].get("lap")
    for f in frames:
        if f.get("lap") != num:
            out.append((num, cur))
            cur, num = [], f.get("lap")
        cur.append(f)
    out.append((num, cur))

    full = []
    for n, fr in out:
        if len(fr) < 10:
            continue
        p = [x.get("lap_dist_pct") for x in fr if x.get("lap_dist_pct") is not None]
        # круг считаем полным, если он начался у линии и дошёл до конца
        if p and min(p) < 0.05 and max(p) > 0.95:
            full.append((n, fr))
    return full


def lap_time(frames):
    """Длительность круга по меткам времени кадров."""
    ts = [f.get("t") for f in frames if f.get("t") is not None]
    return (max(ts) - min(ts)) if len(ts) >= 2 else None


def coverage(frames):
    """Какую долю круга кадры реально покрывают: (начало, конец).

    Это не мелочь. За пределами покрытия `_interp` держит крайнее значение,
    то есть рисует ПРЯМУЮ на постоянной скорости. 31.08.2026 сохранённый круг
    начинался с 8.9% дистанции, и первые 89 точек из тысячи оказались ровной
    полкой на 64 км/ч. Разбор по поворотам честно посчитал это потерей
    в 19.8 секунды — при том, что весь круг медленнее эталона на одну.
    """
    xs = [f.get("lap_dist_pct") for f in frames if f.get("lap_dist_pct") is not None]
    if len(xs) < 2:
        return (0.0, 0.0)
    return (min(xs), max(xs))


def resample(frames, points=POINTS):
    """Каналы на равномерной сетке по доле дистанции.

    Кадры сортируются по дистанции: SDK изредка отдаёт долю с дрожанием
    назад, и без сортировки линейная интерполяция даёт пилу.
    """
    pts = [(f.get("lap_dist_pct"), f) for f in frames if f.get("lap_dist_pct") is not None]
    if len(pts) < 2:
        return {}
    pts.sort(key=lambda x: x[0])
    xs = [p for p, _ in pts]

    out = {}
    for ch in CHANNELS:
        ys = [_num(f.get(ch)) for _, f in pts]
        out[ch] = [_interp(xs, ys, i / (points - 1)) for i in range(points)]
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _interp(xs, ys, x):
    """Линейная интерполяция по возрастающему xs. За краями — крайнее значение."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:                       # двоичный поиск: круг из 1000 точек
        mid = (lo + hi) // 2                 # иначе строится за квадрат
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    dx = xs[hi] - xs[lo]
    if dx <= 0:
        return ys[lo]
    return ys[lo] + (ys[hi] - ys[lo]) * (x - xs[lo]) / dx


def _slug(s):
    """Имя файла из произвольной строки: без пробелов и служебных символов."""
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in (s or "unknown").lower()]
    return "".join(keep).strip("-") or "unknown"


def save_lap(root, identity, lap_num, lap_t, frames, valid=None):
    """Пишет круг на диск. Возвращает путь либо None, если круг не годится.

    Невалидные круги (заезд в боксы, обрыв) не пишутся: база эталонов
    засоряется мгновенно, а пользы от таких кругов нет.
    """
    if valid is None:
        valid = history.is_valid_lap(lap_t)
    if not valid:
        return None

    # Круг обязан покрывать почти всю дистанцию. Проверять только ВРЕМЯ мало:
    # 31.08.2026 на диск лёг круг с правильным временем, но телеметрией
    # с 8.9% дистанции — начало заполнилось ровной полкой на 64 км/ч, и разбор
    # насчитал по ней 19.8 секунды потерь при разнице круга в одну.
    # База эталонов от таких кругов бесполезна, а вреда от них больше, чем
    # от их отсутствия.
    lo, hi = coverage(frames)
    if hi - lo < MIN_COVERAGE:
        return None
    ch = resample(frames)
    if not ch:
        return None

    first = frames[0]
    meta = {
        "track": identity.get("track"), "track_display": identity.get("track_display"),
        "config": identity.get("config"), "car": identity.get("car"),
        "car_path": identity.get("car_path"), "car_class": identity.get("car_class"),
        "session_type": identity.get("session_type"),
        "lap_num": lap_num, "lap_time": lap_t, "points": POINTS,
        # условия круга: без них нельзя честно выбрать эталон — круг на полном
        # баке по холодной трассе несравним с кругом на пустом по горячей
        "fuel_start": _num(first.get("fuel")),
        "track_temp": _num(first.get("track_temp")),
        "air_temp": _num(first.get("air_temp")),
        # Какую часть круга кадры реально покрывают. Без этого поля круг
        # с обрезанным началом неотличим от целого: недостающее место
        # заполняется ровной полкой и выглядит как настоящая телеметрия.
        "covers": list(coverage(frames)),
        "ts": history._now(),
    }

    d = pathlib.Path(root) / _slug(identity.get("track"))
    d.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(identity.get('car'))}-{meta['ts'][:19].replace(':', '')}-l{lap_num}.json.gz"
    path = d / name

    # Пишем во временный файл и подменяем одним движением. Сохранение идёт
    # в фоновом потоке, а поток демонический: закрыл run.py сразу после линии —
    # его убили посреди записи. Без подмены на диске оставался обрезанный
    # .json.gz, который list_laps молча пропускает: круг проехан, а его нет.
    # Расширение .tmp не попадает под маску *.json.gz, поэтому недописанный
    # файл невидим для списка даже до уборки.
    #
    # Имя временного файла уникально для каждого писателя (процесс + поток).
    # Имя КРУГА уникальности не даёт: в него входит время с точностью до
    # секунды, и два запущенных run.py видят одну и ту же смену круга в один
    # и тот же миг. 28.08.2026 так и вышло — два процесса писали один файл,
    # и четыре круга из пяти легли на диск перемешанной кашей (битый CRC,
    # буквы посреди чисел). С уникальным .tmp гонка остаётся, но каждый пишет
    # своё, а os.replace подменяет целиком: побеждает последний, файл всегда
    # читается.
    tmp = d / f"{name}.{os.getpid()}-{threading.get_ident()}.tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump({**meta, "channels": ch}, fh, separators=(",", ":"))
        _replace_with_retry(tmp, path)
    except BaseException:
        # BaseException, а не Exception: поток гасят через SystemExit,
        # и мусор надо убрать в том числе на этом пути.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return path


def _replace_with_retry(tmp, path, tries=10, pause=0.05):
    """Подменить файл, переждав соседа.

    Windows отказывает в доступе, если тот же файл прямо сейчас подменяет
    другой писатель, — в отличие от POSIX, где os.replace просто выигрывает.
    Ждём и пробуем снова; если сосед всё-таки успел раньше, круг уже лежит
    на диске (данные те же — то же имя означает ту же машину, ту же секунду
    и тот же номер круга), и настаивать не на чем.

    Пауза растёт: фиксированные 6×0.05 с давали суммарные 0.3 секунды, и на
    загруженной машине этого не хватало — при шести одновременных писателях
    часть кругов терялась. Теперь суммарно около трёх секунд, и ожидание
    само растягивается ровно настолько, насколько занят диск.
    """
    for attempt in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == tries - 1:
                if path.exists():
                    tmp.unlink(missing_ok=True)     # сосед записал тот же круг
                    return
                raise
            time.sleep(pause * (attempt + 1))


def load_lap(path):
    """Круг целиком: метаданные и каналы."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def list_laps(root, track=None, car=None):
    """Метаданные сохранённых кругов, от быстрого к медленному.

    Каналы не читаются — только шапка файла, поэтому список строится быстро
    даже на тысяче кругов. Битые файлы пропускаются молча: один сбой записи
    не должен ломать весь экран сравнения.
    """
    root = pathlib.Path(root)
    if not root.exists():
        return []
    out = []
    for p in sorted(root.rglob("*.json.gz")):
        try:
            m = load_lap(p)
        except Exception:
            continue
        if track and m.get("track") != track:
            continue
        if car and m.get("car") != car:
            continue
        m.pop("channels", None)
        m["path"] = str(p)
        out.append(m)
    out.sort(key=lambda m: (m.get("lap_time") is None, m.get("lap_time")))
    return out
