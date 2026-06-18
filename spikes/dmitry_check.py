"""Полная проверка ассистента Дмитрий: все компоненты по очереди."""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _ROOT)


def ok(name, cond, extra=""):
    print(f"  [{'OK ' if cond else 'НЕТ'}] {name}{(' — ' + extra) if extra else ''}", flush=True)
    return cond


print("=== 1. Зависимости ===", flush=True)
import importlib
for m in ["sounddevice", "pygame", "httpx", "edge_tts", "playsound",
          "faster_whisper", "keyboard", "numpy", "pygetwindow"]:
    try:
        importlib.import_module(m); ok(m, True)
    except Exception as e:
        ok(m, False, str(e))

import dmitry  # noqa

print("=== 2. Пути приложений (APPS) ===", flush=True)
for keys, launcher, disp, win in dmitry.APPS:
    if callable(launcher):
        ok(disp, True, "запуск через функцию (Discord)")
    else:
        ok(disp, os.path.exists(launcher), launcher)

print("=== 3. Руль и кнопка ===", flush=True)
try:
    import pygame
    pygame.init(); pygame.joystick.init()
    n = pygame.joystick.get_count()
    if ok("руль найден", n > 0, f"устройств: {n}") and n:
        j = pygame.joystick.Joystick(0); j.init()
        ok(f"кнопка {dmitry.BUTTON_INDEX+1} в пределах", dmitry.BUTTON_INDEX < j.get_numbuttons(),
           f"{j.get_name()}, кнопок {j.get_numbuttons()}")
    pygame.quit()
except Exception as e:
    ok("руль", False, str(e))

print("=== 4. Управление окнами (pygetwindow) ===", flush=True)
try:
    import pygetwindow as gw
    ok("чтение окон", len(gw.getAllTitles()) > 0, f"открытых окон: {len(gw.getAllTitles())}")
except Exception as e:
    ok("окна", False, str(e))

print("=== 5. Голос (edge-tts) ===", flush=True)
try:
    dmitry.speak("Проверка связи. Дмитрий полностью готов.")
    ok("озвучка", True, f"голос {dmitry.VOICE}, громкость {dmitry.VOLUME}")
except Exception as e:
    ok("озвучка", False, str(e))

print("=== 6. Мозг (Ollama роутинг) ===", flush=True)
try:
    d = dmitry.route_intent("врубай дискорд")
    ok("Ollama отвечает", d.get("action") == "open_app", str(d))
except Exception as e:
    ok("Ollama", False, str(e))

print("=== 7. Контекст гонки (дашборд) ===", flush=True)
print("   ", dmitry.race_context(), flush=True)

print("=== 8. Распознавание речи (Whisper) ===", flush=True)
try:
    import numpy as np
    from faster_whisper import WhisperModel
    print(f"    загружаю Whisper '{dmitry.WHISPER_MODEL}' (может скачиваться при первом разе)…", flush=True)
    try:
        m = WhisperModel(dmitry.WHISPER_MODEL, device="cuda", compute_type="float16")
        dev = "GPU"
    except Exception:
        m = WhisperModel(dmitry.WHISPER_MODEL, device="cpu", compute_type="int8")
        dev = "CPU"
    list(m.transcribe(np.zeros(16000, dtype=np.float32), language="ru")[0])
    ok("Whisper готов", True, f"модель {dmitry.WHISPER_MODEL}, {dev}")
except Exception as e:
    ok("Whisper", False, str(e))

print("\n=== ПРОВЕРКА ЗАВЕРШЕНА ===", flush=True)
