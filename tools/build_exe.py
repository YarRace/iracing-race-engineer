"""Сборка Windows-приложения одним файлом .exe... точнее, одной папкой.

Почему папка, а не один файл: PySide6 в режиме onefile каждый запуск
распаковывает ~120 МБ во временный каталог. Это несколько секунд ожидания
перед КАЖДЫМ стартом и постоянные ложные срабатывания антивирусов на
самораспаковку. Папка стартует мгновенно; для раздачи её всё равно
кладут в архив.

Собираются ДВА приложения, как и запускаются:
    RaceEngineer.exe        — инженер: читает сим, отдаёт дашборд на :8000
    RaceEngineerOverlay.exe — панель оверлея поверх игры

Данные пользователя (data/) внутрь НЕ кладутся: история кругов, карты трасс
и раскладка оверлея принадлежат тому, у кого стоит программа, а не сборке.
Приложение создаёт data/ рядом с собой при первом запуске.

Запуск:
    python tools/build_exe.py                 → dist/RaceEngineer/
    python tools/build_exe.py --clean         с нуля, без кеша
"""
import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WORK = ROOT / "build"

# (имя приложения, точка входа, оконное ли)
# Инженер — консольный намеренно: он печатает, что видит в симе, и когда
# что-то не так, это единственное окно, куда можно посмотреть.
APPS = [
    ("RaceEngineer", "run.py", False),
    ("RaceEngineerOverlay", "overlay_app.py", True),
]

# Данные, без которых приложение не работает. Пути внутри сборки повторяют
# структуру репозитория — код ищет их относительно корня.
DATAS = [
    ("src/ire/dashboard/static", "src/ire/dashboard/static"),
    ("data/catalog.json", "data"),
    ("docs/widgets", "docs/widgets"),
    ("docs/panel", "docs/panel"),
    ("docs/dashboard", "docs/dashboard"),
    ("docs/news", "docs/news"),
    ("docs/hero.png", "docs"),
]

# ВНИМАНИЕ: пути назначения обязаны совпадать с тем, что считает
# `ire.paths.res_root()` — внутри сборки это sys._MEIPASS. Разъезд не
# ломает запуск: приложение поднимается, отдаёт страницу и валится 500-й
# на стилях. Тест tests/test_paths.py держит соответствие.

# PyInstaller не видит эти импорты: они делаются по строке из переменной
# окружения или внутри uvicorn, а не написаны в коде явно.
HIDDEN = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "irsdk", "anthropic",
]

# Тянуть в сборку нечего: тесты, инструменты разработки и торчащие
# зависимости от них весят больше, чем всё приложение.
EXCLUDE = ["pytest", "PySide6.QtWebEngineCore", "PySide6.QtQuick",
           "PySide6.Qt3DCore", "matplotlib", "tkinter"]


def command(name, entry, windowed, clean):
    sep = ";"                                     # разделитель --add-data на Windows
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm",
           "--name", name, "--distpath", str(DIST), "--workpath", str(WORK),
           "--specpath", str(WORK),
           "--paths", str(ROOT), "--paths", str(ROOT / "src")]
    if clean:
        cmd.append("--clean")
    if windowed:
        cmd.append("--windowed")
    for src, dst in DATAS:
        p = ROOT / src
        if p.exists():                            # снимков может не быть — не беда
            cmd += ["--add-data", f"{p}{sep}{dst}"]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    for x in EXCLUDE:
        cmd += ["--exclude-module", x]
    cmd.append(str(ROOT / entry))
    return cmd


def size_of(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--only", default="", help="собрать только одно приложение")
    args = ap.parse_args()

    try:
        import PyInstaller                                    # noqa: F401
    except ImportError:
        print("  PyInstaller не установлен:  pip install pyinstaller")
        return 1

    built, failed = [], []
    for name, entry, windowed in APPS:
        if args.only and args.only != name:
            continue
        print(f"\n  собираю {name} из {entry} …")
        r = subprocess.run(command(name, entry, windowed, args.clean),
                           cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = DIST / name
        if r.returncode != 0 or not (out / f"{name}.exe").exists():
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-12:]
            failed.append((name, "\n      ".join(tail)))
            continue
        built.append((name, out))

    print()
    for name, out in built:
        print(f"  ГОТОВО {name}: {out}  ({size_of(out) // 1024 // 1024} МБ)")
    for name, err in failed:
        print(f"  ПРОВАЛ {name}:\n      {err}")
    if built and not failed:
        print("\n  Раздавать: заархивировать папки из dist/ целиком.")
        print("  data/ внутрь не кладётся — программа создаст её при запуске.")
    return 1 if failed else 0


def clean():
    for d in (DIST, WORK):
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
