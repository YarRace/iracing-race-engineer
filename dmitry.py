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
# CPU по умолчанию: чтобы Whisper НЕ грузил видеокарту и iRacing не фризил при вопросе.
# medium на CPU — баланс качества/скорости (~5с на фразу).
WHISPER_MODEL = os.environ.get("DMITRY_WHISPER", "medium")
WHISPER_DEVICE = os.environ.get("DMITRY_DEVICE", "cpu")
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
    dev = WHISPER_DEVICE
    ct = "int8" if dev == "cpu" else "float16"
    print(f"Загружаю Whisper ({WHISPER_MODEL}, {dev})…", flush=True)
    try:
        m = WhisperModel(WHISPER_MODEL, device=dev, compute_type=ct)
        list(m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language=LANGUAGE)[0])
        print(f"Whisper готов ({dev.upper()}).", flush=True)
    except Exception as e:                              # запасной путь на CPU
        print(f"{dev} не вышло ({e}); пробую CPU.", flush=True)
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


def set_chrome_volume(delta):
    """Меняет громкость ИМЕННО Chrome (где играет Яндекс.Музыка), не системную.
    Через микшер Windows (pycaw). Возвращает True, если нашёл звук Chrome."""
    try:
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    except Exception:
        return False
    changed = False
    for s in AudioUtilities.GetAllSessions():
        if s.Process and s.Process.name().lower() == "chrome.exe":
            try:
                vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                cur = vol.GetMasterVolume()
                vol.SetMasterVolume(max(0.0, min(1.0, cur + delta)), None)
                changed = True
            except Exception:
                pass
    return changed


def _focus_window(title_substr):
    """Если окно с таким текстом в заголовке уже открыто — развернуть и вывести вперёд.
    Возвращает True, если нашли и активировали."""
    try:
        import pygetwindow as gw
    except Exception:
        return False
    sub = title_substr.lower()
    for w in gw.getAllWindows():
        title = (w.title or "").strip()
        if title and sub in title.lower():
            try:
                if w.isMinimized:
                    w.restore()
                w.activate()
                return True
            except Exception:
                try:
                    w.maximize(); return True
                except Exception:
                    pass
    return False


def _switch_chrome_tab(target):
    """Активирует Chrome и перебирает вкладки (Ctrl+Tab), пока в заголовке не найдёт target.
    Хрупко: если вкладки нет — остановится не на той. Возвращает True при успехе."""
    try:
        import pygetwindow as gw
        import keyboard
    except Exception:
        return False
    chrome = None
    for w in gw.getAllWindows():
        if "chrome" in (w.title or "").lower():
            chrome = w
            break
    if chrome is None:
        return False
    try:
        if chrome.isMinimized:
            chrome.restore()
        chrome.activate()
    except Exception:
        pass
    time.sleep(0.35)
    for _ in range(25):                       # перебор вкладок Chrome
        act = gw.getActiveWindow()
        if act and target.lower() in (act.title or "").lower():
            return True
        keyboard.send("ctrl+tab")
        time.sleep(0.18)
    return False


# Сайты, на которые Дима переключается среди открытых вкладок Chrome.
SITES = [
    (["твич", "twitch", "твитч"], "twitch", "Твич"),
    (["ютуб", "youtube", "ютьюб"], "youtube", "Ютуб"),
]


def _minimize_window(title_substr):
    """Свернуть все окна, содержащие title_substr в заголовке. True — если свернули хоть одно."""
    try:
        import pygetwindow as gw
    except Exception:
        return False
    sub = title_substr.lower()
    done = False
    for w in gw.getAllWindows():
        title = (w.title or "").strip()
        if title and sub in title.lower():
            try:
                w.minimize(); done = True
            except Exception:
                pass
    return done


def _minimize_named_app(name):
    name = (name or "").lower()
    for keys, _l, disp, win in APPS:
        if name and (name in keys or name in disp.lower()
                     or any(name in k or k in name for k in keys)):
            return f"Свернул {disp}" if (win and _minimize_window(win)) else f"{disp} не открыт"
    return "Не знаю такое приложение"


def _launch_path(path):
    if path and os.path.exists(path):
        subprocess.Popen([path]); return True
    return False


