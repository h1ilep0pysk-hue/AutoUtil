import json
import shutil
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from platformdirs import user_data_dir

JOURNAL_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "journal.jsonl"


@dataclass
class JournalEntry:
    id: str
    timestamp: str
    kind: str          # "move"
    src: str
    dst: str
    rule: str
    undone: bool = False


class Journal:
    def __init__(self, path: Path = JOURNAL_PATH) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, entry: JournalEntry) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def read_all(self) -> list[JournalEntry]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [JournalEntry(**json.loads(line)) for line in f if line.strip()]

    def record_move(self, src: Path, dst: Path, rule: str) -> JournalEntry:
        """Записывает намерение до перемещения."""
        entry = JournalEntry(
            id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(),
            kind="move",
            src=str(src),
            dst=str(dst),
            rule=rule,
        )
        self._append(entry)
        return entry

    def undo(self, entry_id: str) -> bool:
        """Возвращает файл на место. Новая запись в журнале не нужна: помечаем исходную."""
        entries = self.read_all()
        for e in entries:
            if e.id == entry_id and not e.undone:
                dst, src = Path(e.dst), Path(e.src)
                if not dst.exists():
                    return False
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                e.undone = True
                self._rewrite(entries)
                return True
        return False

    def _rewrite(self, entries: list[JournalEntry]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with self._lock, tmp.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
        tmp.replace(self.path)