import ctypes
import sys

from PySide6.QtWidgets import QApplication
from pathlib import Path
from PySide6.QtGui import QIcon

from core.config import load_settings, save_settings
from core.events import ModeChanged, bus  # FIX
from core.i18n import set_language
from core.journal import Journal
from core.log import setup_logging
from core.notifier import Notifier
from core.prefs import load_prefs, save_prefs
from modules.organizer.service import OrganizerService
from ui.explorer import ExplorerWindow
from ui.explorer.theme import apply_qss
from ui.journal_view import JournalView
from ui.language_dialog import LanguageDialog
from ui.theme import apply_theme
from ui.tray import Tray
from ui.wizard import SetupWizard
from win.toast import show_toast

MUTEX_NAME = "Local\\AutoUtil_SingleInstance"
ERROR_ALREADY_EXISTS = 183
SECTIONS = {"schema", "pending", "journal", "report", "rules", "settings"}


if "--run-deferred" in sys.argv:
    from core.deferred_runner import run_due_deferred
    # Execute deferred actions and exit
    run_due_deferred()
    sys.exit(0)

def acquire_single_instance() -> int | None:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def main() -> int:
    if acquire_single_instance() is None:
        print("AutoUtil уже запущен.")
        return 1

    log = setup_logging()
    settings = load_settings()
    prefs = load_prefs()

    app = QApplication(sys.argv)
    ICON_PATH = Path(__file__).parent / "ui" / "assets" / "autoutil.ico"
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    apply_qss(app, prefs)

    # Language is asked once, before anything else is shown. Stored in prefs.toml.
    if not prefs.language:
        dialog = LanguageDialog()
        dialog.exec()
        prefs.language = dialog.choice
        save_prefs(prefs)
    set_language(prefs.language)

    if settings.first_run:
        wizard = SetupWizard(settings)
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            return 0
        save_settings(settings)

    journal = Journal()
    notifier = Notifier(sink=show_toast)
    bus.subscribe(ModeChanged, lambda e: notifier.on_mode_change(e.mode == "active"))  # FIX: уведомления после паузы/DND
    organizer = OrganizerService(settings.organizer, journal, notifier)
    if settings.organizer.watch_dirs:
        organizer.start()

    def run_schema(folders: list[str]) -> None:
        settings.organizer.watch_dirs = folders
        save_settings(settings)
        organizer.restart()
        log.info("Схема запущена, папки: %s", folders)

    tray = Tray(app)
    explorer = ExplorerWindow(settings, journal, prefs, on_run_schema=run_schema)
    tray.open_window = explorer.show_section
    tray.open_journal = lambda: JournalView(journal).exec()

    start_section = prefs.default_section if prefs.default_section in SECTIONS else "schema"
    explorer.show_section(start_section)

    log.info("AutoUtil запущен")
    code = app.exec()
    organizer.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())