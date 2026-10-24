import sys
import winreg
from pathlib import Path

VERB = "AutoUtilOCR"
EXTS = [".png", ".jpg", ".jpeg"]
MAIN = Path(__file__).resolve().parent.parent / "main.py"


def install() -> None:
    command = f'\"{sys.executable}\" \"{MAIN}\" --ocr-file "%1"'
    for ext in EXTS:
        base = rf"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\{VERB}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, "Распознать текст")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\\command") as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, command)


def uninstall() -> None:
    for ext in EXTS:
        base = rf"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\{VERB}"
        for sub in (base + r"\\command", base):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except FileNotFoundError:
                pass
