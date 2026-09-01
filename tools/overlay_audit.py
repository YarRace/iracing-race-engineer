"""Ревизия всех виджетов оверлея: кто падает, кто пустой, кому нужна работа.

Сорок два виджета глазами не пересмотришь, а «доводить до идеала» наугад —
значит полировать то, что и так неплохо, и не заметить сломанное. Скрипт
прогоняет КАЖДЫЙ виджет через три состояния и считает объективные признаки.

Три состояния, которые виджет обязан пережить:

  ПУСТО    — сим не запущен, все хранилища пустые. Виджет должен показать
             внятную заглушку, а не упасть и не нарисовать «None».
  ЧАСТИЧНО — сим есть, но данных мало: первый круг, нет соперников, нет
             износа. Самый частый случай в реальности и самый пропускаемый.
  ПОЛНО    — всё на месте.

Запуск:
    python tools/overlay_audit.py            сводка и список проблемных
    python tools/overlay_audit.py --all      таблица по всем виджетам
"""
import argparse
import inspect
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QPainter, QPixmap                            # noqa: E402
from PySide6.QtWidgets import QApplication                             # noqa: E402


def _load_fonts():
    """Без этого в безголовом режиме Qt не видит шрифтов и текст — квадраты."""
    from PySide6.QtGui import QFontDatabase
    for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf"):
        f = pathlib.Path(r"C:\Windows\Fonts") / name
        if f.exists():
            QFontDatabase.addApplicationFont(str(f))


class Cfg:
    """Конфиг-заглушка.

    Обычный класс, а НЕ MagicMock: мок на любой незнакомый вызов возвращает
    новый мок, и виджет падает на сравнении «мок > числа» — ошибка выглядит
    как баг виджета, хотя виновата заглушка. Проверено на Delta trace.
    """

    def geometry(self, key):
        return (0, 0, 400, 260)

    def widget_opt(self, key, name, default=None):
        return default

    def set_widget_opt(self, key, name, value):
        pass

    def set_geometry(self, *a):
        pass

    def opacity(self):
        return 1.0

    def edit_mode(self):
        return False


class Store:
    def __init__(self, data):
        self._d = data

    def get(self, k):
        return self._d.get(k, {})


def states():
    """Три набора данных: пусто, частично, полно."""
    empty = {}

    partial = {
        "live": {"speed": 42.0, "gear": 3, "throttle": 0.5, "brake": 0.0},
        "race": {"lap": 1, "position": 12},
        "standings": [],
        "relative": {},
        "strategy": {},
        "wear": {},
        "session": {},
        "result": {},
        "damage": {},
        "trackmap": {},
    }

    corner = {"l": 0.9, "m": 0.85, "r": 0.8, "min": 0.8}
    full = {
        "live": {"speed": 61.1, "gear": 5, "rpm": 6110, "shift_rpm": 7000,
                 "throttle": 0.9, "brake": 0.05, "steer": 0.2, "clutch": 0.0,
                 "lat_accel": 12.0, "long_accel": -4.0, "yaw_rate": 0.3,
                 "track_temp": 27.0, "air_temp": 21.0, "oil_temp": 95.0,
                 "water_temp": 88.0, "brake_bias": 54.5,
                 "tires": {c: {"tl": 82, "tm": 85, "tr": 88}
                           for c in ("LF", "RF", "LR", "RR")},
                 "shock_defl": {}},
        "race": {"lap": 12, "position": 8, "class_position": 3,
                 "gap_ahead": 1.2, "gap_behind": 0.8, "last_lap_time": 92.4,
                 "best_lap_time": 91.8, "predicted": 91.5, "delta_best": -0.3,
                 "rpm": 6110, "shift_rpm": 7000, "on_pit": True,
                 "car_left_right": 2, "flags": [{"key": "green", "label": "green"}],
                 "warnings": [{"key": "pit_limiter", "label": "pit limiter"}],
                 "energy_pct": 0.6, "deploy_pct": 0.75,
                 "wind_vel": 2.2, "wind_dir": 1.1, "humidity": 0.4,
                 "track_wetness": 1, "incidents": 4, "laps_total": 30},
        "standings": [
            {"pos": 7, "name": "Rival Ahead", "is_player": False,
             "best": 91.2, "last": 92.0, "gap": -1.2, "car": "Ferrari 499P",
             "manufacturer": "ferrari", "class_color": 0xF1C40F, "irating": 3200},
            {"pos": 8, "name": "Yaroslav Chizhov", "is_player": True,
             "best": 91.8, "last": 92.4, "gap": 0.0, "car": "Ferrari 499P",
             "manufacturer": "ferrari", "class_color": 0xF1C40F, "irating": 3287},
            {"pos": 9, "name": "Rival Behind", "is_player": False,
             "best": 92.5, "last": 92.9, "gap": 0.8, "car": "BMW M Hybrid",
             "manufacturer": "bmw", "class_color": 0xF1C40F, "irating": 3100},
        ],
        "relative": {"ahead": [{"name": "Rival Ahead", "gap": -1.2}],
                     "behind": [{"name": "Rival Behind", "gap": 0.8}]},
        "strategy": {"fuel": 42.5, "tank": 89.0, "avg_burn": 3.1, "last_burn": 3.0,
                     "avg_lap_time": 92.0, "laps_to_go": 18, "laps_on_fuel": 13.7,
                     "fuel_to_add": 14.2, "pit_needed_for_fuel": True,
                     "tire_min": 0.8, "tire_wear_per_lap": 0.012,
                     "tire_laps_left": 25.0, "change_tires": False,
                     "plan": {"stops": 1, "first_stop_lap": 20, "add_each": 30.0}},
        "wear": {c: dict(corner) for c in ("LF", "RF", "LR", "RR")},
        "session": {"type": "Race", "laps_total": 30, "laps_remain": 18,
                    "time_remain": 1680.0, "record": 91.0, "sof": 2800,
                    "time_of_day": "14:03"},
        "result": {"symptoms": {"inputs": {"trail_brake_pct": 22.0,
                                           "throttle_smoothness": 0.81},
                                "tire": {"front_rear_balance": 3.4}}},
        "damage": {"incidents": 4, "team": []},
        "trackmap": {"points": [{"x": i, "y": (i * 7) % 100, "pct": i / 100.0}
                                for i in range(100)], "official": True},
    }
    return [("ПУСТО", empty), ("ЧАСТИЧНО", partial), ("ПОЛНО", full)]


