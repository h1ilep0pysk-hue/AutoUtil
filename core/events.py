from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable
import logging

log = logging.getLogger("autoutil.events")

Handler = Callable[[Any], None]


@dataclass
class Event:
    """Базовый класс событий. Наследники задают свои поля."""
    pass



@dataclass
class FileMoved(Event):
    src: str
    dst: str
    rule: str


@dataclass
class FileTrashed(Event):
    src: str
    rule: str


@dataclass
class FileMoveFailed(Event):
    path: str
    reason: str


@dataclass
class ModeChanged(Event):
    mode: str  # "active" | "paused" | "dnd"


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[Event], handler: Handler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        for handler in list(self._handlers[type(event)]):
            try:
                handler(event)
            except Exception:
                # Ошибка одного подписчика не должна ломать остальных.
                log.exception("Ошибка в обработчике %s", type(event).__name__)




@dataclass
class PlanReady(Event):
    src: str
    dst: str
    rule: str

@dataclass
class PendingAdded(Event):
    src: str
    rule: str

bus = EventBus()
