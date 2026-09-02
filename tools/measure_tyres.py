"""Проверка порогов Tyre Tool по накопленным .ibt: держатся или поехали.

ЗАЧЕМ. Пороги в `metrics/tire.py` (CAMBER_NOISE, CAMBER_MUCH) и
`metrics/tyres.py` (CROWN_BAND) измерены один раз, руками, и повторить то
измерение было нечем. Из-за этого в шапке `tyres.py` полгода стояли числа,
посчитанные вместе с сессиями, где машина не выезжала из боксов, — а тот же
модуль ниже велит такие выбрасывать. Заметить это без инструмента нельзя.

И главное: порог не универсален. CAMBER_MUCH срабатывает на 2% колёс
Ferrari 499P и на 39% колёс Super Formula Lights. Появится третья машина —
никто не заметит, что на ней полоса означает совсем другое, пока не запустит
эту команду.

ЧТО ВАЖНО В УСТРОЙСТВЕ. Соглашение о кромках берётся из `tire.edges`, а
пороги — из самих модулей. Инструмент, который переписывает соглашение у
себя, через месяц начнёт уверенно мерить не то — ровно это уже случилось
однажды, когда внутренняя и внешняя кромки оказались перепутаны.

Запуск:
    python tools/measure_tyres.py                    все .ibt из папки iRacing
    python tools/measure_tyres.py --dir путь         своя папка
    python tools/measure_tyres.py --min-kmh 80       строже отбор «ездил»
"""
import argparse
import collections
import glob
import os
import pathlib
import statistics
import sys

# Вывод у нас русский, а консоль на чужой машине бывает не в UTF-8 — на
# раннере GitHub это cp437, и первая же печатная строка роняла скрипт с
# UnicodeEncodeError. Из-за этого проверка падала НА КАЖДОМ коммите, ещё до
# тестов, и заметить это было нечем: локально консоль в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_DIR = pathlib.Path.home() / "Documents" / "iRacing" / "telemetry"
# Ниже этого максимума за сессию машина из боксов не выезжала. Такие сессии
# дают перекос кромок ровно 0.0 и тянут все процентили к нулю.
MIN_KMH = 60.0


def _pct(v, q):
    v = sorted(v)
    return v[int(q * (len(v) - 1))] if v else float("nan")


def _row(name, v):
    if not v:
        return f"  {name:<26}       — нет данных"
    return (f"  {name:<26}{len(v):>5}"
            f"{_pct(v, .05):>8.2f}{_pct(v, .25):>8.2f}{_pct(v, .5):>8.2f}"
            f"{_pct(v, .75):>8.2f}{_pct(v, .95):>8.2f}"
            f"{statistics.fmean(v):>9.2f}{statistics.pstdev(v):>7.2f}")


def _head(title):
    print(f"\n{title}")
    print(f"  {'набор':<26}{'n':>5}{'p5':>8}{'p25':>8}{'p50':>8}"
          f"{'p75':>8}{'p95':>8}{'сред':>9}{'сигма':>7}")


