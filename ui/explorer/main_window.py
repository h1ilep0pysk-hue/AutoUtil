import logging

from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QWidget,
)

from core.config import AppSettings
from core.journal import Journal
from core.prefs import UiPrefs, load_prefs
from ui.explorer.pages import JournalPage, RulesPage, SettingsPage
from ui.explorer.pending_page import PendingPage
from ui.explorer.report_page import ReportPage
from ui.explorer.schema_page import SchemaPage
from ui.explorer.sidebar import Sidebar
from ui.explorer.theme import apply_qss

log = logging.getLogger("autoutil.ui")

LOG_HINT = "%APPDATA%\\AutoUtil\\logs\\autoutil.log"


def _failed_page(name: str, err: Exception) -> QWidget:
    log.exception("Не удалось создать раздел %s", name)
    page = QWidget()
    lbl = QLabel(
        f"Раздел «{name}» не загрузился.\n\n{type(err).__name__}: {err}\n\n"
        f"Подробности в логе: {LOG_HINT}"
    )
    lbl.setWordWrap(True)
    lay = QHBoxLayout(page)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.addWidget(lbl)
    lay.addStretch()
    return page


class ExplorerWindow(QMainWindow):
    def __init__(self, settings: AppSettings, journal: Journal,
                 prefs: UiPrefs | None = None, on_run_schema=None) -> None:
        super().__init__()
        self.settings = settings
        if prefs is None:
            prefs = load_prefs()
        self.prefs = prefs
        self.setWindowTitle("AutoUtil")
        self.resize(1100, 720)

        factories = {
            "schema": lambda: SchemaPage(on_apply=self._on_schema_applied, on_run=on_run_schema),
            "pending": lambda: PendingPage(journal),
            "journal": lambda: JournalPage(journal, prefs),
            "report": lambda: ReportPage(journal),
            "rules": lambda: RulesPage(),
            "settings": lambda: SettingsPage(settings, prefs, self.apply_prefs),
        }
        names = {
            "schema": "Схема", "pending": "Спросить", "journal": "Журнал",
            "report": "Отчёт", "rules": "Правила", "settings": "Настройки",
        }
        self.pages: dict[str, QWidget] = {}
        for key, make in factories.items():
            try:
                self.pages[key] = make()
            except Exception as e:
                self.pages[key] = _failed_page(names[key], e)

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

        section = prefs.default_section if prefs.default_section in self.pages else "schema"
        self.sidebar.select(section)
        self._switch(section)

    def apply_prefs(self, prefs: UiPrefs) -> None:
        self.prefs = prefs
        apply_qss(QApplication.instance(), prefs)
        self.statusBar().showMessage("Настройки сохранены")

    def _switch(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            log.error("Нет раздела с ключом %s", key)
            return
        if hasattr(page, "reload"):
            try:
                page.reload()
            except Exception:
                log.exception("Ошибка при обновлении раздела %s", key)
                self.statusBar().showMessage(f"Ошибка в разделе: см. лог {LOG_HINT}")
        self.stack.setCurrentWidget(page)

    def show_section(self, key: str) -> None:
        self.sidebar.select(key)
        self._switch(key)
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_schema_applied(self, rules, folders: list[str]) -> None:
        self.pages["rules"].reload()
        self.statusBar().showMessage("Схема применена. Правила обновлены.")
