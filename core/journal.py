import json
import logging
import shutil
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from platformdirs import user_data_dir

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
    """Append-only журнал: записи только дописываются, файл целиком не переписывается.

    Откат (undo) дописывает запись kind="undo" со ссылкой на исходную —
    read_all() склеивает их при чтении. Ротация по размеру держит файл
    в пределах MAX_JOURNAL_BYTES.
    """

    def __init__(self, path: Path = JOURNAL_PATH) -> None:
        self.path = path
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

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
        with self._lock:
            return self._read_unlocked()

    def record_move(self, src: Path, dst: Path, rule: str) -> JournalEntry:
        """Записывает перенос. Вызывать после успешного перемещения."""
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

    def record_bin(self, src: Path, rule: str) -> JournalEntry:
        """Записывает отправку в корзину. Вызывать после успешного recycle()."""
        entry = JournalEntry(
            id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc).isoformat(),
            kind="bin",
            src=str(src),
            dst="",
            rule=rule,
        )
        self._append(entry)
        return entry

    def undo(self, entry_id: str) -> bool:
        """Возвращает файл на место. Мешающий файл сначала переименовывается, потом уходит в корзину.

        FIX: факт отката дописывается в журнал отдельной записью (append-only),
        вместо переписывания всего файла.
        """
        with self._lock:
            entries = self._read_unlocked()
            for e in entries:
                if e.id != entry_id or e.undone:
                    continue
                if e.kind == "bin" or not e.dst:
                    # Файл уже в корзине — вернуть может только сама корзина.
                    return False
                dst, src = Path(e.dst), Path(e.src)
                if not dst.exists():
                    return False
                src.parent.mkdir(parents=True, exist_ok=True)

                backup: Path | None = None  # FIX: мешающий файл не удаляется до успешного возврата
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
                self._append(JournalEntry(
                    id=uuid.uuid4().hex,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    kind="undo",
                    src="",
                    dst=entry_id,
                    rule="",
                    undone=True,
                    trashed=trashed,
                ))
                return True
            return False
