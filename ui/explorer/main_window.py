from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from core.config import AppSettings
from core.journal import Journal
from core.prefs import UiPrefs
from modules.grabber.history import History
from ui.explorer.pages import CapturesPage, JournalPage, RulesPage, SettingsPage
from ui.explorer.sidebar import Sidebar
from ui.explorer.theme import apply_qss

from core.prefs import load_prefs


class ExplorerWindow(QMainWindow):
    def __init__(self, settings: AppSettings, journal: Journal, history: History, prefs: UiPrefs = None) -> None:
        super().__init__()
        self.settings = settings
        if prefs is None:
            prefs = load_prefs()
        self.prefs = prefs
        self.setWindowTitle("AutoUtil")
        self.resize(1000, 640)

        self.pages = {
            "captures": CapturesPage(history, prefs),
            "journal": JournalPage(journal, prefs),
            "rules": RulesPage(),
            "settings": SettingsPage(settings, prefs, self.apply_prefs),
        }
        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.sidebar = Sidebar()
        self.sidebar.section_selected.connect(self._switch)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Готово")

        self.sidebar.select(prefs.default_section)
        self._switch(prefs.default_section)

    def apply_prefs(self, prefs: UiPrefs) -> None:
        self.prefs = prefs
        apply_qss(QApplication.instance(), prefs)
        self.statusBar().showMessage("Настройки сохранены")

    def _switch(self, key: str) -> None:
        page = self.pages[key]
        if hasattr(page, "reload"):
            page.reload()
        self.stack.setCurrentWidget(page)

    def show_section(self, key: str) -> None:
        self.sidebar.select(key)
        self._switch(key)
        self.show()
        self.raise_()
        self.activateWindow()
