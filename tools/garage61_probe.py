"""Разведка API Garage 61: что он реально отдаёт по нашему токену.

Главный вопрос, ради которого написан скрипт: возвращает ли /laps круги
ДРУГИХ пилотов или только свои. От ответа зависит, сможем ли мы брать
эталонные круги оттуда вместо того, чтобы строить свою базу.

Токен НЕ передавать в командной строке и не вставлять в код. Скрипт берёт его
из переменной окружения GARAGE61_TOKEN либо из файла data/garage61_token.txt
(папка data/ в .gitignore, в репозиторий не попадёт). В выводе токен не
печатается ни в каком виде.

Запуск:
    python tools/garage61_probe.py
"""
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
        return f.read_text(encoding="utf-8").strip()
    sys.exit(
        "Токена нет.\n"
        "  1. Зайди на garage61.net под своим аккаунтом\n"
        "  2. Настройки аккаунта -> раздел для разработчиков -> создать токен\n"
        "  3. Сохрани его в файл data/garage61_token.txt (одной строкой)\n"
        "     Папка data/ в .gitignore — токен в репозиторий не уедет.\n"
    )


def get(path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token(),
        "Accept": "application/json",
        "User-Agent": "iracing-race-engineer/probe",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            ct = r.headers.get("Content-Type", "")
            return r.status, (json.loads(body) if "json" in ct else body.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:                                   # сеть, таймаут, VPN
        return 0, str(e)


def head(t):
    print("\n" + "─" * 62 + "\n" + t + "\n" + "─" * 62)


def main():
    head("1. Кто мы")
    code, me = get("/me")
    print("  /me ->", code)
    if code != 200:
        print("  ", me)
        sys.exit("  Токен не принят. Проверь, что он скопирован целиком.")
    my_id = me.get("id") or me.get("userId") or me.get("slug")
    print("  пользователь:", me.get("name") or me.get("displayName") or "?", "| id:", my_id)
    print("  поля ответа:", ", ".join(sorted(me)[:14]))

    head("2. Справочники")
    for p in ("/tracks", "/cars"):
        code, data = get(p)
        n = len(data) if isinstance(data, list) else len((data or {}).get("items", []))
        print(f"  {p} -> {code}, записей: {n}")
        items = data if isinstance(data, list) else (data or {}).get("items", [])
        if items:
            print("    пример:", json.dumps(items[0], ensure_ascii=False)[:150])

    head("3. ГЛАВНОЕ: чьи круги отдаёт /laps")
    code, laps = get("/laps", limit=25)
    print("  /laps -> ", code)
    if code != 200:
        print("  ", laps)
        return
    items = laps if isinstance(laps, list) else (laps or {}).get("items", laps.get("laps", []))
    print("  кругов в ответе:", len(items))
    if not items:
        print("  Пусто. Возможно, нужен фильтр по трассе/машине или в аккаунте нет заездов.")
        return
    print("  поля круга:", ", ".join(sorted(items[0])[:18]))

    drivers = {}
    for l in items:
        d = l.get("driver") or l.get("user") or {}
        key = (d.get("id") or d.get("name") or l.get("driverId") or "?") if isinstance(d, dict) else d
        drivers[str(key)] = drivers.get(str(key), 0) + 1
    print("  уникальных пилотов в выдаче:", len(drivers))
    for k, v in list(drivers.items())[:8]:
        свой = " <- это мы" if str(my_id) and str(k) == str(my_id) else ""
        print(f"    {k}: {v} кругов{свой}")
    print()
    if len(drivers) > 1:
        print("  ВЫВОД: отдаёт круги НЕ ТОЛЬКО наши. Эталоны можно брать отсюда.")
    else:
        print("  ВЫВОД: в выдаче только один пилот. Похоже, доступны лишь свои круги")
        print("  (или круги команды). Значит, эталон берём из своей базы.")

    head("4. Телеметрия круга")
    lap_id = items[0].get("id") or items[0].get("lapId")
    code, csv = get(f"/laps/{lap_id}/csv")
    print(f"  /laps/{lap_id}/csv -> {code}")
    if code == 200 and isinstance(csv, str):
        lines = csv.splitlines()
        print("  строк:", len(lines))
        print("  каналы:", lines[0][:220] if lines else "—")
    else:
        print("  ", str(csv)[:200])


if __name__ == "__main__":
    main()
