"""Задача 7: запись реальной фикстуры стинта из живого SDK.

Запускать С ЗАПУЩЕННЫМ iRacing. Выехать на трассу, проехать 5-10 чистых кругов,
заехать в бокс → файл закроется автоматически. Перезаписывает синтетическую
tests/fixtures/sample_stint.jsonl реальными кадрами.

Run: python spikes/record_stint.py
"""
import os
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))   # пакет ire
sys.path.insert(0, _ROOT)                          # пакет config (в корне)

import irsdk
from ire.collector.live_state import live_frame, is_on_track
from ire.collector.stint_recorder import StintDetector, StintWriter

OUT = "tests/fixtures/sample_stint.jsonl"


def main():
    ir = irsdk.IRSDK()
    assert ir.startup(), "iRacing не запущен / SDK недоступен"
    det = StintDetector()
    writer = None
    n = 0
    print("Жду выезда на трассу… (Ctrl+C — отмена)")
    try:
        while True:
            ir.freeze_var_buffer_latest()
            state = det.update(on_track=is_on_track(ir))
            if state == "running":
                if writer is None:
                    writer = StintWriter(OUT)
                    print(f"Стинт начат → пишу {OUT}")
                writer.write(live_frame(ir))
                n += 1
                if n % 300 == 0:
                    print(f"  …{n} кадров")
            elif state == "closed":
                if writer:
                    writer.close()
                print(f"Стинт закрыт. Записано {n} кадров → {OUT}")
                break
            time.sleep(1 / 60)
    finally:
        ir.shutdown()


if __name__ == "__main__":
    main()
