import sys
from pathlib import Path
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AutoUtil"


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = _command()
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{sys.executable}" "{main}"'
