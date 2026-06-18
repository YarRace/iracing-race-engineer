"""Голосовой гоночный инженер: озвучивает события вслух (русский голос Irina).

Фоновый поток-воркер с очередью фраз — не блокирует live-цикл. Антиспам по
ключу события (одно и то же не повторяется подряд). Отключается IRE_VOICE=off;
при отсутствии pyttsx3/голоса молча выключается.
"""
import os
import queue
import threading


class VoiceEngineer:
    def __init__(self):
        self.enabled = os.environ.get("IRE_VOICE", "on").lower() != "off"
        self._q = queue.Queue()
        self._last = {}            # key -> последняя сказанная фраза (антиспам)
        if self.enabled:
            threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.setProperty("rate", 185)
            for v in eng.getProperty("voices"):     # предпочитаем русский голос
                if "RU" in v.id.upper() or "irina" in v.name.lower():
                    eng.setProperty("voice", v.id)
                    break
        except Exception:
            self.enabled = False
            return
        while True:
            text = self._q.get()
            try:
                eng.say(text)
                eng.runAndWait()
            except Exception:
                pass

    def say(self, text, key=None):
        """Поставить фразу в очередь. key — для антиспама (не повторять то же подряд)."""
        if not self.enabled or not text:
            return
        if key is not None:
            if self._last.get(key) == text:
                return
            self._last[key] = text
        self._q.put(text)


_FLAG_PHRASES = {
    "green": "Зелёный флаг, поехали",
    "yellow": "Жёлтый флаг, осторожно",
    "yellow_waving": "Жёлтый флаг, осторожно",
    "caution": "Полный жёлтый, машина безопасности",
    "caution_waving": "Полный жёлтый, машина безопасности",
    "blue": "Синий флаг, пропусти быстрых",
    "white": "Последний круг",
    "checkered": "Клетчатый флаг, финиш",
    "red": "Красный флаг, стоп",
    "black": "Чёрный флаг, в боксы",
    "repair": "Нужен ремонт, заезжай в бокс",
}


def announce(voice, race, strategy):
    """Озвучивает значимые изменения по снимкам race/strategy. Идемпотентно (антиспам)."""
    if race:
        flags = race.get("flags") or []
        flag_key = flags[0]["key"] if flags else "none"
        phrase = _FLAG_PHRASES.get(flag_key)
        if phrase:
            voice.say(phrase, key="flag")
        else:
            voice._last["flag"] = None          # сброс, чтобы новый флаг снова прозвучал
        for w in (race.get("warnings") or []):
            voice.say(w["label"], key="warn_" + w["key"])
    if strategy:
        lof = strategy.get("laps_on_fuel")
        if lof is not None and lof <= 2.0 and strategy.get("avg_burn"):
            voice.say("Внимание, топлива примерно на два круга", key="lowfuel")
