import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Callable

log = logging.getLogger("autoutil.hotkeys")

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODIFIERS = {"ctrl": MOD_CONTROL, "shift": MOD_SHIFT, "alt": MOD_ALT}

user32 = ctypes.windll.user32


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'ctrl+shift+o' -> (modifiers, vk)."""
    parts = [p.strip().lower() for p in spec.split("+")]
    key = parts[-1]
    mods = 0
    for p in parts[:-1]:
        if p not in _MODIFIERS:
            raise ValueError(f"Неизвестный модификатор: {p}")
        mods |= _MODIFIERS[p]
    if len(key) != 1:
        raise ValueError(f"Поддерживается одна буква или цифра: {key}")
    return mods, ord(key.upper())


class HotkeyListener:
    """Регистрирует хоткей и вызывает callback из своего потока.

    Callback должен быть потокобезопасным: в GUI-приложении его обычно
    передают через сигнал Qt.
    """

    def __init__(self, spec: str, callback: Callable[[], None], hotkey_id: int = 1) -> None:
        self.spec = spec
        self.callback = callback
        self.id = hotkey_id
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._ok = False

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)
        return self._ok

    def stop(self) -> None:
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _loop(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        mods, vk = parse_hotkey(self.spec)
        self._ok = bool(user32.RegisterHotKey(None, self.id, mods | MOD_NOREPEAT, vk))
        if not self._ok:
            log.error("Не удалось зарегистрировать хоткей %s (занят другой программой?)", self.spec)
        self._ready.set()
        if not self._ok:
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam == self.id:
                try:
                    self.callback()
                except Exception:
                    log.exception("Ошибка в обработчике хоткея")
        user32.UnregisterHotKey(None, self.id)