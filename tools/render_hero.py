"""Главная картинка сайта: оверлей так, как он выглядит поверх игры.

На сайтах RaceLab и Go Fast первое, что видишь, — настоящий скриншот продукта
в игре. У нас на странице был только текст, и рядом с ними она выглядела
пустой: непонятно даже, как это вообще выглядит.

Настоящий скриншот из iRacing взять неоткуда (папка screenshots пуста), да и
пересобирать его пришлось бы после каждой правки виджета. Поэтому собираем
из готовых снимков: фон рисуется тем же кодом, что в предпросмотре панели,
а виджеты раскладываются как в реальной раскладке — таблица слева сверху,
дельта по центру, ввод и карта снизу.

Запуск:
    python tools/render_hero.py                 docs/hero.png
    python tools/render_hero.py --width 2400    крупнее
"""
import argparse
import math
import pathlib
import sys

from PIL import Image, ImageDraw

# Вывод у нас русский, а консоль на чужой машине бывает не в UTF-8 — на
# раннере GitHub это cp437, и первая же печатная строка роняла скрипт с
# UnicodeEncodeError. Из-за этого проверка падала НА КАЖДОМ коммите, ещё до
# тестов, и заметить это было нечем: локально консоль в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "widgets"

# (файл, якорь, отступ по x, отступ по y, доля ширины кадра)
LAYOUT = [
    ("standings",  "tl", 0.030, 0.045, 0.300),
    ("deltabar",   "tc", 0.000, 0.045, 0.185),
    ("trackmap",   "tr", 0.030, 0.045, 0.175),
    ("fuel",       "tr", 0.030, 0.300, 0.150),
    ("inputs",     "bl", 0.030, 0.050, 0.150),
    ("racebar",    "bc", 0.000, 0.050, 0.330),
    ("relative",   "br", 0.030, 0.050, 0.230),
]


def backdrop(w, h):
    """Тот же закат, что в предпросмотре панели: небо, обочина, полотно."""
    im = Image.new("RGB", (w, h), "#2b3a55")
    d = ImageDraw.Draw(im)
    horizon = int(h * 0.42)

    for y in range(horizon):                       # градиент неба
        t = y / max(1, horizon)
        d.line([(0, y), (w, y)],
               fill=(int(43 + (201 - 43) * t), int(58 + (111 - 58) * t),
                     int(85 + (63 - 85) * t)))
    d.rectangle([0, horizon, w, h], fill="#3d4a35")

    road_top, road_bot = w * 0.16, w * 1.5         # полотно в перспективе
    d.polygon([((w - road_top) / 2, horizon), ((w + road_top) / 2, horizon),
               ((w + road_bot) / 2, h), ((w - road_bot) / 2, h)], fill="#2a2d33")
    for i in range(9):                             # разметка
        t0, t1 = i / 9.0, i / 9.0 + 0.045
        y0 = horizon + (h - horizon) * t0 ** 2
        y1 = horizon + (h - horizon) * t1 ** 2
        d.line([(w / 2, y0), (w / 2, y1)], fill=(255, 255, 255, 90),
               width=max(2, int(w / 500)))

    dark = Image.new("RGBA", (w, h), (0, 0, 0, 60))
    return Image.alpha_composite(im.convert("RGBA"), dark)


def place(canvas, name, anchor, dx, dy, frac):
    """Виджет на кадр по якорю. Пропорции сохраняются."""
    src = SHOTS / f"{name}.png"
    if not src.exists():
        return False
    im = Image.open(src).convert("RGBA")
    W, H = canvas.size
    tw = int(W * frac)
    im = im.resize((tw, max(1, int(im.height * tw / im.width))), Image.LANCZOS)

    ox = int(W * dx)
    oy = int(H * dy)
    x = ox if anchor[1] == "l" else (W - im.width - ox if anchor[1] == "r"
                                     else (W - im.width) // 2)
    y = oy if anchor[0] == "t" else (H - im.height - oy)
    canvas.alpha_composite(im, (x, y))
    return True


def main():
    ap = argparse.ArgumentParser(description="Главная картинка сайта")
    ap.add_argument("--out", default=str(ROOT / "docs" / "hero.png"))
    ap.add_argument("--width", type=int, default=1920)
    a = ap.parse_args()

    if not SHOTS.exists():
        print("  Нет снимков виджетов. Сначала: python tools/render_widgets.py")
        return 1

    w = a.width
    h = int(w * 9 / 16)
    canvas = backdrop(w, h)

    placed, missing = 0, []
    for name, anchor, dx, dy, frac in LAYOUT:
        if place(canvas, name, anchor, dx, dy, frac):
            placed += 1
        else:
            missing.append(name)

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, quality=92, optimize=True)
    print(f"  {out.name}: {w}×{h}, виджетов {placed}, {out.stat().st_size / 1024:.0f} КБ")
    if missing:
        print(f"  не нашлись снимки: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
