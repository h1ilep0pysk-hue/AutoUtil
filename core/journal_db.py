"""
SQLite‑based journal implementation.
Replaces the legacy JSONL journal.
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, List, Optional

from platformdirs import user_data_dir

log = logging.getLogger("autoutil.journal_db")

# Default path for the SQLite journal
JOURNAL_DB_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "journal.sqlite"

# SQL schema version – bump when schema changes
SCHEMA_VERSION = 1


@dataclass
class MoveEntry:
    id: str
    ts: str  # ISO timestamp UTC
    batch_id: Optional[str]
    rule_id: str
    action: str
    src: str
    dst: Optional[str]
    sha256: Optional[str]
    size: Optional[int]
    status: str
    undone_at: Optional[str] = None
    trashed: Optional[str] = None

    @staticmethod
    def from_row(row: sqlite3.Row) -> "MoveEntry":
        return MoveEntry(
            id=row["id"],
            ts=row["ts"],
            batch_id=row["batch_id"],
            rule_id=row["rule_id"],
            action=row["action"],
            src=row["src"],
            dst=row["dst"],
            sha256=row["sha256"],
            size=row["size"],
            status=row["status"],
            undone_at=row["undone_at"],
            trashed=row["trashed"] if "trashed" in row.keys() else None,
        )


class JournalDB:
    """Append‑only journal stored in SQLite.

    The class creates the database file on first use and performs a migration
    from the legacy JSONL file if it exists and the SQLite file does not.
    """

    def __init__(self, path: Path = JOURNAL_DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self._setup()
        self._maybe_migrate()

    def is_empty(self) -> bool:
        """Return True if no moves are stored in the DB."""
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM moves LIMIT 1")
        return cur.fetchone() is None


    # ---------------------------------------------------------------------
    # Schema handling
    # ---------------------------------------------------------------------
    def _setup(self) -> None:
        cur = self.conn.cursor()
        # Enable WAL for concurrency
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        # meta table for schema version
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        # moves table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS moves (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                batch_id TEXT,
                rule_id TEXT NOT NULL,
                action TEXT NOT NULL,
                src TEXT NOT NULL,
                dst TEXT,
                sha256 TEXT,
                size INTEGER,
                status TEXT NOT NULL,
                undone_at TEXT
            )
            """
        )
        # deferred table (future version – created now for simplicity)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS deferred (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                src TEXT NOT NULL,
                dst TEXT,
                rule TEXT NOT NULL,
                days INTEGER NOT NULL,
                ask INTEGER NOT NULL,
                bin INTEGER NOT NULL,
                due_ts TEXT NOT NULL,
                status TEXT NOT NULL,
                created_ts TEXT NOT NULL,
                lock_owner TEXT,
                lock_ts TEXT,
                error TEXT
            )
            """
        )
        # Ensure new columns exist (migration from older schema with only 'path' column)
        cur.execute("PRAGMA table_info(deferred)")
        cols = {row["name"] for row in cur.fetchall()}
        needed = {"src", "dst", "rule", "days", "ask", "bin"}
        for col in needed:
            if col not in cols:
                # Add column with a generic type; defaults will be set on insert.
                if col in {"ask", "bin"}:
                    cur.execute(f"ALTER TABLE deferred ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                elif col == "days":
                    cur.execute(f"ALTER TABLE deferred ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                else:
                    cur.execute(f"ALTER TABLE deferred ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

        cur.execute("CREATE INDEX IF NOT EXISTS idx_moves_src ON moves(src)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_moves_dst ON moves(dst)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_moves_status ON moves(status)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_deferred_status_due ON deferred(status, due_ts)"
        )
        # store schema version if not present
        cur.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        self.conn.commit()
        self._ensure_trashed_column()

    def _ensure_trashed_column(self) -> None:
        """Add 'trashed' column to moves if it does not exist (for undo tracking)."""
        cur = self.conn.cursor()
        try:
            cur.execute("ALTER TABLE moves ADD COLUMN trashed TEXT DEFAULT ''")
            self.conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

    # ---------------------------------------------------------------------
    # Migration from legacy JSONL journal
    # ---------------------------------------------------------------------
    def _maybe_migrate(self) -> None:
        legacy_path = Path(user_data_dir("AutoUtil", appauthor=False)) / "journal.jsonl"
        if not legacy_path.exists():
            return
        if self.path.exists():
            # SQLite already exists – do not overwrite
            return
        log.info("Migrating legacy journal %s to SQLite %s", legacy_path, self.path)
        # read legacy entries (reuse core.journal logic)
        try:
            from core import journal as legacy_mod
        except Exception as e:
            log.error("Unable to import legacy journal module for migration: %s", e)
            return
        # Create a temporary Journal instance to reuse its parsing
        legacy_journal = legacy_mod.Journal(path=legacy_path)
        entries = legacy_journal.read_all()
        cur = self.conn.cursor()
        for e in entries:
            # Map legacy fields to new schema – most fields correspond directly
            cur.execute(
                "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
                "VALUES (?, ?, NULL, ?, ?, ?, ?, NULL, NULL, ?)",
                (
                    e.id,
                    e.timestamp,
                    e.rule,
                    e.kind,
                    e.src,
                    e.dst,
                    "undone" if getattr(e, "undone", False) else "done",
                ),
            )
        self.conn.commit()
        # rename legacy file to keep backup
        backup = legacy_path.with_name(legacy_path.name + ".bak")
        try:
            legacy_path.rename(backup)
            log.info("Legacy journal renamed to %s", backup)
        except Exception as exc:
            log.warning("Could not rename legacy journal: %s", exc)

    # ---------------------------------------------------------------------
    # Public API – write operations
    # ---------------------------------------------------------------------
    def add_move(
        self,
        *,
        src: str,
        dst: str,
        rule_id: str,
        action: str,
        sha256: Optional[str] = None,
        size: Optional[int] = None,
        status: str = "done",
        batch_id: Optional[str] = None,
    ) -> str:
        """Insert a single move record and return its generated id.

        The caller provides a UUID string for the id – we generate it here for
        simplicity.
        """
        import uuid

        entry_id = uuid.uuid4().hex
        ts = datetime.now(timezone.utc).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id,
                ts,
                batch_id,
                rule_id,
                action,
                src,
                dst,
                sha256,
                size,
                status,
            ),
        )
        self.conn.commit()
        return entry_id

    def add_batch(self, moves: Iterable[dict[str, Any]]) -> List[str]:
        """Insert multiple move records in a single transaction.

        Each item in *moves* is a dict with the same keys accepted by *add_move*.
        Returns a list of generated ids in the same order.
        """
        ids: List[str] = []
        cur = self.conn.cursor()
        for m in moves:
            import uuid

            entry_id = uuid.uuid4().hex
            ids.append(entry_id)
            ts = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    ts,
                    m.get("batch_id"),
                    m.get("rule_id"),
                    m.get("action"),
                    m.get("src"),
                    m.get("dst"),
                    m.get("sha256"),
                    m.get("size"),
                    m.get("status", "done"),
                ),
            )
        self.conn.commit()
        return ids

    def mark_undone(self, move_id: str) -> None:
        """Mark a move as undone and set *undone_at* timestamp."""
        ts = datetime.now(timezone.utc).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE moves SET status='undone', undone_at=? WHERE id=?",
            (ts, move_id),
        )
        self.conn.commit()

    def set_trashed(self, move_id: str, trashed: str) -> None:
        """Store the path where the original source was moved during undo."""
        cur = self.conn.cursor()
        cur.execute("UPDATE moves SET trashed = ? WHERE id = ?", (trashed, move_id))
        self.conn.commit()

    # ---------------------------------------------------------------------
    # Deferred actions API (SQLite based)
    # ---------------------------------------------------------------------
    def add_deferred(self, src: str, dst: str, rule: str, days: int, ask: bool = False, bin: bool = False,
                     due_ts: str | None = None, status: str = "pending", created_ts: str | None = None) -> int:
        """Insert a deferred action and return its row id."""
        created = created_ts if created_ts is not None else datetime.now(timezone.utc).isoformat()
        if due_ts is not None:
            due = due_ts
        else:
            created_dt = datetime.fromisoformat(created)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            due = (created_dt + timedelta(days=days)).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO deferred (path, src, dst, rule, days, ask, bin, action, due_ts, status, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "",
                src,
                dst,
                rule,
                days,
                int(ask),
                int(bin),
                "",
                due,
                status,
                created,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_deferred(self) -> list[dict]:
        """Return all deferred rows as dicts."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM deferred")
        rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_deferred(self, item_id: int) -> dict | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM deferred WHERE id = ?", (item_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_deferred_by_src(self, src: str) -> dict | None:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM deferred WHERE src = ? AND status = 'pending'", (src,))
        row = cur.fetchone()
        return dict(row) if row else None

    def remove_deferred(self, item_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM deferred WHERE id = ?", (item_id,))
        self.conn.commit()

    def reclaim_stale(self) -> int:
        """Return number of rows reclaimed from running to pending."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE deferred SET status='pending', lock_owner=NULL, lock_ts=NULL WHERE status='running' AND lock_ts < ?",
            (cutoff.isoformat(),),
        )
        self.conn.commit()
        return cur.rowcount

    def acquire(self, item_id: int, owner: str) -> bool:
        """Attempt to mark a pending row as running for this owner.
        Returns True if acquisition succeeded."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE deferred SET status='running', lock_owner=?, lock_ts=? WHERE id=? AND status='pending'",
            (owner, now, item_id),
        )
        self.conn.commit()
        return cur.rowcount == 1

    # ---------------------------------------------------------------------
    # Query API
    # ---------------------------------------------------------------------
    def find_moves(
        self,
        name: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        rule_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[MoveEntry]:
        """Search moves with optional filters.

        *name* – substring search in the *src* path (case‑insensitive).
        *since* / *until* – filter by timestamp.
        *rule_id* – exact match.
        *status* – exact match.
        Results are ordered by *ts* descending.
        """
        clauses: List[str] = []
        params: List[Any] = []
        if name:
            clauses.append("LOWER(src) LIKE ?")
            params.append(f"%{name.lower()}%")
        if since:
            clauses.append("ts >= ?")
            params.append(since.isoformat())
        if until:
            clauses.append("ts <= ?")
            params.append(until.isoformat())
        if rule_id:
            clauses.append("rule_id = ?")
            params.append(rule_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            f"SELECT * FROM moves {where} ORDER BY ts DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        cur = self.conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [MoveEntry.from_row(row) for row in rows]

    def get_move(self, move_id: str) -> Optional[MoveEntry]:
        """Retrieve a single move by its id."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM moves WHERE id = ?", (move_id,))
        row = cur.fetchone()
        return MoveEntry.from_row(row) if row else None

    # ---------------------------------------------------------------------
    # Clean‑up helpers
    # ---------------------------------------------------------------------
    def close(self) -> None:
        self.conn.close()
