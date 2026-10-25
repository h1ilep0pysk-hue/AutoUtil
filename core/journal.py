import json
import shutil
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from platformdirs import user_data_dir

try:
    from send2trash import send2trash as _send2trash
except ImportError:
    _send2trash = None

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
    trashed: str = ""  # куда убран мешавший файл при откате: "корзина" или путь

_FIELDS = {f.name for f in fields(JournalEntry)}


def _unique_beside(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.stem} (старый {stamp}){path.suffix}")
    i = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} (старый {stamp}, {i}){path.suffix}")
        i += 1
    return candidate


def set_aside(path: Path) -> str:
    """Убирает файл с пути, чтобы не затереть его. Возвращает, куда он делся."""
    if _send2trash is not None:
        try:
            _send2trash(str(path))
            return "корзина"
        except Exception:
            pass
    target = _unique_beside(path)
    path.rename(target)
    return str(target)


class Journal:
    def __init__(self, path: Path = JOURNAL_PATH) -> None:
        self.path = path
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, entry: JournalEntry) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def _read_unlocked(self) -> list[JournalEntry]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                raw = json.loads(line)
                out.append(JournalEntry(**{k: v for k, v in raw.items() if k in _FIELDS}))
        return out

    def read_all(self) -> list[JournalEntry]:
        with self._lock:
            return self._read_unlocked()

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
        """Возвращает файл на место. Занятое место не затирается: мешающий файл уходит в корзину."""
        with self._lock:
            entries = self._read_unlocked()
            for e in entries:
                if e.id != entry_id or e.undone:
                    continue
                dst, src = Path(e.dst), Path(e.src)
                if not dst.exists():
                    return False
                src.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    e.trashed = set_aside(src)
                shutil.move(str(dst), str(src))
                e.undone = True
                self._rewrite(entries)
                return True
            return False

    def _rewrite(self, entries: list[JournalEntry]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with self._lock:
            with tmp.open("w", encoding="utf-8") as f:
                for e in entries:
                    f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
            tmp.replace(self.path)
