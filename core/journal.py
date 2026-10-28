import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from platformdirs import user_data_dir

from core.journal_db import JournalDB
from core.i18n import t

try:
    from send2trash import send2trash as _send2trash
except ImportError:
    _send2trash = None

log = logging.getLogger("autoutil.journal")  # FIX

JOURNAL_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "journal.jsonl"

MAX_JOURNAL_BYTES = 10 * 1024 * 1024  # FIX: ротация — журнал не растёт бесконечно
KEEP_ROTATIONS = 3                    # сколько старых копий хранить рядом


@dataclass
class JournalEntry:
    id: str
    timestamp: str
    kind: str          # "move" | "bin" | "undo" (undo скрыт в read_all)
    src: str
    dst: str
    rule: str
    undone: bool = False
    trashed: str = ""  # куда убран мешавший файл при откате: "корзина" или путь

_FIELDS = {f.name for f in fields(JournalEntry)}


def _unique_beside(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.stem} ({t('journal.old_copy', stamp=stamp)}){path.suffix}")
    i = 1
    while candidate.exists():
        candidate = path.with_name(
            f"{path.stem} ({t('journal.old_copy_n', stamp=stamp, i=i)}){path.suffix}"
        )
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
    """Compatibility wrapper that delegates to the new SQLite‑based JournalDB.

    The original API (record_move, record_bin, undo, read_all) is preserved so
    existing UI and logic continue to work while the underlying storage uses
    SQLite. All file‑system operations remain unchanged; only persistence is
    redirected.
    """

    def __init__(self, path: Path = JOURNAL_PATH) -> None:
        # Path to legacy JSONL (used only for possible migration)
        self.path = path
        # SQLite DB alongside the legacy path
        db_path = path.parent / "journal.sqlite"
        self._db = JournalDB(path=db_path)
        self._lock = RLock()
        # Perform migration if legacy file exists and DB has no moves
        if self.path.exists() and self._db.is_empty():
            self._migrate_from_jsonl()


    def _migrate_from_jsonl(self) -> None:
        """Import entries from legacy JSONL file into SQLite DB.

        The legacy file is read line by line; malformed lines are skipped with a warning.
        After successful import, the file is renamed to *.bak to avoid re‑import.
        """
        legacy_path = self.path
        db = self._db
        with legacy_path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except Exception as e:
                    log.warning("Битая строка %d в legacy журнале пропущена: %s", lineno, e)
                    continue
                kind = raw.get("kind")
                if kind not in ("move", "bin"):
                    continue
                src = raw.get("src", "")
                dst = raw.get("dst", "")
                rule = raw.get("rule", "")
                status = "undone" if raw.get("undone", False) else "done"
                entry_id = raw.get("id") or uuid.uuid4().hex
                ts = raw.get("timestamp") or datetime.now(timezone.utc).isoformat()
                cur = db.conn.cursor()
                cur.execute(
                    "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
                    "VALUES (?, ?, NULL, ?, ?, ?, ?, NULL, NULL, ?)",
                    (entry_id, ts, rule, kind, src, dst, status),
                )
                db.conn.commit()
        backup_path = legacy_path.with_name(legacy_path.name + ".bak")
        try:
            legacy_path.rename(backup_path)
            log.info("Legacy journal %s renamed to %s", legacy_path, backup_path)
        except Exception as e:
            log.warning("Failed to rename legacy journal %s: %s", legacy_path, e)




    def _append(self, entry: JournalEntry) -> None:
        with self._lock:
            self._rotate_if_needed()
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def _rotate_if_needed(self) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < MAX_JOURNAL_BYTES:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotated = self.path.with_name(f"{self.path.stem}-{stamp}{self.path.suffix}")
        try:
            self.path.rename(rotated)
        except OSError:
            return
        log.info("Журнал достиг %.1f МБ, перенесён в %s", size / 1048576, rotated.name)
        olds = sorted(self.path.parent.glob(f"{self.path.stem}-*{self.path.suffix}"))
        for old in olds[:-KEEP_ROTATIONS]:
            try:
                old.unlink()
                log.info("Старая ротация журнала удалена: %s", old.name)
            except OSError:
                pass

    def _read_unlocked(self) -> list[JournalEntry]:
        if not self.path.exists():
            return []
        entries: list[JournalEntry] = []
        undos: dict[str, JournalEntry] = {}
        with self.path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:  # FIX: одна битая строка не должна ломать весь журнал
                    raw = json.loads(line)
                    entry = JournalEntry(**{k: v for k, v in raw.items() if k in _FIELDS})
                except (ValueError, TypeError) as e:
                    log.warning("Битая строка %d в журнале пропущена: %s", lineno, e)
                    continue
                if entry.kind == "undo":
                    if entry.dst:
                        undos.setdefault(entry.dst, entry)
                else:
                    entries.append(entry)
        # склейка: записи-откаты помечают исходные как возвращённые
        for e in entries:
            u = undos.get(e.id)
            if u is not None:
                e.undone = True
                e.trashed = u.trashed or e.trashed
        return entries

    def read_all(self) -> list[JournalEntry]:
        """Return all journal entries from the SQLite store, converted to the legacy format."""
        with self._lock:
            moves = self._db.find_moves(limit=1000000)
            entries: list[JournalEntry] = []
            for m in moves:
                entries.append(
                    JournalEntry(
                        id=m.id,
                        timestamp=m.ts,
                        kind=m.action,
                        src=m.src,
                        dst=m.dst or "",
                        rule=m.rule_id,
                        undone=(m.status == "undone"),
                        trashed=m.trashed if hasattr(m, "trashed") else "",
                    )
                )
            # sort chronologically
            entries.sort(key=lambda e: e.timestamp)
            return entries


    def record_move(self, src: Path, dst: Path, rule: str) -> JournalEntry:
        """Записывает перенос. Вызывать после успешного перемещения.
        Persists via SQLite and returns a compatible JournalEntry.
        """
        entry_id = self._db.add_move(
            src=str(src),
            dst=str(dst),
            rule_id=rule,
            action="move",
        )
        entry = JournalEntry(
            id=entry_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            kind="move",
            src=str(src),
            dst=str(dst),
            rule=rule,
        )
        # Append to legacy file for compatibility (now disabled)
        # self._append(entry)
        return entry


    def record_bin(self, src: Path, rule: str) -> JournalEntry:
        """Записывает отправку в корзину. Вызывать после успешного recycle()."""
        entry_id = self._db.add_move(
            src=str(src),
            dst="",
            rule_id=rule,
            action="bin",
        )
        entry = JournalEntry(
            id=entry_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            kind="bin",
            src=str(src),
            dst="",
            rule=rule,
        )
        # Append to legacy file for compatibility (now disabled)
        # self._append(entry)
        return entry


    def undo(self, entry_id: str) -> bool:
        """Возвращает файл на место и отмечает запись как undone в SQLite.
        Файловые операции остаются прежними.
        """
        with self._lock:
            # Retrieve the move entry from DB
            move = self._db.get_move(entry_id)
            if not move:
                return False
            if move.action == "bin" or not move.dst:
                return False
            dst, src = Path(move.dst), Path(move.src)
            if not dst.exists():
                return False
            src.parent.mkdir(parents=True, exist_ok=True)
            backup: Path | None = None
            if src.exists():
                backup = _unique_beside(src)
                src.rename(backup)
            try:
                shutil.move(str(dst), str(src))
            except Exception:
                if backup is not None:
                    backup.rename(src)
                raise
            trashed = set_aside(backup) if backup is not None else ""
            # Mark as undone in DB (status updated)
            self._db.mark_undone(entry_id)
            # Record trashed path for undo entry
            self._db.set_trashed(entry_id, trashed)
            # No legacy undo entry is recorded anymore.
            return True

