import logging

from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QWidget,
)

from core.config import AppSettings
from core.i18n import t
from core.journal import Journal
from core.prefs import UiPrefs, load_prefs
from ui.explorer.pages import JournalPage, RulesPage, SettingsPage
from ui.explorer.pending_page import PendingPage
from ui.explorer.report_page import ReportPage
from ui.explorer.schema_page import SchemaPage
from ui.explorer.sidebar import Sidebar
from ui.explorer.theme import apply_qss

log = logging.getLogger("autoutil.ui")

LOG_HINT = "%LOCALAPPDATA%\\AutoUtil\\logs\\autoutil.log"


def _failed_page(name: str, err: Exception) -> QWidget:
    log.exception("Не удалось создать раздел %s", name)
    page = QWidget()
    lbl = QLabel(t("failed.page", name=name, err=f"{type(err).__name__}: {err}", hint=LOG_HINT))
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
        self.journal = journal
        self.on_run_schema = on_run_schema
        default = prefs.default_section
        self._current_section = default if default in ("schema", "pending", "journal", "report", "rules", "settings") else "schema"
        self.setWindowTitle("AutoUtil")
        self.resize(1100, 720)
        self._build_ui()

    def _build_ui(self) -> None:
        """Собрать страницы/сайдбар/стек; вызывается и при смене языка."""
        factories = {
            "schema": lambda: SchemaPage(
                on_apply=self._on_schema_applied, on_run=self.on_run_schema,
                settings=self.settings, journal=self.journal,
            ),
            "pending": lambda: PendingPage(self.journal),
            "journal": lambda: JournalPage(self.journal, self.prefs),
            "report": lambda: ReportPage(self.journal),
            "rules": lambda: RulesPage(),
            "settings": lambda: SettingsPage(
                self.settings, self.prefs, self.apply_prefs,
                on_language_changed=self.apply_language,
            ),
        }
        names = {key: t(f"section.{key}") for key in factories}
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
        self.statusBar().showMessage(t("Готово"))

        section = self._current_section if self._current_section in self.pages else "schema"
        self.sidebar.select(section)
        self._switch(section)

    def apply_language(self) -> None:
        """Язык изменён в настройках: пересобрать интерфейс на новом языке."""
        old_central = self.centralWidget()
        old_section = self._current_section
        self._current_section = old_section
        self._build_ui()
        if old_central is not None:
            old_central.deleteLater()
        names = {"ru": "Русский", "en": "English"}
        self.statusBar().showMessage(
            t("settings.language_applied", lang=names.get(self.prefs.language, self.prefs.language))
        )

    def apply_prefs(self, prefs: UiPrefs) -> None:
        self.prefs = prefs
        apply_qss(QApplication.instance(), prefs)
        self.statusBar().showMessage(t("Настройки сохранены"))

    def _switch(self, key: str) -> None:
        self._current_section = key
        page = self.pages.get(key)
        if page is None:
            log.error("Нет раздела с ключом %s", key)
            return
        if hasattr(page, "reload"):
            try:
                page.reload()
            except Exception:
                log.exception("Ошибка при обновлении раздела %s", key)
                self.statusBar().showMessage(t("Ошибка в разделе: см. лог {hint}", hint=LOG_HINT))
        self.stack.setCurrentWidget(page)

    def show_section(self, key: str) -> None:
        self.sidebar.select(key)
        self._switch(key)
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_schema_applied(self, rules, folders: list[str]) -> None:
        self.pages["rules"].reload()
        self.statusBar().showMessage(t("Схема применена. Правила обновлены."))