def probe(W, data):
    """Один прогон виджета. Возвращает None если всё хорошо, иначе текст ошибки."""
    try:
        w = W(Store(data), Cfg())
        w.resize(*W.DEFAULT)
        pm = QPixmap(w.size())
        pm.fill()
        p = QPainter(pm)
        try:
            if hasattr(w, "rows"):
                w.rows()
            w.draw(p)
        finally:
            p.end()
        return None
    except Exception as e:                                   # noqa: BLE001 — ловим всё
        return f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description="Ревизия виджетов оверлея")
    ap.add_argument("--all", action="store_true", help="показать таблицу по всем")
    a = ap.parse_args()

    QApplication([])
    _load_fonts()
    from overlay.widgets import WIDGETS

    rows = []
    for W in WIDGETS:
        title = getattr(W, "TITLE", W.__name__)
        try:
            lines = len(inspect.getsource(W).splitlines())
        except OSError:
            lines = 0
        fails = {}
        for name, data in states():
            err = probe(W, data)
            if err:
                fails[name] = err
        rows.append({
            "title": title,
            "key": getattr(W, "KEY", "?"),
            "group": getattr(W, "GROUP", "?"),
            "lines": lines,
            "settings": "extra_settings" in W.__dict__,
            "cycle": hasattr(W, "CYCLE_OPT"),
            "fails": fails,
        })

    broken = [r for r in rows if r["fails"]]
    thin = [r for r in rows if not r["fails"] and r["lines"] < 20]

    print(f"\nВиджетов: {len(rows)}")
    print(f"Падают хотя бы в одном состоянии: {len(broken)}")
    print(f"Тоньше 20 строк (кандидаты в заглушки): {len(thin)}")
    print(f"Со своими настройками (не общими): {sum(1 for r in rows if r['settings'])}")

    if broken:
        print("\n" + "─" * 70)
        print("  ПАДАЮТ — чинить в первую очередь")
        print("─" * 70)
        for r in sorted(broken, key=lambda r: -len(r["fails"])):
            print(f"\n  {r['title']}  [{r['key']}, {r['lines']} строк]")
            for state, err in r["fails"].items():
                print(f"      {state}: {err[:110]}")

    if thin:
        print("\n" + "─" * 70)
        print("  ТОНКИЕ — проверить, хватает ли им содержания")
        print("─" * 70)
        for r in sorted(thin, key=lambda r: r["lines"]):
            mark = " ⚙" if r["settings"] else ""
            print(f"  {r['lines']:3} строк  {r['title']:22} [{r['group']}]{mark}")

    if a.all:
        print("\n" + "─" * 70)
        print("  ВСЕ ВИДЖЕТЫ")
        print("─" * 70)
        for r in sorted(rows, key=lambda r: (r["group"], -r["lines"])):
            state = "ПАДАЕТ" if r["fails"] else "ок"
            print(f"  {r['lines']:4} строк  {state:7} {r['title']:22} [{r['group']}]")

    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
