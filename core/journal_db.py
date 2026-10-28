"""
SQLite‑based journal implementation.
Replaces the legacy JSONL journal.
"""

import json
import logging
import shutil
import sqlite3
import weakref
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

# Current schema of the deferred table. Legacy databases may still carry the
# older layout with ``path TEXT NOT NULL`` and ``action`` columns instead of
# ``src``/``rule``; _migrate_deferred_schema() upgrades them in place.
_DEFERRED_SCHEMA_SQL = """
            CREATE TABLE {name} (
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

# Columns of the current deferred schema (order matters for INSERT ... SELECT).
_DEFERRED_COLUMNS = [
    "id", "src", "dst", "rule", "days", "ask", "bin",
    "due_ts", "status", "created_ts", "lock_owner", "lock_ts", "error",
]


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


def _backup_before_migration(db_path: Path) -> Path | None:
    """Copy the database file before a deferred schema migration.

    Returns the backup path when a legacy schema (``path``/``action`` columns)
    was detected and the copy succeeded, or ``None`` when no migration is
    needed (current schema, absent table, or an in-memory database).

    Never runs without making the copy: if the copy fails, a RuntimeError is
    raised and the caller must not proceed with the migration. An existing
    backup is never overwritten — a timestamp suffix is appended instead.
    """
    if str(db_path) == ":memory:":
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        # Flush the WAL so the copy contains all committed rows.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(deferred)")}
    finally:
        conn.close()
    if "path" not in cols and "action" not in cols:
        return None
    backup = db_path.with_name(db_path.name + ".pre-migration.bak")
    if backup.exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = db_path.with_name(f"{db_path.name}.pre-migration.bak.{stamp}")
    try:
        shutil.copy2(str(db_path), str(backup))
    except OSError as exc:
        raise RuntimeError(
            f"Cannot create backup {backup} before deferred schema migration: "
            f"{exc}. Migration aborted to protect data."
        ) from exc
    return backup


class JournalDB:
    """Append‑only journal stored in SQLite.

    The class creates the database file on first use and performs a migration
    from the legacy JSONL file if it exists and the SQLite file does not.
    """

    def __init__(self, path: Path | None = None) -> None:
        # Resolved at call time so tests can patch JOURNAL_DB_PATH.
        self.path = path if path is not None else JOURNAL_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        # Close the SQLite connection when this object is collected;
        # otherwise the connection is finalized unclosed and emits a
        # ResourceWarning under -W error.
        weakref.finalize(self, self.conn.close)
        self._setup()
        self._maybe_migrate()

    def is_empty(self) -> bool:
        """Return True if no moves are stored in the DB."""
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM moves LIMIT 1")
        return cur.fetchone() is None

    # ---------------------------------------------------------------------
    # meta table (key/value flags, e.g. one-time migration markers)
    # ---------------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        """Return the value stored for *key* in meta, or None."""
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """Insert or update a meta flag."""
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()


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
        cur.execute(_DEFERRED_SCHEMA_SQL.format(name="IF NOT EXISTS deferred"))
        # Back up the db file before touching the schema; the migration runs
        # only if the backup succeeded (returns a path) or was not needed
        # (returns None for the current schema or an in-memory db). A failed
        # copy raises and the migration is never reached.
        backup = _backup_before_migration(self.path)
        if backup is not None:
            log.info("Backed up journal db to %s before schema migration", backup)
        # Upgrade a legacy deferred table (with path/action columns) in place.
        self._migrate_deferred_schema(cur)
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

    # ---------------------------------------------------------------------
    # Legacy deferred schema migration (path/action -> src/rule)
    # ---------------------------------------------------------------------
    def _migrate_deferred_schema(self, cur: sqlite3.Cursor) -> None:
        """Rebuild the deferred table if it still has legacy columns.

        Legacy databases carry ``path TEXT NOT NULL`` and ``action`` columns
        that no longer exist in the current schema, so INSERTs fail with
        NOT NULL constraint errors. The rebuild happens in a single
        transaction; on any error everything is rolled back. Idempotent:
        once the legacy columns are gone this is a no-op.
        """
        cur.execute("PRAGMA table_info(deferred)")
        old_cols = {row["name"] for row in cur.fetchall()}
        if "path" not in old_cols and "action" not in old_cols:
            return  # already on the current schema
        log.info("Migrating legacy deferred schema in %s", self.path)
        cur.execute("BEGIN")
        try:
            cur.execute(_DEFERRED_SCHEMA_SQL.format(name="deferred_new"))
            skipped = self._copy_deferred_rows(cur, old_cols)
            cur.execute("DROP TABLE deferred")
            cur.execute("ALTER TABLE deferred_new RENAME TO deferred")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_deferred_status_due "
                "ON deferred(status, due_ts)"
            )
        except Exception:
            self.conn.rollback()
            log.exception("Legacy deferred schema migration failed, rolled back")
            raise
        self.conn.commit()
        if skipped:
            log.warning(
                "Skipped %d deferred rows with both src and path empty", skipped
            )

    def _copy_deferred_rows(self, cur: sqlite3.Cursor, old_cols: set[str]) -> int:
        """Copy rows from legacy ``deferred`` into ``deferred_new``.

        Rows where ``src`` is empty but the legacy ``path`` is filled get
        ``path`` promoted to ``src``. Rows with both empty are dropped and
        counted in the return value. Isolated into a method so tests can
        force a failure here.
        """
        has_src = "src" in old_cols
        has_path = "path" in old_cols
        select_exprs: list[str] = []
        for col in _DEFERRED_COLUMNS:
            if col == "src" and has_path:
                if has_src:
                    select_exprs.append(
                        "CASE WHEN (src IS NULL OR src = '') AND path <> '' "
                        "THEN path ELSE src END"
                    )
                else:
                    select_exprs.append("path")
            elif col in old_cols:
                select_exprs.append(col)
            elif col == "id":
                select_exprs.append("NULL")  # let AUTOINCREMENT assign
            elif col in {"days", "ask", "bin"}:
                select_exprs.append("0")
            elif col in {"dst", "lock_owner", "lock_ts", "error"}:
                select_exprs.append("NULL")
            else:
                select_exprs.append("''")
        # Rows with both src and path empty carry no useful information.
        if has_src and has_path:
            skip_filter = "NOT ((src IS NULL OR src = '') AND (path IS NULL OR path = ''))"
        elif has_path:
            skip_filter = "path IS NOT NULL AND path <> ''"
        elif has_src:
            skip_filter = "src IS NOT NULL AND src <> ''"
        else:
            skip_filter = None
        (total,) = cur.execute("SELECT COUNT(*) FROM deferred").fetchone()
        kept = total
        if skip_filter:
            (kept,) = cur.execute(
                f"SELECT COUNT(*) FROM deferred WHERE {skip_filter}"
            ).fetchone()
        insert_sql = (
            f"INSERT INTO deferred_new ({', '.join(_DEFERRED_COLUMNS)}) "
            f"SELECT {', '.join(select_exprs)} FROM deferred"
        )
        if skip_filter:
            insert_sql += f" WHERE {skip_filter}"
        cur.execute(insert_sql)
        return total - kept

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
        legacy_path = JOURNAL_DB_PATH.parent / "journal.jsonl"
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
            "INSERT INTO deferred (src, dst, rule, days, ask, bin, due_ts, status, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                src,
                dst,
                rule,
                days,
                int(ask),
                int(bin),
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