def _launch_discord():
    upd = os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe")
    if os.path.exists(upd):
        subprocess.Popen([upd, "--processStart", "Discord.exe"]); return True
    return False


def _launch_race_engineer():
    """Запускает наш дашборд Race Engineer (сервер + браузер) через start-dashboard.bat."""
    bat = os.path.join(_ROOT, "start-dashboard.bat")
    if os.path.exists(bat):
        os.startfile(bat); return True
    return False


def _launch_admin(path):
    """Запуск программы ОТ ИМЕНИ АДМИНИСТРАТОРА (всплывёт окно UAC — подтвердить «Да»)."""
    import ctypes
    if not os.path.exists(path):
        return False
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", path, None, os.path.dirname(path), 1)
        return rc > 32
    except Exception:
        return False


def _launch_gopro():
    return _launch_admin(r"C:\Program Files (x86)\GoPro\GoPro Webcam\GoPro Webcam.exe")


# Каталог приложений: (ключевые слова, чем запускать, что сказать, текст-заголовка-окна).
# Сначала Дима ищет уже открытое окно (даже свёрнутое) и разворачивает; если нет — запускает.
APPS = [
    (["стим", "steam"], r"C:\Program Files (x86)\Steam\Steam.exe", "Стим", "Steam"),
    (["телеграм", "телеграмм", "telegram", "тэгэ", "тэ гэ"], r"C:\Users\Ярослав\AppData\Roaming\Telegram Desktop\Telegram.exe", "Телеграм", "Telegram"),
    (["рутони", "рутон", "рута не", "рутэни", "rutony", "рутони чат"], r"D:\SteamLibrary\steamapps\common\RutonyChat\RutonyChat.exe", "Рутони чат", "RutonyChat"),
    (["обс", "о бэ эс", "о б с", "obs"], r"C:\Program Files\obs-studio\bin\64bit\obs64.exe", "О Б С", "OBS"),
    (["мозу", "моза", "мозы", "питхаус", "пит хаус", "pit house"], r"C:\Program Files (x86)\MOZA Pit House\MOZA Pit House.exe", "Мозу", "Pit House"),
    (["дискорд", "discord"], _launch_discord, "Дискорд", "Discord"),
    (["браузер", "хром", "chrome", "гугл"], r"C:\Program Files\Google\Chrome\Application\chrome.exe", "браузер", "Chrome"),
    (["айрейсинг", "айресинг", "рейсинг", "iracing", "симулятор"], r"C:\Program Files (x86)\Steam\steamapps\common\iRacing\ui\iRacingUI.exe", "Айрейсинг", "iRacing"),
    (["амнези", "amnezia", "впн", "vpn"], r"C:\Program Files\AmneziaVPN\AmneziaVPN.exe", "Амнезию", "Amnezia"),
    (["инженер", "гоночн", "рейс инженер", "race engineer", "race_engineer", "дашборд"], _launch_race_engineer, "Гоночного инженера", "Race Engineer"),
    (["камер", "гопро", "gopro", "вебкам", "webcam"], _launch_gopro, "Камеру", "GoPro Webcam"),
    (["трейдинг", "пейнтс", "пэйнтс", "ливре", "trading paints", "trading_paints", "трейдинг пейнтс"], r"C:\Program Files (x86)\Rhinode LLC\Trading Paints\Trading Paints.exe", "Трейдинг Пейнтс", "Trading Paints"),
    (["капс", "капп", "kapps", "оверлей", "оверлэй", "overlay"], r"C:\Users\Ярослав\AppData\Local\kapps\Kapps.exe", "Капс", "Kapps"),
]


def _try_launch_app(text):
    """«открой/запусти/включи <приложение>»: развернуть открытое окно или запустить. Иначе None."""
    if not any(w in text for w in ("открой", "запусти", "включи", "разверни", "открыть")):
        return None
    for keys, launcher, name, win_title in APPS:
        if any(k in text for k in keys):
            if win_title and _focus_window(win_title):       # уже открыто → развернуть
                return f"Разворачиваю {name}"
            ok = launcher() if callable(launcher) else _launch_path(launcher)
            return f"Открываю {name}" if ok else "Не нашёл это приложение"
    return None


