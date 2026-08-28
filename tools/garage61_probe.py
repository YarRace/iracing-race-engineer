"""Разведка API Garage 61: что он реально отдаёт по нашему токену.

Проверено на живых данных 28.08.2026 — и результат опроверг то, чего мы ждали
по документации. Разрешение driving_data у токена ЕСТЬ, поэтому:

  • чужие круги отдаются (Road Atlanta: 21 круг от 21 разного пилота);
  • их телеметрия тоже (canViewTelemetry=true у 19 из 21);
  • CSV содержит все 8 наших каналов плюс Lat/Lon — настоящие координаты,
    то есть геометрию трассы, которой iRacing SDK не даёт вовсе.

Значит сравнение с чужим эталоном возможно, и это главное, ради чего затевалась
телеметрия.

Особенности схемы, на которых спотыкается наивный клиент:

  • списки приходят конвертом {"items": [...], "total": N}, а не голым списком;
  • /laps ТРЕБУЕТ параметр tracks — без него 400, а не пустой ответ;
  • телеметрия только по /laps/{id}/csv; /laps/{id}/telemetry отдаёт 404;
  • профиль зовёт поля firstName/lastName/nickName и apiPermissions,
    а не name/permissions.

Токен НЕ передавать в командной строке и не вставлять в код. Скрипт берёт его
из переменной окружения GARAGE61_TOKEN либо из файла data/garage61_token.txt
(папка data/ в .gitignore). В выводе токен не печатается ни в каком виде.

Запуск:
    python tools/garage61_probe.py                        Road Atlanta по умолчанию
    python tools/garage61_probe.py --track "Spa"          другая трасса
    python tools/garage61_probe.py --track "Monza" --car "499P"
    python tools/garage61_probe.py --tracks-like atlanta  показать id по слову
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://garage61.net/api/v1"


def token():
    t = os.environ.get("GARAGE61_TOKEN", "").strip()
    if t:
        return t
    f = pathlib.Path(__file__).resolve().parents[1] / "data" / "garage61_token.txt"
    if f.exists():
        # utf-8-sig: Блокнот на Windows дописывает BOM, а он ломает заголовок
        t = f.read_text(encoding="utf-8-sig").strip()
        if t:
            return t
    sys.exit(
        "Токена нет.\n"
        "  1. Войди на garage61.net\n"
        "  2. Открой garage61.net/developer/applications, зайди в приложение\n"
        "  3. Скопируй персональный токен\n"
        "  4. Вставь одной строкой в data/garage61_token.txt\n"
        "     Папка data/ в .gitignore — токен в репозиторий не уедет.\n"
    )


def get(path, timeout=40, **params):
    """(код, данные). JSON разбирается, остальное отдаётся текстом.

    Телеметрию сервер собирает на лету — круг на четыре тысячи точек приходит
    заметно дольше справочника, поэтому у CSV своё ожидание.
    """
    url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token(),
        "Accept": "application/json",
        "User-Agent": "iracing-race-engineer/probe",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            ct = r.headers.get("Content-Type", "")
            return r.status, (json.loads(body) if "json" in ct else body.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:                                   # сеть, таймаут, VPN
        return 0, str(e)


def items(data):
    """Распаковка конверта {"items": [...], "total": N}."""
    if isinstance(data, dict):
        return data.get("items", [])
    return data or []


def who(lap):
    d = lap.get("driver") or {}
    name = f"{d.get('firstName', '')} {d.get('lastName', '')}".strip()
    return name or d.get("slug") or "?"


def lap_time(sec):
    return f"{int(sec // 60)}:{sec % 60:06.3f}" if isinstance(sec, (int, float)) else "—"


def head(t):
    print("\n" + "─" * 66 + "\n" + t + "\n" + "─" * 66)


def find(catalog, needle):
    """Записи справочника, чьё имя содержит подстроку (без учёта регистра)."""
    n = needle.lower()
    return [x for x in catalog if n in (x.get("name", "") + " " + x.get("variant", "")).lower()]


def main():
    ap = argparse.ArgumentParser(description="Что отдаёт Garage 61 нашему токену")
    ap.add_argument("--track", default="Road Atlanta Full Course", help="название трассы")
    ap.add_argument("--car", default="", help="название машины (необязательно)")
    ap.add_argument("--limit", type=int, default=100, help="сколько кругов запросить")
    ap.add_argument("--tracks-like", default="", help="показать id трасс по слову и выйти")
    a = ap.parse_args()

    head("1. Кто мы")
    code, me = get("/me")
    print(f"  /me -> {code}")
    if code != 200:
        print(" ", me)
        sys.exit("  Токен не принят. Проверь, что он скопирован целиком, одной строкой.")
    my_id = me.get("id")
    print(f"  {me.get('firstName', '')} {me.get('lastName', '')} · ник {me.get('nickName')} "
          f"· план {me.get('subscriptionPlan')}")
    perms = me.get("apiPermissions") or []
    print(f"  разрешения: {', '.join(perms) if perms else 'нет'}")
    if "driving_data" in perms:
        print("  driving_data ЕСТЬ — чужие круги и их телеметрия доступны")
    else:
        print("  driving_data НЕТ — видны только свои круги и круги одноклубников")
    for t in me.get("teams") or []:
        print(f"    команда: {t.get('name')}")

    head("2. Справочники")
    _, T = get("/tracks")
    _, C = get("/cars")
    tracks, cars = items(T), items(C)
    print(f"  трасс {len(tracks)} · машин {len(cars)}")

    if a.tracks_like:
        head(f"Трассы по слову «{a.tracks_like}»")
        for t in find(tracks, a.tracks_like):
            print(f"  id={t['id']:<5} {t['name']} {t.get('variant') or ''}")
        return 0

    tm = find(tracks, a.track)
    if not tm:
        sys.exit(f"\n  Трасса «{a.track}» не найдена. "
                 f"Подбери id: --tracks-like <слово>")
    track = tm[0]
    if len(tm) > 1:
        print(f"  ! под «{a.track}» подошло {len(tm)}, беру первую — "
              f"уточни название, если не та")
    car = None
    if a.car:
        cm = find(cars, a.car)
        if not cm:
            sys.exit(f"  Машина «{a.car}» не найдена.")
        car = cm[0]
    print(f"  выбрано: {track['name']} {track.get('variant') or ''} (id {track['id']})"
          + (f" · {car['name']} (id {car['id']})" if car else " · все машины"))

    head("3. Чьи круги отдаёт /laps")
    q = {"tracks": track["id"], "limit": a.limit}
    if car:
        q["cars"] = car["id"]
    code, L = get("/laps", **q)
    print(f"  /laps -> {code}")
    if code != 200:
        print(" ", L)
        return 1
    laps = sorted(items(L), key=lambda x: x.get("lapTime") or 9e9)
    total = L.get("total") if isinstance(L, dict) else len(laps)
    print(f"  кругов {len(laps)} из {total}")
    if not laps:
        print("  Пусто. На этой связке никто не ездил либо круги не публичны.")
        return 0

    others = [x for x in laps if (x.get("driver") or {}).get("id") != my_id]
    print(f"  пилотов разных: {len({who(x) for x in laps})} · чужих кругов: {len(others)}")
    print()
    for x in laps[:10]:
        mark = " ← ты" if (x.get("driver") or {}).get("id") == my_id else ""
        tele = "телеметрия" if x.get("canViewTelemetry") else "без телеметрии"
        print(f"  {lap_time(x.get('lapTime')):>10}  {who(x):<26} {tele}{mark}")

    head("4. Телеметрия эталона")
    cand = [x for x in others if x.get("canViewTelemetry")]
    if not cand:
        print("  Чужих кругов с телеметрией нет — эталон берём из своей базы.")
        return 0

    # Сервер собирает CSV на лету и на части кругов не успевает: отдаёт 504
    # после трёх минут. 28.08.2026 из трёх подряд взятых кругов два ответили
    # 504, третий — 200 за 32 секунды. Поэтому не упираемся в самый быстрый,
    # а идём по списку вниз, пока какой-нибудь не отдастся.
    csv = None
    for ref in cand[:4]:
        print(f"  качаю {who(ref)}, {lap_time(ref.get('lapTime'))} …")
        code, body = get(f"/laps/{ref['id']}/csv", timeout=200)
        if code == 200 and isinstance(body, str):
            csv = body
            break
        why = "сервер не успел собрать (504)" if code == 504 else f"{code} {str(body)[:90]}"
        print(f"    не отдалось: {why}")
    if csv is None:
        print("\n  Ни один круг не отдался. Это сторона Garage 61, не наша —")
        print("  список кругов приходит за секунду. Попробуй позже.")
        return 1
    rows = csv.splitlines()
    cols = rows[0].split(",") if rows else []
    print(f"  точек {len(rows) - 1} · каналов {len(cols)}")
    print(f"  {', '.join(cols)}")
    need = {"Speed", "LapDistPct", "Brake", "Throttle",
            "SteeringWheelAngle", "Gear", "LatAccel", "LongAccel"}
    missing = sorted(need - set(cols))
    print(f"\n  наши каналы: {'все на месте' if not missing else 'НЕ ХВАТАЕТ ' + ', '.join(missing)}")
    if {"Lat", "Lon"} <= set(cols):
        print("  Lat/Lon есть — по ним строится настоящая геометрия трассы,")
        print("  которую iRacing SDK не отдаёт вовсе")
    return 0


if __name__ == "__main__":
    sys.exit(main())
