import logging
from pathlib import Path

import pyperclip
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from core.events import FileMoved, ModeChanged, TextCaptured, bus
from core.state import Mode, state
from modules.grabber.history import History
from ui.explorer import ExplorerWindow  # noqa: F401

log = logging.getLogger("autoutil.tray")

ASSETS = Path(__file__).parent / "assets"

MODE_ICONS = {
    Mode.ACTIVE.value: "tray_idle.png",
    Mode.PAUSED.value: "tray_paused.png",
    Mode.DND.value: "tray_paused.png",
    "alert": "tray_alert.png",
}

MODE_TITLES = {
    Mode.ACTIVE.value: "AutoUtil: работает",
    Mode.PAUSED.value: "AutoUtil: пауза",
    Mode.DND.value: "AutoUtil: не беспокоить",
}


def _load_icon(key: str) -> QIcon:
    path = ASSETS / MODE_ICONS.get(key, "tray_idle.png")
    if path.exists():
        return QIcon(str(path))
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)


class _ModeBridge(QObject):
    """Передаёт события из фоновых потоков в главный поток Qt."""

    mode_changed = Signal(str)
    alert = Signal()


class Tray:
    def __init__(self, app: QApplication, history: History) -> None:
        self.app = app
        self.history = history
        self.open_journal = None
        self.open_window = None
        self._alert_on = False

        self._bridge = _ModeBridge()
        self._bridge.mode_changed.connect(self._apply_mode)
        self._bridge.alert.connect(self._set_alert)
        bus.subscribe(ModeChanged, lambda e: self._bridge.mode_changed.emit(e.mode))
        bus.subscribe(FileMoved, lambda e: self._bridge.alert.emit())
        bus.subscribe(TextCaptured, lambda e: self._bridge.alert.emit())

        self.tray = QSystemTrayIcon(_load_icon(Mode.ACTIVE.value), parent=app)
        self.tray.setToolTip(MODE_TITLES[Mode.ACTIVE.value])

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._on_menu_open)

        self.status_action = QAction(MODE_TITLES[Mode.ACTIVE.value])
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()

        self.pause_hour = QAction("Пауза на час")
        self.pause_hour.triggered.connect(lambda: state.pause_for(hours=1))
        self.menu.addAction(self.pause_hour)

        self.dnd = QAction("Не беспокоить")
        self.dnd.setCheckable(True)
        self.dnd.triggered.connect(lambda checked: state.toggle_dnd(checked))
        self.menu.addAction(self.dnd)

        self.recent_menu = QMenu("Последние захваты")
        self.menu.addMenu(self.recent_menu)

        self.menu.addSeparator()
        open_action = QAction("Открыть AutoUtil")
        open_action.triggered.connect(lambda: self.open_window and self.open_window("captures"))
        self.menu.addAction(open_action)
        self.menu.addSeparator()

        journal_action = QAction("Журнал")
        journal_action.triggered.connect(self._open_journal)
        self.menu.addAction(journal_action)

        settings_action = QAction("Настройки")
        settings_action.triggered.connect(self._open_settings)
        self.menu.addAction(settings_action)

        self.menu.addSeparator()
        quit_action = QAction("Выход")
        quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _on_menu_open(self) -> None:
        self._alert_on = False
        self._refresh_recent()
        self._apply_mode(state.mode.value)

    def _refresh_recent(self) -> None:
        self.recent_menu.clear()
        items = self.history.list()
        if not items:
            empty = QAction("Пока пусто")
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for item in items:
            preview = item.text if len(item.text) <= 60 else item.text[:57] + "..."
            action = QAction(preview.replace("\n", " "))
            action.triggered.connect(lambda _=False, t=item.text: pyperclip.copy(t))
            self.recent_menu.addAction(action)

    def _open_journal(self) -> None:
        if self.open_journal:
            self.open_journal()
        else:
            log.info("Окно журнала не подключено")

    def _open_settings(self) -> None:
        if self.open_settings:
            self.open_settings()
        else:
            log.info("Окно настроек не подключено")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick and self.open_window:
            self.open_window("captures")

    def _set_alert(self) -> None:
        self._alert_on = True
        self.tray.setIcon(_load_icon("alert"))

    def _apply_mode(self, mode: str) -> None:
        title = MODE_TITLES.get(mode, MODE_TITLES[Mode.ACTIVE.value])
        if not self._alert_on:
            self.tray.setIcon(_load_icon(mode))
        self.tray.setToolTip(title)
        self.status_action.setText(title)
        self.dnd.setChecked(mode == Mode.DND.value)
        log.info("Режим в трее: %s", mode)