ROUTER_SYSTEM = (
    "Ты — Дмитрий, голосовой ассистент гонщика в iRacing. По реплике гонщика реши, "
    "что он хочет, и верни СТРОГО JSON: {\"action\": \"...\", \"param\": \"...\"}.\n"
    "Возможные action и param:\n"
    "- minimize_app — свернуть окно ЛЮБОЙ программы из списка ниже. param: то же имя из списка "
    "(steam, telegram, rutonychat, obs, moza, discord, chrome, iracing, amnezia, race_engineer, "
    "gopro, trading_paints, kapps) или 'all' — свернуть все окна.\n"
    "- open_app — открыть/развернуть программу. param: одно из "
    "[steam, telegram, rutonychat, obs, moza, discord, chrome, iracing, amnezia, "
    "race_engineer, gopro, trading_paints, kapps]\n"
    "  ВАЖНО различай: telegram — мессенджер Телеграм; rutonychat — отдельная программа "
    "для чата стрима (НЕ телеграм). race_engineer — наш дашборд; gopro — камера; "
    "trading_paints — программа для ливрей/раскрасок машин (если просят 'ливреи'); "
    "kapps — гоночный оверлей (если просят 'оверлей' или 'капс').\n"
    "- switch_tab — переключиться на вкладку сайта в браузере. param: [twitch, youtube]\n"
    "- make_clip — сделать клип на твиче. param пустой\n"
    "- media — музыка (Яндекс.Музыка в браузере). param: [next, prev, playpause, volup, voldown]. "
    "volup/voldown — громкость МУЗЫКИ в браузере (не системная).\n"
    "- self_volume — громкость голоса самого Дмитрия. param: [up, down]\n"
    "- answer — это вопрос или реплоса без действия. В param помести КОРОТКИЙ ответ "
    "по-русски (1-2 фразы), используя данные гонки если они есть.\n"
    "Выбирай open_app/switch_tab/media/make_clip/self_volume ТОЛЬКО если гонщик явно "
    "просит сделать действие. Иначе action=answer."
)


def _open_named_app(name):
    name = (name or "").lower()
    for keys, launcher, disp, win in APPS:
        if name and (name in keys or name in disp.lower()
                     or any(name in k or k in name for k in keys)):
            if win and _focus_window(win):
                return f"Разворачиваю {disp}"
            ok = launcher() if callable(launcher) else _launch_path(launcher)
            return f"Открываю {disp}" if ok else "Не нашёл это приложение"
    return "Не знаю такое приложение"


def execute(decision):
    """Выполняет решение роутера и возвращает фразу для озвучки."""
    a = (decision.get("action") or "answer").lower()
    p = (decision.get("param") or "")
    pl = p.lower() if isinstance(p, str) else ""
    if a == "open_app":
        return _open_named_app(pl)
    if a == "minimize_app":
        if pl in ("all", "все", "всё"):
            import keyboard
            keyboard.send("windows+d"); return "Свернул всё"
        return _minimize_named_app(pl)
    if a == "switch_tab":
        target = "twitch" if ("twi" in pl or "твич" in pl) else "youtube"
        nm = "Твич" if target == "twitch" else "Ютуб"
        return f"Переключаюсь на {nm}" if _switch_chrome_tab(target) else f"Не нашёл вкладку {nm}"
    if a == "make_clip":
        import keyboard
        if _switch_chrome_tab("twitch"):
            time.sleep(0.3); keyboard.send("alt+x"); return "Делаю клип"
        return "Не нашёл вкладку Твич"
    if a == "media":
        if pl == "volup":
            return "Громче" if set_chrome_volume(+0.12) else "Музыка не играет"
        if pl == "voldown":
            return "Тише" if set_chrome_volume(-0.12) else "Музыка не играет"
        m = {"next": "next track", "prev": "previous track", "playpause": "play/pause media"}
        if pl in m:
            _media(m[pl]); return "Готово"
        return "Не понял по музыке"
    if a == "self_volume":
        _set_volume(_vol_num() + (15 if pl == "up" else -15))
        return "Сделал громче" if pl == "up" else "Сделал тише"
    return p or "Не понял, повтори"