def measure(folder, min_kmh):
    """Читает все .ibt и возвращает наблюдения по колесо-сессиям."""
    import irsdk

    from config import channels
    from ire.metrics.tire import edges

    files = sorted(glob.glob(os.path.join(str(folder), "*.ibt")))
    rows, skipped = [], []
    for f in files:
        ibt = irsdk.IBT()
        try:
            ibt.open(f)

            def avg(name):
                v = [x for x in (ibt.get_all(name) or [])
                     if isinstance(x, (int, float)) and x > 0]
                return sum(v) / len(v) if v else None

            sp = [x for x in (ibt.get_all("Speed") or []) if isinstance(x, (int, float))]
            top = max(sp) * 3.6 if sp else 0.0
            car = os.path.basename(f).split("_")[0]
            if top < min_kmh:
                skipped.append((os.path.basename(f), top))
                continue

            for corner in ("LF", "RF", "LR", "RR"):
                # Имена каналов — из channels, а не собранные строкой: там же
                # лежит запасной набор для машин без поверхностных каналов.
                names = channels.TIRE_TEMP[corner]
                l, m, r = (avg(n) for n in names)
                if None in (l, m, r):
                    names = channels.TIRE_TEMP_CARCASS[corner]
                    l, m, r = (avg(n) for n in names)
                if None in (l, m, r):
                    continue
                inner, outer = edges(corner, l, r)
                rows.append({"car": car, "corner": corner, "top_kmh": top,
                             "camber": inner - outer,
                             "crown": m - (inner + outer) / 2})
        except Exception as e:                                   # noqa: BLE001
            print(f"  пропуск {os.path.basename(f)}: {type(e).__name__}: {e}")
        finally:
            try:
                ibt.close()
            except Exception:                                    # noqa: BLE001
                pass
    return files, rows, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--min-kmh", type=float, default=MIN_KMH,
                    help="ниже этого максимума считаем, что машина не выезжала")
    a = ap.parse_args()

    from ire.metrics.tire import CAMBER_MUCH, CAMBER_NOISE
    from ire.metrics.tyres import CROWN_BAND

    folder = pathlib.Path(a.dir)
    if not folder.exists():
        print(f"  Папки нет: {folder}")
        print("  Телеметрию iRacing пишет в Documents\\iRacing\\telemetry —")
        print("  включи запись в настройках сима, проедь заезд и запусти снова.")
        return 1

    files, rows, skipped = measure(folder, a.min_kmh)
    print(f"  Папка: {folder}")
    print(f"  Файлов: {len(files)}   отброшено (не выезжал): {len(skipped)}")
    if not rows:
        print("  Ни одной пригодной сессии — мерить нечего.")
        return 1

    cars = collections.Counter(r["car"] for r in rows)
    print(f"  Колесо-сессий: {len(rows)}   машин: {len(cars)}")
    for car, n in cars.most_common():
        print(f"      {car:<26}{n // 4:>3} сессий")

    if len(cars) < 3:
        # Это не придирка: на двух машинах, каждая из которых ездила по одной
        # трассе, машину от трассы не отличить никакой статистикой.
        print("\n  ВНИМАНИЕ: машин меньше трёх. Менять пороги по таким данным")
        print("  нельзя — эффект машины неотличим от эффекта трассы.")

    for field, title in (("camber", "РАЗВАЛ: внутренняя минус внешняя кромка, °C"),
                         ("crown", "КОРОНА: середина минус кромки, °C")):
        _head(title)
        print(_row("все машины", [r[field] for r in rows]))
        for car in cars:
            print(_row(car, [r[field] for r in rows if r["car"] == car]))
        for end, label in (("F", "перед"), ("R", "зад")):
            v = [r[field] for r in rows if r["corner"][1] == end]
            print(_row(f"— {label}", v))

    print(f"\nКАК ЧАСТО СРАБАТЫВАЮТ НЫНЕШНИЕ ПОРОГИ "
          f"(шум {CAMBER_NOISE}, много {CAMBER_MUCH}, корона {CROWN_BAND})")
    print(f"  {'машина':<26}{'n':>5}{'not_enough':>12}{'even':>8}"
          f"{'working':>9}{'too_much':>10}{'корона':>9}")
    for car in cars:
        v = [r for r in rows if r["car"] == car]
        ne = sum(1 for r in v if r["camber"] < -CAMBER_NOISE)
        tm = sum(1 for r in v if r["camber"] > CAMBER_MUCH)
        wk = sum(1 for r in v if CAMBER_NOISE < r["camber"] <= CAMBER_MUCH)
        cr = sum(1 for r in v if abs(r["crown"]) > CROWN_BAND)
        n = len(v)
        print(f"  {car:<26}{n:>5}{ne / n:>11.0%}{(n - ne - tm - wk) / n:>8.0%}"
              f"{wk / n:>9.0%}{tm / n:>10.0%}{cr / n:>9.0%}")

    # Двадцатикратная разница в частоте вердикта означает, что порог описывает
    # машину, а не физику. Сказать об этом должен инструмент, а не человек,
    # который будет сравнивать столбцы глазами.
    hits = {car: sum(1 for r in rows if r["car"] == car and r["camber"] > CAMBER_MUCH)
                 / max(1, sum(1 for r in rows if r["car"] == car))
            for car in cars}
    if len(hits) > 1 and max(hits.values()) > 4 * max(min(hits.values()), 0.01):
        lo = min(hits, key=hits.get)
        hi = max(hits, key=hits.get)
        print(f"\n  ПОРОГ ПОЕХАЛ: CAMBER_MUCH срабатывает на {hits[hi]:.0%} колёс "
              f"{hi}\n  и на {hits[lo]:.0%} колёс {lo}. Это разница в машинах, "
              f"а не в сетапе.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
