import json
import threading
from pathlib import Path

from platformdirs import user_data_dir

LEARNED_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "learned.json"
THRESHOLD = 2


class Learned:
    """Запоминает, куда пользователь сам переложил файлы определённого типа."""

    def __init__(self, path: Path = LEARNED_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def record(self, ext: str, folder: str) -> None:
        with self._lock:
            data = self._read()
            counts = data.setdefault(ext, {})
            counts[folder] = counts.get(folder, 0) + 1
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def preferred(self, ext: str) -> str | None:
        with self._lock:
            counts = self._read().get(ext, {})
        if not counts:
            return None
        folder, count = max(counts.items(), key=lambda kv: kv[1])
        return folder if count >= THRESHOLD else None
