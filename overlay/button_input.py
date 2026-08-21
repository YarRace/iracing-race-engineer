"""Единый ввод для оверлея: кнопки руля/геймпада + хаты (крестовина/стик) + КЛАВИАТУРА.

Любой физический ввод можно назначить на действие в оверлее. Неважно, какой у
пользователя девайс — руль, геймпад, «кругляш» или просто клавиатура: главное, что
нажатая им кнопка/направление считывается и шлёт Qt-сигнал `pressed(action_id)`.

Типы привязок (`binding`):
  • {"type":"joybtn","guid","btn","name"}              — кнопка руля/геймпада (pygame)
  • {"type":"hat","guid","hat","hx","hy","name"}       — направление крестовины/хата
  • {"type":"key","vk","name"}                          — клавиша (Win32 low-level hook)

Ключевое:
  • SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS=1 — кнопки руля читаются при фокусе игры.
  • Клавиатура — WH_KEYBOARD_LL хук: ловит клавишу глобально (даже в iRacing) и
    ПРОПУСКАЕТ её дальше (CallNextHookEx) — не крадёт у игры (в отличие от RegisterHotKey).
  • `capture()` ловит следующий ЛЮБОЙ ввод — для кнопки «Assign» в настройках.

Всё в try/except: нет pygame/руля/Windows — оверлей просто работает без этих привязок.
"""
from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QObject, Signal

_HUB = None


def hub():
    """Единый экземпляр (лениво стартует фоновые потоки при первом обращении)."""
    global _HUB
    if _HUB is None:
        _HUB = InputHub()
        _HUB.start()
    return _HUB


# --- идентификатор физического ввода (чистая функция — тестируется) ---
def input_id(binding):
    """Хешируемый ключ ввода: одинаков у одинаковых кнопок/направлений/клавиш.
    Совместимо со старым форматом (без 'type', но с guid/btn = кнопка руля)."""
    if not binding:
        return None
    t = binding.get("type")
    if t == "key":
        return ("key", binding.get("vk"))
    if t == "hat":
        return ("hat", binding.get("guid"), binding.get("hat"),
                binding.get("hx"), binding.get("hy"))
    return ("joybtn", binding.get("guid"), binding.get("btn"))   # joybtn / старый формат


# --- имена для показа в UI ---
_VK_NAMES = {0x20: "Space", 0x0D: "Enter", 0x1B: "Esc", 0x08: "Backspace", 0x09: "Tab",
             0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
             0xA0: "LShift", 0xA1: "RShift", 0xA2: "LCtrl", 0xA3: "RCtrl",
             0xA4: "LAlt", 0xA5: "RAlt", 0x14: "Caps", 0x2D: "Insert", 0x2E: "Delete",
             0x24: "Home", 0x23: "End", 0x21: "PgUp", 0x22: "PgDn"}


def key_name(vk):
    if vk in _VK_NAMES:
        return _VK_NAMES[vk]
    if 0x30 <= vk <= 0x5A:                       # 0-9, A-Z
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num{vk - 0x60}"
    if 0x70 <= vk <= 0x7B:
        return f"F{vk - 0x6F}"
    return f"vk{vk}"


def hat_name(hx, hy):
    return {(0, 1): "▲ up", (0, -1): "▼ down", (-1, 0): "◀ left", (1, 0): "▶ right",
            (-1, 1): "↖", (1, 1): "↗", (-1, -1): "↙", (1, -1): "↘"}.get((hx, hy), f"hat {hx},{hy}")


