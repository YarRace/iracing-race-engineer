"""Где лежат файлы — в исходниках и в собранном .exe.

Пока проект запускался только из исходников, всё считалось от расположения
модуля: подняться на три уровня — вот и корень. В собранном приложении это
разъезжается, и разъезжается ТИХО: страница отдаётся, а стили к ней 500,
потому что tokens.css искали не там.

Разъезжается потому, что каталогов становится два, и путать их нельзя:

  ── ресурсы ──  всё, что положили в сборку: разметка дашборда, палитра,
      снимки для сайта, чейнджлог, каталог виджетов. Только на чтение,
      одинаковы у всех, кто поставил программу. PyInstaller распаковывает
      их в свою папку и сообщает путь через sys._MEIPASS.

  ── данные ──  то, что принадлежит человеку: история кругов, телеметрия,
      карты трасс, раскладка оверлея. Их нельзя класть внутрь сборки —
      обновление программы стёрло бы всё нажитое. Поэтому они лежат РЯДОМ
      с .exe, и папка переживает любую замену программы.

Из исходников оба корня — это корень репозитория, и поведение не меняется.
"""
import os
import pathlib
import sys


def frozen() -> bool:
    """Запущены ли мы из собранного .exe."""
    return bool(getattr(sys, "frozen", False))


def res_root() -> pathlib.Path:
    """Корень ресурсов сборки (только чтение)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return pathlib.Path(base)
    return pathlib.Path(__file__).resolve().parents[2]


def user_root() -> pathlib.Path:
    """Корень пользовательских данных — рядом с .exe, а не внутри сборки."""
    if frozen():
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parents[2]


def data_dir() -> pathlib.Path:
    """Папка data/. Создаём: при первом запуске .exe её ещё нет."""
    d = user_root() / "data"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass                                  # только чтение — пусть падает дальше
    return d


def res(*parts) -> str:
    """Путь к файлу ресурсов строкой — для os.path-кода."""
    return os.path.join(str(res_root()), *parts)


# Папки, куда человек кладёт СВОИ файлы, и записка в каждой.
#
# Логотипы марок и фото трасс подхватываются по имени файла, и это ровно
# та возможность, о которой никто не узнает: пустой папки нет, а в
# документации к оверлею никто не заглядывает, пока что-нибудь не сломается.
# Поэтому папка создаётся сама и объясняет себя изнутри.
#
# Записка по-английски: её читает пользователь, а интерфейс у нас
# английский. Существующий файл НЕ перезаписываем — человек мог написать
# в нём своё.
_NOTES = {
    "logos": """Manufacturer badges for the standings table.

Drop PNG files with a transparent background in here. The file name is the
manufacturer, and it is matched loosely: porsche.png, Porsche.png,
"Aston Martin.png" and aston-martin.png all work.

  porsche  bmw  ferrari  audi  mercedes  mclaren  lamborghini  chevrolet
  ford  acura  cadillac  astonmartin  bentley  honda  toyota  nissan

Square, 64x64 or larger, transparent. .png is best; .svg .jpg .webp also work.
No file means no badge - nothing breaks, the name just shows without one.

Turn them on in the overlay panel: Standings -> Manuf. logo.
Restart the overlay after adding files.
""",
    "trackphotos": """Photographs to sit behind the track map.

Drop a picture in here and the Track map overlay will use it as a backdrop.
The file name is the track, matched loosely, so all of these work:

  lemans.jpg        "Le Mans.png"      circuit-de-la-sarthe.webp
  spa.jpg           "Spa Francorchamps full.jpg"

Track and layout together win over the track alone: "lemans full.jpg" is
used at Le Mans full, and "lemans.jpg" everywhere else on that circuit.
That matters where a circuit has several layouts - a backdrop from the
wrong one looks like the wrong track.

Any size; the picture is scaled to cover the widget without distortion.
Formats: .jpg .jpeg .png .webp .bmp. No file means no backdrop.

Brightness is a slider in the widget settings - a photo at full strength
buries the map that is drawn on top of it.
""",
}


def ensure_user_folders():
    """Создать папки для файлов человека и положить в каждую записку.

    Возвращает пути. Права только на чтение или диск занят — молчим:
    из-за отсутствующей папки для картинок программа падать не должна.
    """
    made = []
    for name, note in _NOTES.items():
        d = data_dir() / name
        try:
            d.mkdir(parents=True, exist_ok=True)
            f = d / "README.txt"
            if not f.exists():
                f.write_text(note, encoding="utf-8")
        except OSError:
            continue
        made.append(d)
    return made
