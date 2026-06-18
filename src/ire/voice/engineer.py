"""Голосовой гоночный инженер «Дмитрий»: озвучивает события вслух.

Основной голос — edge-tts «ru-RU-DmitryNeural» (нейросетевой мужской русский,
нужен интернет). Если edge недоступен (нет сети/пакета) — авто-откат на системный
SAPI-голос (pyttsx3), чтобы инженер не замолчал. Фоновый поток-воркер + очередь,
не блокирует live-цикл. Антиспам по ключу. Отключается IRE_VOICE=off.
"""
import os
import queue
import tempfile
import threading

DEFAULT_VOICE = "ru-RU-DmitryNeural"


class VoiceEngineer:
    def __init__(self):
        self.enabled = os.environ.get("IRE_VOICE", "on").lower() != "off"
        self.voice_name = os.environ.get("IRE_VOICE_NAME", DEFAULT_VOICE)
        self.volume = os.environ.get("IRE_VOICE_VOLUME", "-75%")   # тише
        self._q = queue.Queue()
        self._last = {}            # key -> последняя сказанная фраза (антиспам)
        if self.enabled:
            threading.Thread(target=self._worker, daemon=True).start()

    def _speak_edge(self, text):
        """edge-tts (Dmitry) → mp3 → проигрывание. Бросает исключение при ошибке/без сети."""
        import asyncio
        import edge_tts
        from playsound import playsound
        path = os.path.join(tempfile.gettempdir(), "ire_voice.mp3")
        asyncio.run(edge_tts.Communicate(text, self.voice_name, volume=self.volume).save(path))
        playsound(path)
        try:
            os.remove(path)
        except OSError:
            pass

    def _init_sapi(self):
        """Запасной системный голос (pyttsx3), если edge недоступен."""
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.setProperty("rate", 185)
            for v in eng.getProperty("voices"):
                if "RU" in v.id.upper() or "irina" in v.name.lower():
                    eng.setProperty("voice", v.id)
                    break
            return eng
        except Exception:
            return None

    def _worker(self):
        sapi = None
        while True:
            text = self._q.get()
            try:
                self._speak_edge(text)              # основной путь — Дмитрий
            except Exception:
                if sapi is None:                    # откат на системный голос
                    sapi = self._init_sapi()
                if sapi is not None:
                    try:
                        sapi.say(text)
                        sapi.runAndWait()
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
