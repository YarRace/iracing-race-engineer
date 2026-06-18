#!/usr/bin/env python3
"""Дмитрий — голосовой гоночный ассистент (Jarvis-style).

Активация: кнопка 20 на руле MOZA (pygame index 19) — нажал/начал говорить,
нажал ещё раз — закрыл вопрос. Цепочка:
  кнопка → запись микрофона → Whisper (STT) → роутинг →
    • команда («открой телеграм», «следующий трек», «пауза», «громче/тише») → выполнить;
    • вопрос → Ollama (qwen2.5) с КОНТЕКСТОМ гонки из дашборда localhost:8000 → ответ;
  → голос Дмитрия (edge-tts) озвучивает.

Запуск: python dmitry.py   (или ярлык). Дашборд (run.py) лучше тоже запущен —
тогда Дмитрий знает твою позицию, топливо, разрывы и т.д.
"""
import os
import sys
import time
import threading

_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _ROOT)


def _add_nvidia_dll_dirs():
    """CUDA-DLL из pip-пакетов nvidia-* в путь поиска (как в voice_input)."""
    try:
        import nvidia
        bases = list(getattr(nvidia, "__path__", []))
    except Exception:
        return
    for base in bases:
        try:
            subs = os.listdir(base)
        except Exception:
            continue
        for name in subs:
            d = os.path.join(base, name, "bin")
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


_add_nvidia_dll_dirs()

import asyncio
import subprocess
import numpy as np
import sounddevice as sd
import pygame
import httpx
import edge_tts
from playsound import playsound
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
LANGUAGE = "ru"
WHISPER_MODEL = os.environ.get("DMITRY_WHISPER", "small")   # small=быстро; large-v3=точно
BUTTON_INDEX = int(os.environ.get("DMITRY_BUTTON", "19"))   # кнопка 20 на руле = индекс 19
VOICE = "ru-RU-DmitryNeural"
VOL_FILE = os.path.join(_ROOT, "dmitry_volume.txt")   # запоминаем громкость между запусками


def _load_volume():
    try:
        return open(VOL_FILE, encoding="utf-8").read().strip() or "-75%"
    except Exception:
        return os.environ.get("DMITRY_VOLUME", "-75%")


VOLUME = _load_volume()


def _vol_num():
    try:
        return int(VOLUME.replace("%", "").replace("+", ""))
    except Exception:
        return -75


def _set_volume(pct):
    global VOLUME
    pct = max(-95, min(0, int(pct)))
    VOLUME = "+0%" if pct == 0 else f"{pct}%"
    try:
        open(VOL_FILE, "w", encoding="utf-8").write(VOLUME)
    except Exception:
        pass
OLLAMA = os.environ.get("IRE_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("IRE_OLLAMA_MODEL", "qwen2.5:7b")
DASH = "http://localhost:8000"

SYSTEM = (
    "Ты — Дмитрий, гоночный инженер и голосовой ассистент в симуляторе iRacing. "
    "Отвечай КОРОТКО (1-2 фразы), по-русски, разговорно и по делу. Если есть данные "
    "гонки — используй их. На общие вопросы отвечай как обычный помощник."
)

is_recording = False
audio_frames = []
model = None
_lock = threading.Lock()


def speak(text):
    try:
        path = os.path.join(os.environ.get("TEMP", "."), "dmitry_say.mp3")
        asyncio.run(edge_tts.Communicate(text, VOICE, volume=VOLUME).save(path))
        playsound(path)
        os.remove(path)
    except Exception as e:
        print("TTS ошибка:", e, flush=True)


def load_model():
    global model
    print(f"Загружаю Whisper ({WHISPER_MODEL})…", flush=True)
    try:
        m = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
        list(m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language=LANGUAGE)[0])
        print("Whisper готов (GPU).", flush=True)
    except Exception as e:
        print(f"GPU недоступен ({e}); CPU.", flush=True)
        m = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        list(m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language=LANGUAGE)[0])
        print("Whisper готов (CPU).", flush=True)
    model = m


def transcribe(frames):
    audio = np.clip(np.concatenate(frames, axis=0).reshape(-1).astype(np.float32), -1, 1)
    segments, _ = model.transcribe(audio, language=LANGUAGE, condition_on_previous_text=False)
    return "".join(s.text for s in segments).strip()


def audio_callback(indata, frames, t, status):
    if is_recording:
        audio_frames.append(indata.copy())


# ---------- контекст гонки из дашборда ----------
def race_context():
    parts = []
    try:
        st = httpx.get(f"{DASH}/api/strategy", timeout=1).json()
        if st.get("avg_burn"):
            parts.append(f"топливо {st.get('fuel')}л, расход {st.get('avg_burn')}л/круг, "
                         f"хватит на {st.get('laps_on_fuel')} кругов, долить {st.get('fuel_to_add')}л")
    except Exception:
        pass
    try:
        r = httpx.get(f"{DASH}/api/race", timeout=1).json()
        if r.get("position"):
            parts.append(f"позиция P{r.get('position')}, разрыв впереди {r.get('standing_ahead')}с, "
                         f"сзади {r.get('standing_behind')}с, лучший круг {r.get('best_lap_time')}")
    except Exception:
        pass
    try:
        res = httpx.get(f"{DASH}/api/result", timeout=1).json()
        bal = (res.get("symptoms") or {}).get("balance") or {}
        if bal:
            parts.append("баланс: " + ", ".join(f"{k} {v.get('tendency')}" for k, v in bal.items()))
    except Exception:
        pass
    return "; ".join(parts) or "данных гонки нет (дашборд не запущен или ты не на трассе)"


# ---------- команды-действия ----------
def _media(key):
    import keyboard
    keyboard.send(key)


