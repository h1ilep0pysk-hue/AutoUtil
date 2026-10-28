"""Process due deferred actions.

Runs as a standalone process (invoked with ``--run-deferred``) or from the
UI scheduler. Uses the SQLite ``deferred`` table via :class:`core.journal_db.JournalDB`
and respects inter‑process locking.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import msvcrt

from core.journal_db import JournalDB
from modules.organizer.actions import recycle, apply_move, prepare_target
from core.journal import Journal

log = logging.getLogger("autoutil.deferred_runner")


@dataclass
class RunReport:
    done: int = 0
    skipped: int = 0
    failed: int = 0
    reclaimed: int = 0
    skipped_locked: bool = False


def _acquire_lock(lock_path: Path) -> tuple[bool, object | None]:
    """Try to acquire an exclusive non‑blocking lock on *lock_path*.
    Returns ``(acquired, file_handle)``.
    """
    try:
        f = lock_path.open("a+b")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return True, f
        except OSError:
            f.close()
            return False, None
    except Exception:
        return False, None


def _release_lock(fh) -> None:
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    finally:
        fh.close()


def run_due_deferred(db_path: Path | None = None, now: datetime | None = None, lock_path: Path | None = None) -> RunReport:
    """Process due deferred actions.

    *db_path* – optional path to ``journal.sqlite`` (defaults to the standard location).
    *now* – injected current time for testing.
    *lock_path* – path to the cross‑process lock file.
    """
    if lock_path is None:
        lock_path = Path(os.getenv("LOCALAPPDATA", "")) / "AutoUtil" / "runner.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

    acquired, lock_fh = _acquire_lock(lock_path)
    if not acquired:
        return RunReport(skipped_locked=True)

    try:
        report = RunReport()
        db = JournalDB(path=db_path) if db_path else JournalDB()
        now_dt = now or datetime.now(timezone.utc)

        # Reclaim stale running rows (>1h)
        reclaimed = db.reclaim_stale()
        report.reclaimed = reclaimed

        # Fetch pending items that are due
        cur = db.conn.cursor()
        cur.execute(
            "SELECT * FROM deferred WHERE status='pending' AND due_ts <= ? ORDER BY due_ts",
            (now_dt.isoformat(),),
        )
        rows = cur.fetchall()
        for row in rows:
            item_id = row["id"]
            # Attempt atomic capture
            owner = f"runner-{os.getpid()}"
            if not db.acquire(item_id, owner):
                continue
            src_path = Path(row["src"])
            if not src_path.exists():
                db.remove_deferred(item_id)
                report.skipped += 1
                continue
            try:
                if row["bin"]:
                    success = recycle(src_path)
                    if success:
                        Journal().record_bin(src_path, row["rule"])
                        report.done += 1
                    else:
                        report.failed += 1
                else:
                    dst_path = Path(row["dst"])
                    final_dst = prepare_target(dst_path)
                    apply_move(src_path, final_dst)
                    Journal().record_move(src_path, final_dst, row["rule"])
                    report.done += 1
                db.remove_deferred(item_id)
            except Exception as exc:
                log.exception("Deferred action failed for %s", src_path)
                # Record error text
                cur.execute("UPDATE deferred SET status='failed', error=? WHERE id=?", (str(exc), item_id))
                db.conn.commit()
                report.failed += 1
        return report
    finally:
        _release_lock(lock_fh)
