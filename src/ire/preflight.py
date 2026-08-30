"""Проверка окружения перед стартом — понятным текстом, а не трассировкой.

Проект написан на синтаксисе, которого нет в старых версиях Python. На 3.11
падение выглядит как `SyntaxError` в случайном файле где-то в середине
импорта: человек видит красную простыню и делает вывод, что программа
сломана, а не что у него не та версия.

Проверять надо ДО импорта остального кода, поэтому здесь нет ни одной
внешней зависимости и ничего новее, чем понимает Python 3.6, — иначе сама
проверка упадёт тем же способом, от которого она защищает.
"""
MIN_PYTHON = (3, 12)

# Пакеты, без которых не стартует ничего. Ключ — что импортируем,
# значение — как называется в pip (это разные имена чаще, чем кажется).
REQUIRED = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn[standard]"),
    ("httpx", "httpx"),
]
OVERLAY = [("PySide6", "PySide6")]


def _line(msg):
    print(msg)


def check(extra=(), exit_on_fail=True):
    """Возвращает список проблем. По умолчанию печатает их и выходит.

    Возврат списка нужен тестам: проверять надо саму проверку, а не то,
    как она завершает процесс.
    """
    import sys

    problems = []
    if sys.version_info < MIN_PYTHON:
        have = ".".join(str(x) for x in sys.version_info[:3])
        need = ".".join(str(x) for x in MIN_PYTHON)
        problems.append(
            "Python {0} is too old — this needs {1} or newer.\n"
            "    You are running: {2}".format(have, need, sys.executable))

    # В собранном .exe зависимости внутри, и проверять их незачем: если
    # чего-то не хватает, приложение не запустилось бы вовсе.
    if not getattr(sys, "frozen", False):
        for mod, pkg in list(REQUIRED) + list(extra):
            try:
                __import__(mod)
            except ImportError:
                problems.append(
                    "Package '{0}' is missing.\n"
                    "    pip install {1}".format(mod, pkg))

    if problems and exit_on_fail:
        _line("")
        _line("  Race Engineer cannot start:")
        for p in problems:
            _line("    - " + p)
        _line("")
        _line("  Full setup: https://github.com/YarRace/iracing-race-engineer")
        _line("")
        # Окно консоли закрывается мгновенно, если запустили двойным кликом,
        # и прочитать сообщение невозможно. Ждём Enter — но только когда
        # ввод вообще есть: под pytest и в CI его нет.
        try:
            if sys.stdin and sys.stdin.isatty():
                input("  Press Enter to close… ")
        except (EOFError, OSError):
            pass
        raise SystemExit(1)
    return problems
