import ctypes
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from core.config import load_settings, save_settings
from core.journal import Journal
from core.log import setup_logging
from core.notifier import Notifier
from modules.grabber.file_ocr import ocr_file
from modules.grabber.history import History
from modules.grabber.overlay import SelectionOverlay
from modules.grabber.pipeline import GrabPipeline
from modules.organizer.service import OrganizerService
from ui.journal_view import JournalView
from ui.settings_window import SettingsWindow
from ui.theme import apply_theme
from core.prefs import load_prefs
from ui.explorer.theme import apply_qss
from ui.tray import Tray
from ui.explorer import ExplorerWindow
from ui.wizard import SetupWizard
from win import shell_menu
from win.hotkeys import HotkeyListener
from win.toast import show_toast

MUTEX_NAME = "Global\\AutoUtil_SingleInstance"
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance() -> int | None:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


class _HotkeyBridge(QObject):
    triggered = Signal()


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--ocr-file":
        app = QApplication(sys.argv)
        ocr_file(sys.argv[2])
        return 0

    if acquire_single_instance() is None:
        print("AutoUtil уже запущен.")
        return 1

    log = setup_logging()
    settings = load_settings()
    prefs = load_prefs()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    apply_qss(app, prefs)

    if settings.first_run:
        wizard = SetupWizard(settings)
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            return 0
        save_settings(settings)

    journal = Journal()
    notifier = Notifier(sink=show_toast)
    history = History()
    pipeline = GrabPipeline(history=history, notifier=notifier)

    overlay = SelectionOverlay()
    overlay.selected.connect(pipeline.run_async)

    bridge = _HotkeyBridge()
    bridge.triggered.connect(overlay.start)
    hotkey = HotkeyListener(settings.grabber.hotkey, bridge.triggered.emit)
    if not hotkey.start():
        log.warning("Хоткей %s не зарегистрирован", settings.grabber.hotkey)

    organizer = OrganizerService(settings.organizer, journal, notifier)
    if settings.organizer.watch_dirs:
        organizer.start()

    if settings.shell_menu:
        shell_menu.install()

    tray = Tray(app, history)
    explorer = ExplorerWindow(settings, journal, history, prefs)
    tray.open_window = explorer.show_section
    tray.open_journal = lambda: JournalView(journal).exec()
    tray.open_settings = lambda: SettingsWindow(settings).exec()

    log.info("AutoUtil запущен")
    code = app.exec()
    hotkey.stop()
    organizer.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())