import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from core.events import FileMoved, ModeChanged, PendingAdded, bus
from core.i18n import t
from core.state import Mode, state

log = logging.getLogger("autoutil.tray")

ASSETS = Path(__file__).parent / "assets"

MODE_ICONS = {
    Mode.ACTIVE.value: "tray_idle.png",
    Mode.PAUSED.value: "tray_paused.png",
    Mode.DND.value: "tray_paused.png",
    "alert": "tray_alert.png",
}

MODE_TITLE_KEYS = {
    Mode.ACTIVE.value: "tray.active",
    Mode.PAUSED.value: "tray.paused",
    Mode.DND.value: "tray.dnd",
}


def _mode_title(mode: str) -> str:
    return t(MODE_TITLE_KEYS.get(mode, "tray.active"))


def _load_icon(key: str) -> QIcon:
    path = ASSETS / MODE_ICONS.get(key, "tray_idle.png")
    if path.exists():
        return QIcon(str(path))
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)


class _ModeBridge(QObject):
    mode_changed = Signal(str)
    alert = Signal()


class Tray:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.open_window = None
        self.open_journal = None
        self._alert_on = False

        self._bridge = _ModeBridge()
        self._bridge.mode_changed.connect(self._apply_mode)
        self._bridge.alert.connect(self._set_alert)
        bus.subscribe(ModeChanged, lambda e: self._bridge.mode_changed.emit(e.mode))
        bus.subscribe(FileMoved, lambda e: self._bridge.alert.emit())
        bus.subscribe(PendingAdded, lambda e: self._bridge.alert.emit())

        self.tray = QSystemTrayIcon(_load_icon(Mode.ACTIVE.value), parent=app)
        self.tray.setToolTip(_mode_title(Mode.ACTIVE.value))

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._on_menu_open)

        self.status_action = QAction(_mode_title(Mode.ACTIVE.value))
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()

        self.pause_hour = QAction(t("tray.pause_hour"))
        self.pause_hour.triggered.connect(lambda: state.pause_for(hours=1))
        self.menu.addAction(self.pause_hour)

        self.dnd = QAction(t("tray.dnd_action"))
        self.dnd.setCheckable(True)
        self.dnd.triggered.connect(lambda checked: state.toggle_dnd(checked))
        self.menu.addAction(self.dnd)

        self.menu.addSeparator()
        open_action = QAction(t("tray.open"))
        open_action.triggered.connect(lambda: self.open_window and self.open_window("schema"))
        self.menu.addAction(open_action)

        journal_action = QAction(t("tray.journal"))
        journal_action.triggered.connect(self._open_journal)
        self.menu.addAction(journal_action)

        settings_action = QAction(t("tray.settings"))
        settings_action.triggered.connect(self._open_settings)
        self.menu.addAction(settings_action)

        self.menu.addSeparator()
        quit_action = QAction(t("tray.quit"))
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _on_menu_open(self) -> None:
        self._alert_on = False
        self._apply_mode(state.mode.value)

    def _open_journal(self) -> None:
        if self.open_journal:
            self.open_journal()
        else:
            log.info("Окно журнала не подключено")

    def _open_settings(self) -> None:
        if self.open_window:
            self.open_window("settings")
        else:
            log.info("Окно настроек не подключено")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick and self.open_window:
            self.open_window("schema")

    def _set_alert(self) -> None:
        self._alert_on = True
        self.tray.setIcon(_load_icon("alert"))

    def _apply_mode(self, mode: str) -> None:
        title = _mode_title(mode)
        if not self._alert_on:
            self.tray.setIcon(_load_icon(mode))
        self.tray.setToolTip(title)
        self.status_action.setText(title)
        self.dnd.setChecked(mode == Mode.DND.value)
        log.info("Режим в трее: %s", mode)