class InputHub(QObject):
    pressed = Signal(str)               # сработала кнопка, привязанная к action_id
    captured = Signal(dict, str)        # пойман ввод при назначении: (binding, имя)

    def __init__(self):
        super().__init__()
        self._bindings = {}             # action_id -> binding
        self._capture = False
        self._lock = threading.Lock()
        self._run = True
        self.ok = False                 # поднялся ли pygame.joystick
        self.kb_ok = False              # поднялся ли клав. хук
        self._keys_down = set()
        self._kb_tid = None

    def start(self):
        threading.Thread(target=self._joy_loop, daemon=True).start()
        threading.Thread(target=self._kb_loop, daemon=True).start()

    def stop(self):
        self._run = False
        if self._kb_tid is not None:                    # разбудить GetMessage, чтобы поток вышел
            try:
                import ctypes
                ctypes.windll.user32.PostThreadMessageW(self._kb_tid, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass

    def bind(self, action_id, binding):
        with self._lock:
            if binding:
                self._bindings[action_id] = binding
            else:
                self._bindings.pop(action_id, None)

    def unbind(self, action_id):
        self.bind(action_id, None)

    def capture(self):
        """Поймать следующий любой ввод (для назначения)."""
        with self._lock:
            self._capture = True

    def cancel_capture(self):
        with self._lock:
            self._capture = False

    def _on_input(self, binding, name):
        """Общая точка для всех источников: захват при назначении либо роутинг в действия."""
        with self._lock:
            if self._capture:
                self._capture = False
                self.captured.emit(binding, name)
                return
            iid = input_id(binding)
            hits = [a for a, bd in self._bindings.items() if input_id(bd) == iid]
        for a in hits:
            self.pressed.emit(a)

    # --- руль/геймпад: кнопки + хаты (pygame) ---
    def _joy_loop(self):
        try:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
            import pygame
            pygame.display.init()
            pygame.joystick.init()
        except Exception:
            return
        self.ok = True
        joys, pb, ph = {}, {}, {}
        while self._run:
            try:
                pygame.event.pump()
                n = pygame.joystick.get_count()
                if len(joys) != n:
                    joys = {}
                    for i in range(n):
                        try:
                            j = pygame.joystick.Joystick(i); j.init(); joys[i] = j
                        except Exception:
                            pass
                for j in joys.values():
                    try:
                        guid, name = j.get_guid(), j.get_name()
                    except Exception:
                        continue
                    for b in range(j.get_numbuttons()):
                        try:
                            down = bool(j.get_button(b))
                        except Exception:
                            down = False
                        k = (guid, b)
                        if down and not pb.get(k, False):
                            self._on_input({"type": "joybtn", "guid": guid, "btn": int(b),
                                            "name": f"{name} · button {b + 1}"},
                                           f"{name} · button {b + 1}")
                        pb[k] = down
                    for hi in range(j.get_numhats()):     # крестовина/стик как хат
                        try:
                            hx, hy = j.get_hat(hi)
                        except Exception:
                            hx, hy = 0, 0
                        k = (guid, hi)
                        if (hx, hy) != (0, 0) and (hx, hy) != ph.get(k, (0, 0)):
                            self._on_input({"type": "hat", "guid": guid, "hat": int(hi),
                                            "hx": int(hx), "hy": int(hy),
                                            "name": f"{name} · {hat_name(hx, hy)}"},
                                           f"{name} · {hat_name(hx, hy)}")
                        ph[k] = (hx, hy)
            except Exception:
                pass
            time.sleep(0.02)

    # --- клавиатура: глобальный low-level хук (Windows) ---
    def _kb_loop(self):
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return
        WH_KEYBOARD_LL = 13
        WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
        WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

        class KBD(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]
        PROC = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        def proc(nCode, wParam, lParam):
            try:
                if nCode == 0:
                    vk = ctypes.cast(lParam, ctypes.POINTER(KBD)).contents.vkCode
                    if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if vk not in self._keys_down:            # фронт нажатия (без автоповтора)
                            self._keys_down.add(vk)
                            nm = f"Key {key_name(vk)}"
                            self._on_input({"type": "key", "vk": int(vk), "name": nm}, nm)
                    elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                        self._keys_down.discard(vk)
            except Exception:
                pass
            return user32.CallNextHookExW(None, nCode, wParam, lParam)   # пропустить клавишу дальше (не красть)

        self._kb_proc = PROC(proc)                                       # держим ссылку от GC
        try:
            self._kb_tid = kernel32.GetCurrentThreadId()
            hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc,
                                            kernel32.GetModuleHandleW(None), 0)
            if not hook:
                return
            self.kb_ok = True
            msg = wintypes.MSG()
            while self._run and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.UnhookWindowsHookEx(hook)
        except Exception:
            return


# обратная совместимость со старым импортом (ButtonHub)
ButtonHub = InputHub
