import sys
import winreg

RUN_KEY = r"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
VALUE_NAME = "AutoUtil"


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = f'\"{sys.executable}\" \"{_main_path()}\"'
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass


def _main_path() -> str:
    from pathlib import Path
    return str(Path(__file__).resolve().parent.parent / "main.py")
