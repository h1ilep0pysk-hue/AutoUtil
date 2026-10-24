import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir

HISTORY_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "history.jsonl"
MAX_ITEMS = 20


@dataclass
class Capture:
    timestamp: str
    text: str


class History:
    def __init__(self, path: Path = HISTORY_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, text: str) -> None:
        item = Capture(timestamp=datetime.now(timezone.utc).isoformat(), text=text)
        with self._lock:
            items = self._read()
            items.append(item)
            self._write(items[-MAX_ITEMS:])

    def list(self) -> list:
        """От новых к старым."""
        with self._lock:
            return list(reversed(self._read()))

    def _read(self) -> list:
        if not self.path.exists():
            return []
            return []
        with self.path.open(encoding="utf-8") as f:
            return [Capture(**json.loads(line)) for line in f if line.strip()]

    def _write(self, items: list) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
        tmp.replace(self.path)