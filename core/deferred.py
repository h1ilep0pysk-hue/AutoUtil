"""Очередь «Через N дней»: файлы, действие над которыми отложено.

Хранится в deferred.json. Срок отсчитывается от времени изменения файла:
файл должен пролежать N дней, тогда действие (перенос, корзина, вопрос)
выполняется фоновым планировщиком. Проверка по возрасту самовосстанавливается:
если программа была выключена, она просто догонит график при следующем пуске.
"""
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir

DEFERRED_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "deferred.json"
_lock = threading.Lock()


@dataclass
class DeferredItem:
    id: str
    src: str
    dst: str
    rule: str
    days: int
    ask: bool = False
    bin: bool = False
    created: str = ""


class DeferredStore:
    def __init__(self, path: Path = DEFERRED_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[DeferredItem]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").strip() or "[]"
        return [DeferredItem(**d) for d in json.loads(raw)]

    def _write(self, items: list[DeferredItem]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def add(self, src: str, dst: str, rule: str, days: int,
            ask: bool = False, bin: bool = False) -> DeferredItem:
        item = DeferredItem(
            id=uuid.uuid4().hex,
            src=src,
            dst=dst,
            rule=rule,
            days=int(days),
            ask=bool(ask),
            bin=bool(bin),
            created=datetime.now(timezone.utc).isoformat(),
        )
        with _lock:
            items = self._read()
            items.append(item)
            self._write(items)
        return item

    def all_items(self) -> list[DeferredItem]:
        with _lock:
            return self._read()

    def get_for_src(self, src: str) -> DeferredItem | None:
        for item in self.all_items():
            if item.src == src:
                return item
        return None

    def get(self, item_id: str) -> DeferredItem | None:
        for item in self.all_items():
            if item.id == item_id:
                return item
        return None

    def remove(self, item_id: str) -> None:
        with _lock:
            items = [i for i in self._read() if i.id != item_id]
            self._write(items)
