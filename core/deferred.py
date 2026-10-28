"""SQLite‑based deferred actions storage.

Provides the same API as the legacy JSON implementation but operates on
the ``deferred`` table in ``journal.sqlite`` via :class:`core.journal_db.JournalDB`.
"""

import threading
from datetime import datetime, timezone
from typing import List, Optional

from core.config import APP_DIR
from core.journal_db import JournalDB
from core.deferred_migration import migrate_deferred_json

_deferred_lock = threading.Lock()


class DeferredItem:
    """Data class mirroring the columns of the ``deferred`` table."""

    def __init__(
        self,
        id: int,
        src: str,
        dst: str,
        rule: str,
        days: int,
        ask: bool,
        bin: bool,
        due_ts: str,
        status: str,
        created_ts: str,
        lock_owner: Optional[str] = None,
        lock_ts: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self.id = id
        self.src = src
        self.dst = dst
        self.rule = rule
        self.days = days
        self.ask = bool(ask)
        self.bin = bool(bin)
        self.due_ts = due_ts
        self.status = status
        self.created_ts = created_ts
        self.lock_owner = lock_owner
        self.lock_ts = lock_ts
        self.error = error

    @classmethod
    def from_row(cls, row: dict) -> "DeferredItem":
        return cls(
            id=row["id"],
            src=row["src"],
            dst=row["dst"],
            rule=row["rule"],
            days=row["days"],
            ask=bool(row["ask"]),
            bin=bool(row["bin"]),
            due_ts=row["due_ts"],
            status=row["status"],
            created_ts=row["created_ts"],
            lock_owner=row["lock_owner"],
            lock_ts=row["lock_ts"],
            error=row["error"],
        )


class DeferredStore:
    def __init__(self, db: JournalDB | None = None) -> None:
        self._db = db if db is not None else JournalDB()

    def _ensure_migrated(self) -> None:
        # Must be called while holding _deferred_lock.
        if getattr(self, "_migration_checked", False):
            return
        self._migration_checked = True
        migrate_deferred_json(APP_DIR / "deferred.json", self._db)

    def add(self, src: str, dst: str, rule: str, days: int, ask: bool = False, bin: bool = False) -> DeferredItem:
        with _deferred_lock:
            self._ensure_migrated()
            row_id = self._db.add_deferred(src, dst, rule, days, ask, bin)
            # Fetch the inserted row to return a full object
            row = self._db.get_deferred(row_id)
            return DeferredItem.from_row(row)

    def all_items(self) -> List[DeferredItem]:
        with _deferred_lock:
            self._ensure_migrated()
            rows = self._db.list_deferred()
            return [DeferredItem.from_row(r) for r in rows]

    def get_for_src(self, src: str) -> Optional[DeferredItem]:
        with _deferred_lock:
            self._ensure_migrated()
            row = self._db.get_deferred_by_src(src)
            return DeferredItem.from_row(row) if row else None

    def get(self, item_id: int) -> Optional[DeferredItem]:
        with _deferred_lock:
            self._ensure_migrated()
            row = self._db.get_deferred(item_id)
            return DeferredItem.from_row(row) if row else None

    def remove(self, item_id: int) -> None:
        with _deferred_lock:
            self._ensure_migrated()
            self._db.remove_deferred(item_id)
