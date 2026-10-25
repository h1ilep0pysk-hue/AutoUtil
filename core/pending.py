"""Очередь «Спросить»: файлы, которые ждут решения пользователя. Хранится в pending.json."""
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir

PENDING_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "pending.json"
_lock = threading.Lock()


@dataclass
class PendingMove:
    id: str
    src: str
    dst: str
    rule: str
    created: str


class PendingStore:
    def __init__(self, path: Path = PENDING_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[PendingMove]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").strip() or "[]"
        return [PendingMove(**d) for d in json.loads(raw)]

    def _write(self, items: list[PendingMove]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def add(self, src: str, dst: str, rule: str) -> PendingMove:
        item = PendingMove(
            id=uuid.uuid4().hex,
            src=src,
            dst=dst,
            rule=rule,
            created=datetime.now(timezone.utc).isoformat(),
        )
        with _lock:
            items = self._read()
            items.append(item)
            self._write(items)
        return item

    def all_items(self) -> list[PendingMove]:
        with _lock:
            return self._read()

    def get(self, pending_id: str) -> PendingMove | None:
        for item in self.all_items():
            if item.id == pending_id:
                return item
        return None

    def remove(self, pending_id: str) -> None:
        with _lock:
            items = [i for i in self._read() if i.id != pending_id]
            self._write(items)
