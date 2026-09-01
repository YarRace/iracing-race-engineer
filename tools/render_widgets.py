"""Снимки всех виджетов на демо-данных — для витрины сайта.

У RaceLab на сайте карусель из 29 оверлеев: слева список, справа живой рендер
выбранного. Наш сайт показывал только текст, и рядом с ними выглядел пустым.

Снимать вручную 42 виджета в игре — работа на вечер, и её пришлось бы
повторять после каждой правки. Скрипт делает это за минуту и всегда на одних
и тех же данных, поэтому картинки сопоставимы между собой.

Данные берутся из overlay/demo.py — они синтетические и подписаны как
таковые. Момент круга фиксирован (--at), иначе снимки менялись бы от запуска
к запуску и git видел бы изменения там, где ничего не менялось.

Запуск:
    python tools/render_widgets.py                  в docs/widgets/
    python tools/render_widgets.py --out путь       свой каталог
    python tools/render_widgets.py --at 24          другой момент круга
    python tools/render_widgets.py --scale 2        для экранов с ретиной
"""
import argparse
import json
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap                 # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402


def load_fonts():
    """Подсунуть Qt системные шрифты.

    В безголовом режиме (QT_QPA_PLATFORM=offscreen) Qt на Windows не видит
    НИ ОДНОГО шрифта — QFontDatabase.families() пуст, и весь текст рисуется
    квадратами-заглушками. Для картинок, которые пойдут на сайт, это негодно.
    Грузим файлы явно; отсутствие какого-то из них не смертельно.
    """
    from PySide6.QtGui import QFontDatabase
    got = []
    for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuisb.ttf",
                 "arial.ttf", "arialbd.ttf"):
        p = pathlib.Path(r"C:\Windows\Fonts") / name
        if p.exists() and QFontDatabase.addApplicationFont(str(p)) != -1:
            got.append(name)
    return got


class Cfg:
    """Настройки по умолчанию: снимок должен показывать виджет «из коробки»."""

    def geometry(self, key):
        return None

    def widget_opt(self, key, name, default=None):
        return default

    def set_widget_opt(self, *a):
        pass

    def set_geometry(self, *a):
        pass

    def opacity(self):
        return 1.0

    def edit_mode(self):
        return False


def render(cls, store, config, scale):
    """Виджет ровно такой, каким он будет на экране — со своей подложкой.

    Раньше снималось голое `draw()`, а подложку рисует `paintEvent`, — и в
    галерее виджет выглядел иначе, чем в игре: без тёмного скруглённого
    прямоугольника, на котором он на самом деле лежит. На тёмных страницах
    сайта и панели это почти не видно, но галерея для того и нужна, чтобы
    узнать виджет в лицо, а показывала она не его.

    Подложка полупрозрачная, так что снимок по-прежнему ложится на любой
    фон, — и заодно перестаёт зависеть от того, светлый он или тёмный.
    """
    w = cls(store, config)
    w.resize(*cls.DEFAULT)
    pm = QPixmap(int(cls.DEFAULT[0] * scale), int(cls.DEFAULT[1] * scale))
    pm.setDevicePixelRatio(scale)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    try:
        w._bg(p)
        w.draw(p)
    finally:
        p.end()
        w.deleteLater()
    return pm


# Виджеты, которым общий момент круга не подходит: ключ → секунда круга.
AT = {"sectors": 78.0}       # два сектора позади, третий идёт


def main():
    ap = argparse.ArgumentParser(description="Снимки виджетов на демо-данных")
    ap.add_argument("--out", default=str(ROOT / "docs" / "widgets"))
    ap.add_argument("--at", type=float, default=18.0,
                    help="секунда круга: фиксирована, чтобы снимки не «дрожали» между запусками")
    ap.add_argument("--scale", type=float, default=2.0)
    a = ap.parse_args()

    QApplication([])
    fonts = load_fonts()
    from overlay.demo import DemoFeed
    from overlay.panel import STARTERS
    from overlay.widgets import WIDGETS

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # Момент круга задаём смещением «начала» назад: поток считает время сам,
    # и без фиксации каждый запуск давал бы другую картинку.
    import time
    config = Cfg()

    def feed(at):
        return DemoFeed(t0=time.monotonic() - at)

    store = feed(a.at)

    index, failed = [], []
    for cls in WIDGETS:
        name = getattr(cls, "KEY", cls.__name__)
        try:
            # Виджету секторов на 18-й секунде круга сказать нечего: первый
            # сектор ещё не закончен, и в галерее он выглядел бы пустым, хотя
            # исправен. Снимаем его позже по кругу — данные те же, демо то же,
            # просто момент, в который виджет что-то показывает.
            pm = render(cls, feed(AT.get(name, a.at)) if name in AT else store,
                        config, a.scale)
            path = out / f"{name}.png"
            pm.save(str(path))
            index.append({
                "key": name,
                "title": getattr(cls, "TITLE", name),
                "group": getattr(cls, "GROUP", "solo"),
                "size": list(cls.DEFAULT),
                "file": path.name,
                "doc": getattr(cls, "BLURB", ""),      # английская подпись
                # В каких готовых наборах он стоит. Витрина без этого отвечает
                # «вот такой виджет есть», но не отвечает на главный вопрос —
                # нужен ли он мне и когда его включают.
                "sets": [n for n, keys in STARTERS if name in keys],
            })
        except Exception as e:                                   # noqa: BLE001
            failed.append((name, f"{type(e).__name__}: {e}"))

    (out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum((out / i["file"]).stat().st_size for i in index)
    print(f"  шрифты: {', '.join(fonts) or 'НЕ НАЙДЕНЫ — текст будет квадратами'}")
    print(f"  снято: {len(index)} из {len(WIDGETS)}")
    print(f"  каталог: {out}")
    print(f"  вес: {total / 1024:.0f} КБ, опись в index.json")
    if failed:
        print("\n  НЕ СНЯЛИСЬ:")
        for n, err in failed:
            print(f"    {n}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
