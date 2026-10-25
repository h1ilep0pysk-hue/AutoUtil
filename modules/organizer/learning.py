import json
import threading
from pathlib import Path

from platformdirs import user_data_dir

LEARNED_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "learned.json"
THRESHOLD = 3  # сколько одинаковых ручных переносов нужно для предложения


class Learned:
    """Ключ = «правило|расширение». Значение: счётчики папок и принятая папка."""

    def __init__(self, path: Path = LEARNED_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _entry(data: dict, key: str) -> dict:
        e = data.get(key)
        if not isinstance(e, dict):
            e = {}
            data[key] = e
        e.setdefault("counts", {})
        e.setdefault("accepted", None)
        return e

    def record(self, key: str, folder: str) -> None:
        """Записывает, что правило+расширение пользователем помещено в папку."""
        if not folder:
            return
        with self._lock:
            data = self._read()
            e = self._entry(data, key)
            e["counts"][folder] = e["counts"].get(folder, 0) + 1
            self._write(data)

    def suggestions(self) -> list[tuple[str, str, int]]:
        with self._lock:
            data = self._read()
        out = []
        for key, e in data.items():
            if not isinstance(e, dict) or e.get("accepted"):
                continue
            counts = e.get("counts") or {}
            if not counts:
                continue
            folder, count = max(counts.items(), key=lambda kv: kv[1])
            if count >= THRESHOLD:
                out.append((key, folder, count))
        return out

    def accept(self, key: str) -> None:
        with self._lock:
            data = self._read()
            e = data.get(key)
            if not isinstance(e, dict) or not e.get("counts"):
                return
            e["accepted"] = max(e["counts"].items(), key=lambda kv: kv[1])[0]
            self._write(data)

    def reject(self, key: str) -> None:
        with self._lock:
            data = self._read()
            e = data.get(key)
            if isinstance(e, dict):
                e["counts"] = {}
                e["accepted"] = None
                self._write(data)

    def preferred(self, key: str) -> str | None:
        with self._lock:
            data = self._read()
        e = data.get(key)
        if isinstance(e, dict) and e.get("accepted"):
            return e["accepted"]
        return None
