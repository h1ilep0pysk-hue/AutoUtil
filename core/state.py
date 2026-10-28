import logging
import threading
from datetime import datetime, timedelta
from enum import Enum

from core.events import bus, ModeChanged

log = logging.getLogger("autoutil.state")


class Mode(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DND = "dnd"


class AppState:
    """Текущий режим работы. Потокобезопасен."""

    def __init__(self) -> None:
        self._mode = Mode.ACTIVE
        self._until: datetime | None = None
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None

    @property
    def mode(self) -> Mode:
        with self._lock:
            self._expire_if_needed()
            return self._mode

    def is_active(self) -> bool:
        """Можно ли сейчас перемещать файлы и показывать уведомления."""
        return self.mode == Mode.ACTIVE

    def set_mode(self, mode: Mode, until: datetime | None = None) -> None:
        with self._lock:
            self._cancel_timer()
            self._mode = mode
            self._until = until
            if mode == Mode.PAUSED and until is not None:
                self._schedule_resume(until)
        log.info("Режим: %s (до %s)", mode.value, until)
        bus.publish(ModeChanged(mode=mode.value))

    def pause_for(self, hours: float) -> None:
        self.set_mode(Mode.PAUSED, until=datetime.now() + timedelta(hours=hours))

    def toggle_dnd(self, enabled: bool) -> None:
        self.set_mode(Mode.DND if enabled else Mode.ACTIVE)

    def resume(self) -> None:
        self.set_mode(Mode.ACTIVE)

    def _expire_if_needed(self) -> None:
        # Вызывается под блокировкой.
        if self._until is not None and datetime.now() >= self._until:
            self._mode = Mode.ACTIVE
            self._until = None

    def _schedule_resume(self, until: datetime) -> None:
        # Вызывается под блокировкой.
        delay = max((until - datetime.now()).total_seconds(), 0)
        self._timer = threading.Timer(delay, self.resume)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        # Вызывается под блокировкой.
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


state = AppState()