"""Иконка приложения — рисуется кодом, а не лежит картинкой.

Своя, а не взятая: чужой значок в приложении, которое метит в продажу, —
это чужой товарный знак. Рисуем сами из того же, что и весь интерфейс:
клетчатый флаг на тёмном фоне и синий акцент проекта.

Кодом, а не файлом в репозитории, по той же причине, что и фон
предпросмотра: картинку пришлось бы где-то взять, а сгенерированная
переделывается одной правкой числа.

.ico хранит НЕСКОЛЬКО размеров в одном файле, и Windows берёт нужный сам:
16 в списке задач, 32 в проводнике, 256 в крупных значках. Один размер,
растянутый системой, выглядит мылом — ровно на этом отличают самоделку.

Запуск:
    python tools/make_icon.py            → docs/icon.ico  (+ icon.png)
"""
import argparse
import pathlib
import sys

# Вывод у нас русский, а консоль на чужой машине бывает не в UTF-8 — на
# раннере GitHub это cp437, и первая же печатная строка роняла скрипт с
# UnicodeEncodeError. Из-за этого проверка падала НА КАЖДОМ коммите, ещё до
# тестов, и заметить это было нечем: локально консоль в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]

BG = (14, 17, 22)          # фон приложения
ACCENT = (62, 166, 255)    # синий проекта
WHITE = (232, 234, 237)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size, accent_bar=True):
    """Один кадр иконки. Всё в долях от size — иначе на 16 пикселях каша."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), BG + (255,))
    d = ImageDraw.Draw(img)

    r = max(2, round(size * 0.18))
    d.rounded_rectangle([0, 0, size - 1, size - 1], r, fill=BG + (255,))

    # Клетчатый флаг: 4×4 клетки на две трети значка, по центру.
    n = 4
    pad = size * 0.22
    cell = (size - pad * 2) / n
    for row in range(n):
        for col in range(n):
            if (row + col) % 2:
                continue
            x0 = pad + col * cell
            y0 = pad + row * cell
            d.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=WHITE + (255,))

    # Синяя полоса снизу — тот же акцент, что и в интерфейсе. На мелких
    # размерах она съедает флаг, поэтому её там нет.
    if accent_bar and size >= 32:
        h = max(2, round(size * 0.075))
        d.rectangle([pad, size - pad * 0.55, size - pad, size - pad * 0.55 + h],
                    fill=ACCENT + (255,))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "icon.ico"))
    args = ap.parse_args()

    try:
        from PIL import Image                                     # noqa: F401
    except ImportError:
        print("  нужен Pillow:  pip install pillow")
        return 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw(s) for s in SIZES]
    # Pillow сам разложит переданные размеры внутрь .ico
    frames[-1].save(out, format="ICO",
                    sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    png = out.with_suffix(".png")
    frames[-1].save(png)
    print(f"  {out}  ({out.stat().st_size // 1024} КБ, размеры: "
          f"{', '.join(str(s) for s in SIZES)})")
    print(f"  {png}   — для сайта и README")
    return 0


if __name__ == "__main__":
    sys.exit(main())