def _launch_path(path):
    if path and os.path.exists(path):
        subprocess.Popen([path]); return True
    return False


def _launch_discord():
    upd = os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe")
    if os.path.exists(upd):
        subprocess.Popen([upd, "--processStart", "Discord.exe"]); return True
    return False


# Каталог приложений: (ключевые слова в фразе, чем запускать, что сказать).
# Запуск: строка-путь ИЛИ функция. Добавлять новые — просто дописать строку сюда.
APPS = [
    (["стим", "steam"], r"C:\Program Files (x86)\Steam\Steam.exe", "Открываю Стим"),
    (["обс", "о бэ эс", "о б с", "obs"], r"C:\Program Files\obs-studio\bin\64bit\obs64.exe", "Запускаю О Б С"),
    (["мозу", "моза", "мозы", "питхаус", "пит хаус", "pit house"], r"C:\Program Files (x86)\MOZA Pit House\MOZA Pit House.exe", "Открываю Мозу"),
    (["дискорд", "discord"], _launch_discord, "Открываю Дискорд"),
    (["браузер", "хром", "chrome", "гугл"], r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Открываю браузер"),
    (["айрейсинг", "айресинг", "рейсинг", "iracing", "симулятор"], r"D:\SteamLibrary\steamapps\common\iRacing\ui\iRacingUI.exe", "Запускаю Айрейсинг"),
    (["амнези", "amnezia", "впн", "vpn"], r"C:\Program Files\AmneziaVPN\AmneziaVPN.exe", "Открываю Амнезию"),
]


def _try_launch_app(text):
    """Если фраза — «открой/запусти/включи <приложение>», запускает его. Иначе None."""
    if not any(w in text for w in ("открой", "запусти", "включи", "запой", "открыть")):
        return None
    for keys, launcher, phrase in APPS:
        if any(k in text for k in keys):
            ok = launcher() if callable(launcher) else _launch_path(launcher)
            return phrase if ok else "Не нашёл это приложение"
    return None


def handle_command(text):
    """Возвращает фразу-ответ, если это команда; иначе None (значит вопрос)."""
    t = text.lower()
    # громкость САМОГО Дмитрия (голос) — отличаем от системной по словам про него
    about_self = any(w in t for w in ["голос", "говори", "себя", "тебя", "ты ", "дим"])
    if about_self and ("тише" in t or "потише" in t or "убавь" in t or "слишком громк" in t):
        _set_volume(_vol_num() - 15); return "Сделал тише"
    if about_self and ("громче" in t or "погромче" in t or "прибавь" in t):
        _set_volume(_vol_num() + 15); return "Сделал громче"
    app = _try_launch_app(t)                       # открой/запусти <приложение>
    if app is not None:
        return app
    if ("следующ" in t or "переключи" in t) and ("трек" in t or "музык" in t or "песн" in t):
        _media("next track"); return "Следующий трек"
    if "предыдущ" in t and ("трек" in t or "музык" in t):
        _media("previous track"); return "Предыдущий трек"
    if ("пауза" in t or "поставь на паузу" in t) or (("стоп" in t) and "музык" in t):
        _media("play/pause media"); return "Пауза"
    if "играй" in t or "продолжи музык" in t or "включи музык" in t:
        _media("play/pause media"); return "Играю"
    if "громче" in t or "погромче" in t:
        _media("volume up"); _media("volume up"); return "Громче"
    if "тише" in t or "потише" in t:
        _media("volume down"); _media("volume down"); return "Тише"
    return None


def ask_ollama(question):
    ctx = race_context()
    prompt = f"Данные гонки сейчас: {ctx}.\nВопрос гонщика: {question}\nОтветь коротко."
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
            "stream": False, "keep_alive": "30m",
            "options": {"temperature": 0.4, "num_predict": 200},
        }, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:
        return f"Не смог ответить: {e}"


def process(frames):
    if not frames or model is None:
        speak("Секунду, ещё гружусь" if model is None else "Не расслышал")
        return
    try:
        text = transcribe(frames)
    except Exception as e:
        print("STT ошибка:", e, flush=True); speak("Не расслышал"); return
    if not text:
        speak("Повтори, не расслышал"); return
    print("Ты:", text, flush=True)
    cmd = handle_command(text)
    if cmd is not None:
        print("Дмитрий (команда):", cmd, flush=True); speak(cmd); return
    answer = ask_ollama(text)
    print("Дмитрий:", answer, flush=True)
    speak(answer)


def toggle():
    global is_recording, audio_frames
    with _lock:
        if not is_recording:
            audio_frames = []
            is_recording = True
            print("● слушаю… (нажми кнопку ещё раз — закончить)", flush=True)
        else:
            is_recording = False
            frames = audio_frames
            audio_frames = []
            print("… обрабатываю", flush=True)
            threading.Thread(target=process, args=(frames,), daemon=True).start()


def main():
    print("Дмитрий-ассистент. Активация — кнопка 20 на руле.", flush=True)
    threading.Thread(target=load_model, daemon=True).start()
    pygame.init(); pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("Руль не найден!", flush=True); return
    j = pygame.joystick.Joystick(0); j.init()
    print(f"Руль: {j.get_name()} — кнопка {BUTTON_INDEX+1} активирует Дмитрия.", flush=True)
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype=np.float32,
                            callback=audio_callback)
    speak("Дмитрий на связи")
    prev = False
    with stream:
        while True:
            pygame.event.pump()
            pressed = bool(j.get_button(BUTTON_INDEX))
            if pressed and not prev:
                threading.Thread(target=toggle, daemon=True).start()
            prev = pressed
            time.sleep(0.02)


if __name__ == "__main__":
    main()