def quick_match(text):
    """Быстрый матч типичных команд БЕЗ LLM (мгновенно). None — если не распознано."""
    t = text.lower()
    about_self = any(w in t for w in ["голос", "говори", "себя", "тебя", "дим"])
    if about_self and any(w in t for w in ["тише", "потише", "убавь"]):
        _set_volume(_vol_num() - 15); return "Сделал тише"
    if about_self and any(w in t for w in ["громче", "погромче", "прибавь"]):
        _set_volume(_vol_num() + 15); return "Сделал громче"
    if "клип" in t:
        import keyboard
        if _switch_chrome_tab("twitch"):
            time.sleep(0.3); keyboard.send("alt+x"); return "Делаю клип"
        return "Не нашёл вкладку Твич"
    # развернуть все свёрнутые окна
    if ("все окна" in t or "всё окна" in t or "все окошк" in t) and \
       any(w in t for w in ("открой", "разверни", "восстанов", "покажи", "верни")):
        import keyboard
        keyboard.send("windows+shift+m"); return "Развернул все окна"
    if any(w in t for w in ("сверни", "свернуть", "сворачивай", "скрой")):
        if "все" in t or "всё" in t:                      # свернуть все окна
            import keyboard
            keyboard.send("windows+d"); return "Свернул всё"
        for keys, _l, disp, win in APPS:
            if any(k in t for k in keys):
                return f"Свернул {disp}" if (win and _minimize_window(win)) else f"{disp} не открыт"
        return None
    launch_trig = any(w in t for w in ("открой", "открыть", "запусти", "запускай",
                                       "включи", "врубай", "разверни", "разверня",
                                       "раскрой", "покажи", "верни", "давай"))
    if launch_trig:
        for keys, target, name in SITES:                  # вкладки сайтов
            if any(k in t for k in keys):
                return f"Переключаюсь на {name}" if _switch_chrome_tab(target) else f"Не нашёл вкладку {name}"
        for keys, launcher, disp, win in APPS:            # приложения
            if any(k in t for k in keys):
                if win and _focus_window(win):
                    return f"Разворачиваю {disp}"
                ok = launcher() if callable(launcher) else _launch_path(launcher)
                return f"Открываю {disp}" if ok else "Не нашёл это приложение"
    # громкость МУЗЫКИ — крутим именно Chrome (не системную, не весь комп)
    if "музык" in t and ("громче" in t or "погромче" in t):
        return "Громче" if set_chrome_volume(+0.12) else "Музыка не играет"
    if "музык" in t and ("тише" in t or "потише" in t):
        return "Тише" if set_chrome_volume(-0.12) else "Музыка не играет"
    if ("следующ" in t or "переключи" in t) and ("трек" in t or "музык" in t or "песн" in t):
        _media("next track"); return "Следующий трек"
    if "предыдущ" in t and ("трек" in t or "музык" in t):
        _media("previous track"); return "Предыдущий трек"
    if "пауза" in t or "остановись" in t or ("стоп" in t and "музык" in t):
        _media("play/pause media"); return "Пауза"
    if ("играй" in t or "включи музык" in t or "продолжи музык" in t):
        _media("play/pause media"); return "Играю"
    return None


def route_intent(text):
    """Ollama решает намерение по свободной речи → dict {action, param}."""
    import json
    ctx = race_context()
    prompt = f'Данные гонки сейчас: {ctx}.\nРеплика гонщика: "{text}"\nВерни JSON-решение.'
    try:
        r = httpx.post(f"{OLLAMA}/api/chat", json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "system", "content": ROUTER_SYSTEM},
                         {"role": "user", "content": prompt}],
            "stream": False, "format": "json", "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_predict": 300},
        }, timeout=120)
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except Exception as e:
        return {"action": "answer", "param": f"Не смог обработать: {e}"}


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
    quick = quick_match(text)                      # сначала быстрый матч (без LLM)
    if quick is not None:
        print("Дмитрий (быстро):", quick, flush=True); speak(quick); return
    decision = route_intent(text)                 # иначе Ollama (свободная речь/вопросы)
    print("  намерение:", decision, flush=True)
    reply = execute(decision)
    print("Дмитрий:", reply, flush=True)
    speak(reply)


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
