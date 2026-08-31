"""Проверка входа в iRacing: заработало или нет, и что именно не так.

Смысл отдельного инструмента в том, что вход в iRacing ломается по пяти
разным причинам, и все они снаружи выглядят одинаково — «не работает».
Здесь каждая названа отдельно и сказано, что с ней делать.

Пароль НИКОГДА не печатается — ни целиком, ни кусками. Всё, что скрипт
про него говорит, — это «в файле есть» или «в файле пусто».

Запуск:
    python tools/iracing_login.py            проверить и показать профиль
    python tools/iracing_login.py --setup    создать заготовку файла
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

STEPS = """
  Что сделать, по шагам:

  1. Открой Проводник и зайди в папку:
       {folder}

  2. Скопируй файл  iracing_auth.example.json  и назови копию:
       iracing_auth.json

  3. Открой его Блокнотом и впиши СВОИ данные вместо примера:
       {{"email": "твоя-почта@пример.ru", "password": "твой-пароль"}}

     Это та же почта и тот же пароль, которыми ты заходишь на
     members.iracing.com. Кавычки и запятую не трогай.

  4. Сохрани и запусти снова:
       python tools/iracing_login.py

  Файл лежит в папке data/, а она в .gitignore — в репозиторий и никуда
  наружу он не уедет. Пароль отправляется только в виде хеша.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true",
                    help="создать заготовку data/iracing_auth.json")
    a = ap.parse_args()

    from ire import paths
    from ire.collector import iracing_api as api

    folder = paths.data_dir()
    target = folder / "iracing_auth.json"

    if a.setup:
        if target.exists():
            print(f"  Файл уже есть: {target}")
        else:
            target.write_text(json.dumps(
                {"email": "твоя-почта@пример.ru", "password": "твой-пароль"},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  Создал заготовку: {target}")
            print("  Открой её Блокнотом и впиши свои данные.")
        return 0

    print(f"  Ищу файл: {target}")
    if not target.exists():
        print("  Файла нет.")
        print(STEPS.format(folder=folder))
        return 1

    email, password = api.credentials()
    if not email or not password:
        print("  Файл есть, но данные в нём пустые или он написан с ошибкой.")
        print("  Проверь, что внутри ровно такая строка (со своими данными):")
        print('    {"email": "твоя-почта@пример.ru", "password": "твой-пароль"}')
        return 1
    if "@" not in email:
        print(f"  В поле email не похоже на почту: {email!r}")
        return 1
    if "пример.ru" in email or password == "твой-пароль":
        print("  В файле остался ПРИМЕР, а не твои данные.")
        print(STEPS.format(folder=folder))
        return 1

    print(f"  Почта: {email}")
    print("  Пароль: есть (сюда он не печатается и в лог не пишется)")
    print("  Захожу в iRacing…")

    c = api.Client()
    if not c.login():
        print(f"\n  Не вышло: {c.error}\n")
        if "CAPTCHA" in c.error:
            print("  Это НЕ поломка. iRacing иногда просит подтвердить, что ты")
            print("  человек. Обходить проверку мы не будем — она для того и есть.")
            print("  Открой в браузере members.iracing.com, зайди один раз руками")
            print("  и запусти эту проверку снова.")
        elif "429" in c.error or "rate" in c.error.lower():
            print("  Слишком часто входили. Подожди 10–15 минут и попробуй ещё раз.")
        elif "rejected" in c.error or "password" in c.error.lower():
            print("  iRacing не принял почту или пароль. Проверь их на сайте:")
            print("  если туда заходишь — значит опечатка в файле.")
        else:
            print("  Похоже на сеть. У тебя всё идёт через VPN — проверь, что")
            print("  туннель поднят, и попробуй снова.")
        return 1

    print("  Вход есть. Спрашиваю профиль…")
    p = api.profile(force=True)
    if not p.get("ok"):
        print(f"  Вошли, но профиль не отдался: {p.get('reason')}")
        return 1

    print(f"\n  ГОТОВО. Ты для iRacing: {p.get('name')}"
          f"{'  ·  клуб ' + p['club'] if p.get('club') else ''}")
    for x in p.get("licenses") or []:
        ir = x.get("irating")
        print(f"    {str(x.get('category')):<16} iRating {ir if ir else '—':<6} "
              f"лицензия {x.get('licence') or '—'}")
    print("\n  Теперь это само появится на главной в приложении.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
