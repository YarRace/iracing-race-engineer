"""Снимки ПАНЕЛИ настроек для сайта.

Витрина (`render_widgets.py`) отвечает на вопрос «что видно в игре». На вопрос
«а настраивать это как» она не отвечает вовсе — а у обоих конкурентов именно
скриншот окна настроек занимает половину страницы. Человек покупает не
виджеты, а то, насколько просто их подогнать под себя.

Панель снимается с ВРЕМЕННЫМ конфигом, а не с рабочим. Две причины:
снимок должен быть одинаковым при каждом запуске (иначе диффы в git на
каждую перестановку виджета), и в него не должна попадать личная раскладка.

Запуск:
    python tools/render_panel.py                  → docs/panel/
"""
import argparse
import json
import os
import pathlib
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

WIN_FONTS = pathlib.Path(r"C:\Windows\Fonts")
# Без ЯВНОЙ загрузки offscreen-Qt не видит ни одного системного шрифта и
# рисует каждый символ квадратом. Emoji и Symbol нужны отдельно: «🏁», «＋»,
# «🗑» живут не в Segoe UI, и без них шапка панели — ряд пустых рамок.
FONT_FILES = ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf",
              "seguiemj.ttf", "seguisym.ttf", "arial.ttf", "arialbd.ttf")

# (файл, что показываем, подпись под снимком)
SHOTS = [
    ("panel.png", "fuel",
     "Pick an overlay on the left, watch it change in the middle, tune it on "
     "the right. No need to alt-tab into the game to see the result."),
    ("panel-map.png", "trackmap",
     "The preview is the real widget on the real data — not a picture of one."),
    ("panel-log.png", "laplog",
     "Every widget carries its own settings, its own presets and a reset "
     "back to factory."),
]


def load_fonts():
    from PySide6.QtGui import QFontDatabase
    got = []
    for name in FONT_FILES:
        f = WIN_FONTS / name
        if f.exists() and QFontDatabase.addApplicationFont(str(f)) != -1:
            got.append(name)
    return got


def build_panel(cfg_path):
    """Панель на временном конфиге с показательной, но честной раскладкой."""
    from overlay.config import Config
    from overlay.panel import ControlPanel
    from overlay.store import Store
    from overlay.widgets import WIDGETS

    cfg = Config(str(cfg_path))
    for key in ("fuel", "delta", "standings", "relative", "trackmap"):
        cfg.set_enabled(key, True)
    for key in ("fuel", "delta", "trackmap"):
        cfg.set_favourite(key, True)
    panel = ControlPanel(Store(), cfg, WIDGETS)
    # Боевые оверлеи в снимке не нужны: это отдельные окна поверх экрана,
    # они всё равно не попадут в grab() панели, но будут висеть без дела.
    for w in list(panel.widgets.values()):
        w.hide()
    return panel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "panel"))
    ap.add_argument("--width", type=int, default=1180)
    ap.add_argument("--height", type=int, default=760)
    args = ap.parse_args()

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    fonts = load_fonts()
    print("  шрифты:", ", ".join(fonts) or "НИ ОДНОГО (будут квадраты)")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        panel = build_panel(pathlib.Path(tmp) / "shot.json")
        panel.resize(args.width, args.height)
        panel.show()
        app.processEvents()

        index, failed = [], []
        for fname, key, caption in SHOTS:
            try:
                panel.select(key)
                app.processEvents()
                path = out / fname
                if not panel.grab().save(str(path)):
                    raise OSError(f"не удалось записать {path}")
                index.append({"file": fname, "key": key, "caption": caption})
            except Exception as exc:                            # noqa: BLE001
                failed.append((fname, f"{type(exc).__name__}: {exc}"))
        panel.close()

    (out / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in out.glob("*.png"))
    print(f"  снято: {len(index)} из {len(SHOTS)}")
    for name, err in failed:
        print(f"  ПРОВАЛ {name}: {err}")
    print(f"  каталог: {out}")
    print(f"  вес: {total // 1024} КБ, опись в index.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
