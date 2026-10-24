import winreg

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

PERSONALIZE = r"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"


def is_dark() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except OSError:
        return False


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    if not is_dark():
        return
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(32, 32, 32))
    p.setColor(QPalette.ColorRole.WindowText, QColor(235, 235, 235))
    p.setColor(QPalette.ColorRole.Base, QColor(24, 24, 24))
    p.setColor(QPalette.ColorRole.Text, QColor(235, 235, 235))
    p.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(235, 235, 235))
    p.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
    app.setPalette(p)
