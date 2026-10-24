from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from core.prefs import UiPrefs

GRAY = {
    "bg": "#2B2D31",
    "panel": "#232529",
    "surface": "#33363B",
    "border": "#3F4247",
    "text": "#E6E7EA",
    "muted": "#9A9EA6",
}

LIGHT = {
    "bg": "#F4F5F7",
    "panel": "#EBEDF0",
    "surface": "#FFFFFF",
    "border": "#D5D8DD",
    "text": "#1F2226",
    "muted": "#6B7079",
}


def build_qss(prefs: UiPrefs) -> str:
    c = GRAY if prefs.theme == "graphite" else LIGHT
    accent = prefs.accent
    row_pad = 4 if prefs.compact_lists else 8
    return f"""
    QWidget {{ background: {c['bg']}; color: {c['text']};
              font-size: {prefs.font_size}pt; }}
    QListWidget, QListView, QLineEdit {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 6px; padding: 4px; }}
    QListView::item, QListWidget::item {{ padding: {row_pad}px; border-radius: 4px; }}
    QListView::item:selected, QListWidget::item:selected {{
        background: {accent}; color: #FFFFFF; }}
    QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']};
                  border-radius: 6px; padding: 6px 14px; }}
    QPushButton:hover {{ border-color: {accent}; }}
    QPushButton:pressed {{ background: {c['border']}; }}
    QCheckBox {{ spacing: 8px; }}
    QLabel[role="muted"] {{ color: {c['muted']}; }}
    QLabel[role="title"] {{ font-size: {prefs.font_size + 4}pt; font-weight: 600; }}
    #Sidebar {{ background: {c['panel']}; border: none; }}
    #Sidebar::item {{ padding: 10px 14px; border-radius: 6px; margin: 2px 6px; }}
    #Sidebar::item:selected {{ background: {c['surface']}; color: {c['text']};
                              border-left: 3px solid {accent}; }}
    QStatusBar {{ background: {c['panel']}; color: {c['muted']}; }}
    """


def apply_qss(app: QApplication, prefs: UiPrefs) -> None:
    app.setStyleSheet(build_qss(prefs))
