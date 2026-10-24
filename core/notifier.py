import logging
import threading
from dataclasses import dataclass
from typing import Callable

from core.state import state

log = logging.getLogger("autoutil.notifier")

WINDOW_SECONDS = 3.0


@dataclass
class Notice:
    title: str
    body: str
    action_label: str | None = None
    action: Callable[[], None] | None = None


class Notifier:
    """Собирает уведомления в пачку и выпускает одно за окно WINDOW_SECONDS.

    В режиме DND или паузе уведомления копятся и выходят сводкой
    при возврате в активный режим.
    """

    def __init__(self, sink: Callable[[Notice], None]) -> None:
        self._sink = sink
        self._pending: list[Notice] = []
        self._held: list[Notice] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def notify(self, notice: Notice) -> None:
        with self._lock:
            if not state.is_active():
                self._held.append(notice)
                return
            self._pending.append(notice)
            if self._timer is None:
                self._timer = threading.Timer(WINDOW_SECONDS, self._flush)
                self._timer.daemon = True
                self._timer.start()

    def on_mode_change(self, active: bool) -> None:
        """Вызывается при возврате в активный режим: выпускает накопленное."""
        if active:
            with self._lock:
                self._pending.extend(self._held)
                self._held.clear()
                if self._pending and self._timer is None:
                    self._timer = threading.Timer(WINDOW_SECONDS, self._flush)
                    self._timer.daemon = True
                    self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            batch, self._pending = self._pending, []
            self._timer = None
        if not batch:
            return
        if len(batch) == 1:
            self._sink(batch[0])
        else:
            self._sink(Notice(
                title="AutoUtil",
                body=f"Событий: {len(batch)}. Откройте журнал, чтобы посмотреть.",
            ))