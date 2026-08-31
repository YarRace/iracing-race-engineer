"""Прямое чтение телеметрии iRacing В ПРОЦЕССЕ ОВЕРЛЕЯ — для масляно-плавных
быстрых виджетов (Race bar, Inputs, дельта, шифт), без HTTP-прыжка.

iRacing публикует телеметрию в общей памяти ~60 раз/сек. Читаем её напрямую в
фоновом потоке (как это делает run.py, но здесь — прямо в оверлее) и держим свежий
снимок «быстрых» каналов. Виджеты берут значения отсюда; если iRacing не подключён
(`ok=False`) — откатываются на данные по HTTP (Store), ничего не ломается.

Несколько читателей общей памяти одновременно — норма: так же читают RaceLab,
SimHub и наш бэкенд. Поток демон, ест копейки CPU.
"""
from __future__ import annotations

import threading
import time

# «быстрые» каналы (меняются каждый кадр) → как зовём у себя : канал iRacing SDK
_CHANNELS = {
    "speed": "Speed", "gear": "Gear", "rpm": "RPM",
    "throttle": "Throttle", "brake": "Brake", "clutch": "Clutch",
    "steer": "SteeringWheelAngle", "shift_rpm": "PlayerCarSLShiftRPM",
    "delta_best": "LapDeltaToBestLap", "on_pit": "OnPitRoad",
}

_FEED = None


def start_feed():
    """Поднять чтение живой телеметрии. Зовёт ТОЛЬКО оверлей при запуске."""
    global _FEED
    if _FEED is None:
        _FEED = Telemetry()
        _FEED.start()
    return _FEED


def feed():
    """Живая телеметрия, если её кто-то поднял. Иначе None.

    Раньше фид поднимался ЛЕНИВО, при первом же обращении из виджета. Из-за
    этого любой тест, который дёргал fastval(), запускал фоновый поток к
    общей памяти iRacing — и дальше отвечал по-разному в зависимости от
    того, открыт ли сейчас сим. Набор тестов падал на чужой машине с
    запущенной игрой и проходил на пустой; поймать такое почти невозможно.

    Теперь поднимает фид только тот, кому он нужен, — оверлей в
    `store.start()`. Всё остальное получает None и работает по HTTP.
    """
    return _FEED


class Telemetry:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()
        self._run = True
        self.ok = False                     # подключены ли к живой сессии ПРЯМО СЕЙЧАС

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._run = False

    def get(self, name, default=None):
        with self._lock:
            v = self._d.get(name)
        return v if v is not None else default

    def _loop(self):
        try:
            import irsdk
        except Exception:
            return                          # нет пакета — молча работаем без прямого чтения
        ir = irsdk.IRSDK()
        while self._run:
            try:
                if not (ir.is_initialized and ir.is_connected):
                    ir.startup()
                    if not (ir.is_initialized and ir.is_connected):
                        self.ok = False
                        time.sleep(0.5)     # iRacing не запущена — ждём спокойно
                        continue
                ir.freeze_var_buffer_latest()
                snap = {}
                for name, ch in _CHANNELS.items():
                    try:
                        snap[name] = ir[ch]
                    except Exception:
                        snap[name] = None
                with self._lock:
                    self._d = snap
                self.ok = True
            except Exception:
                self.ok = False
            time.sleep(1 / 60)              # ~60 раз/сек — в такт с симом
