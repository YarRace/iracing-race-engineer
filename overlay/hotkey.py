"""Глобальный хоткей поверх игры (Win32 RegisterHotKey) — как «лок» в Kapps.

Регистрирует комбинацию (по умолчанию Ctrl+Shift+L) на уровне ОС, ловит WM_HOTKEY
через нативный фильтр событий Qt и зовёт callback. Работает, даже когда в фокусе
iRacing. Всё в try/except — если не вышло, приложение просто работает без хоткея.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x0001, 0x0002, 0x0004
WM_HOTKEY = 0x0312
VK_L = 0x4C


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback, vk=VK_L, mods=MOD_CONTROL | MOD_SHIFT, hotkey_id=1):
        super().__init__()
        self.cb = callback
        self.id = hotkey_id
        self.ok = False
        if sys.platform != "win32":
            return
        try:
            import ctypes
            if ctypes.windll.user32.RegisterHotKey(None, self.id, mods, vk):
                QCoreApplication.instance().installNativeEventFilter(self)
                self.ok = True
        except Exception:
            self.ok = False

    def nativeEventFilter(self, etype, message):
        try:
            if self.ok and message is not None:
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == self.id:
                    self.cb()
        except Exception:
            pass
        return False, 0
