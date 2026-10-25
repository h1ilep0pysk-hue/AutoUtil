from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from ui.explorer.theme import DARK, FONT_FAMILY


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    font = QFont(FONT_FAMILY, 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    palette = QPalette()
    roles = [
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "panel"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "surface"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "raised"),
        (QPalette.ColorRole.HighlightedText, "text"),
        (QPalette.ColorRole.ToolTipBase, "raised"),
        (QPalette.ColorRole.ToolTipText, "text"),
    ]
    for role, key in roles:
        palette.setColor(role, QColor(DARK[key]))
    app.setPalette(palette)
