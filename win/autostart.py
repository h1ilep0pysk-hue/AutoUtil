"""Автозапуск вместе с Windows (HKCU\\...\\Run).

FIX: раньше `set_autostart` мог молча упасть (исключение терялось в слоте
«Сохранить»), а галочка в настройках не сверялась с реальным состоянием
реестра — поэтому автозапуск «не работал». Теперь:
- команда для сорцов строится на pythonw (консоль не мигает при старте);
- исключения не гасятся глобально: set_autostart возвращает True/False;
- есть autostart_enabled() — единственный источник правды (реестр).
"""
import logging
import sys
from pathlib import Path
import winreg

log = logging.getLogger("autoutil.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AutoUtil"


def autostart_enabled() -> bool:
    """Реальное текущее состояние автозапуска (по реестру)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        log.exception("Не удалось прочитать ключ автозапуска")
        return False
    return bool(str(value).strip())


def set_autostart(enabled: bool) -> bool:
    """Включить/выключить автозапуск. Возвращает успех; False — см. лог."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        # нет прав/антивирус/политики — не роняем сохранение настроек
        log.exception("Не удалось настроить автозапуск")
        return False


def _command() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller: sys.executable - путь к самому exe
        return f'"{sys.executable}"'
    # из исходников: pythonw.exe, чтобы при старте Windows не мигало окно консоли
    main = Path(__file__).resolve().parent.parent / "main.py"
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = pyw if pyw.exists() else Path(sys.executable)
    return f'"{exe}" "{main}"'
