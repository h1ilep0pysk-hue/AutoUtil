from PySide6.QtWidgets import QApplication

from core.prefs import UiPrefs

DARK = {
    "bg": "#181818",
    "panel": "#1F1F1F",
    "surface": "#272727",
    "raised": "#313131",
    "border": "#363636",
    "text": "#F2F2F2",
    "muted": "#9B9B9B",
    "faint": "#5E5E5E",
    "accent": "#F2F2F2",
    "accent_text": "#000000",
    "accent_hover": "#D9D9D9",
    "focus": "#8AB4F8",
    "danger": "#E5484D",
}

LIGHT = {
    "bg": "#F4F4F5",
    "panel": "#EBEBED",
    "surface": "#FFFFFF",
    "raised": "#E2E2E5",
    "border": "#D4D4D8",
    "text": "#18181B",
    "muted": "#6B6B73",
    "faint": "#A1A1AA",
    "accent": "#18181B",
    "accent_text": "#FFFFFF",
    "accent_hover": "#33333A",
    "focus": "#3B6FD8",
    "danger": "#D03A3F",
}

FONT_FAMILY = "Manrope"


def build_qss(prefs: UiPrefs) -> str:
    t = LIGHT if prefs.theme == "light" else DARK
    fs = prefs.font_size
    return f"""
QWidget {{
    background: {t['bg']};
    color: {t['text']};
    font-family: \"{FONT_FAMILY}\", \"Segoe UI\";
    font-size: {fs}pt;
}}
QLabel {{ background: transparent; }}
QLabel[role=\"title\"] {{ font-size: {fs + 6}pt; font-weight: 600; }}
QLabel[role=\"muted\"], QLabel#Muted, QLabel#Help {{ color: {t['muted']}; }}
QLabel#Heading {{ font-size: {fs + 2}pt; font-weight: 600; }}

#Sidebar {{
    background: {t['panel']};
    border: none;
    padding: 8px;
    outline: none;
}}
#Sidebar::item {{
    padding: 10px 12px;
    border-radius: 8px;
    color: {t['muted']};
    margin: 2px 0px;
}}
#Sidebar::item:hover {{ background: {t['surface']}; color: {t['text']}; }}
#Sidebar::item:selected {{ background: {t['raised']}; color: {t['text']}; }}

QPushButton {{
    background: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 8px 12px;
}}
QPushButton:hover {{ background: {t['raised']}; border-color: {t['muted']}; }}
QPushButton:pressed {{ background: {t['bg']}; padding-top: 9px; padding-bottom: 7px; }}
QPushButton:focus {{ border: 1px solid {t['focus']}; }}
QPushButton:disabled {{ color: {t['faint']}; }}
QPushButton#Primary {{
    background: {t['accent']};
    color: {t['accent_text']};
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {t['accent_hover']}; }}
QPushButton#DangerBtn {{
    background: transparent;
    color: {t['danger']};
    border: 1px solid {t['danger']};
}}

QLineEdit, QSpinBox, QComboBox {{
    background: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: {t['accent']};
    selection-color: {t['accent_text']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {t['focus']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t['surface']};
    border: 1px solid {t['border']};
    selection-background-color: {t['raised']};
    outline: none;
}}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {t['muted']};
    background: {t['surface']};
}}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}

QListView, QListWidget {{
    background: {t['panel']};
    border: 1px solid {t['border']};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}
QListView::item {{ padding: 10px 12px; border-radius: 8px; }}
QListView::item:hover {{ background: {t['surface']}; }}
QListView::item:selected {{ background: {t['raised']}; color: {t['text']}; }}

QMenu {{
    background: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 16px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['raised']}; }}
QMenu::item:disabled {{ color: {t['faint']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['raised']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0px; }}

QToolTip {{
    background: {t['raised']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 6px;
}}
QStatusBar {{
    background: {t['panel']};
    color: {t['muted']};
    border-top: 1px solid {t['border']};
}}
QMessageBox, QWizard, QDialog {{ background: {t['bg']}; }}
"""


def apply_qss(app: QApplication, prefs: UiPrefs) -> None:
    app.setStyleSheet(build_qss(prefs))
