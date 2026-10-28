"""Quarantine for duplicate copies: move, never overwrite, keep a journal.

Order of operations for every file is fixed:
1. journal row is created with status "pending" (before anything is touched);
2. the kept file is re-checked — if it changed, the whole group is aborted
   and the row is marked "failed";
3. the file is moved (``Path.replace``) — on OSError the row is "failed";
4. the row is marked "done". If this last step fails, the file is already
   in quarantine and the row stays "pending" for the next run to reconcile.

Nothing is ever deleted here: files are moved aside and purged by age later.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import config
from modules.organizer.dedupe_groups import DupGroup, keep_still_valid

log = logging.getLogger("autoutil.quarantine")


def quarantine_dir(now: datetime | None = None) -> Path:
    """Today's quarantine folder (UTC date), e.g. <app>/quarantine/2026-10-28."""
    moment = now or datetime.now(timezone.utc)
    return config.APP_DIR / "quarantine" / moment.strftime("%Y-%m-%d")


def quarantine_target(src: Path, base: Path) -> Path:
    """Free path for *src* inside *base*; never returns an existing file."""
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / src.name
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = base / f"{src.stem}_{index}{src.suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _as_db(journal):
    """Accept either Journal or JournalDB."""
    return getattr(journal, "db", journal)


def move_to_quarantine(group: DupGroup, journal, rule_name: str) -> list[Path]:
    """Move ``group.remove`` into quarantine; return the new paths."""
    db = _as_db(journal)
    base = quarantine_dir()
    moved: list[Path] = []
    for src in group.remove:
        target = quarantine_target(src, base)
        try:
            move_id = db.add_move(
                src=str(src), dst=str(target), rule_id=rule_name, action="move",
                sha256=group.digest, size=group.size, status="pending",
            )
        except Exception:
            log.exception("quarantine: journal write failed, file kept: %s", src)
            continue

        if not keep_still_valid(group):
            log.warning(
                "quarantine: kept file changed, group aborted (keep=%s)", group.keep
            )
            try:
                db.set_status(move_id, "failed")
            except Exception:
                log.exception("quarantine: could not mark %s failed", move_id)
            break

        try:
            src.replace(target)
        except OSError:
            log.warning("quarantine: move failed for %s -> %s", src, target)
            try:
                db.set_status(move_id, "failed")
            except Exception:
                log.exception("quarantine: could not mark %s failed", move_id)
            continue

        try:
            db.set_status(move_id, "done")
        except Exception:
            # The file is already in quarantine; the row stays "pending" and
            # is reconciled by the presence of the file on the next run.
            log.exception("quarantine: could not mark %s done, stays pending", move_id)
            continue
        moved.append(target)
    return moved


def purge_quarantine(retention_days: int = 30, now: datetime | None = None) -> int:
    """Delete quarantine date folders older than *retention_days*.

    Returns the number of removed folders. Folders whose name is not a date
    are left untouched.
    """
    root = config.APP_DIR / "quarantine"
    if not root.is_dir():
        return 0
    moment = now or datetime.now(timezone.utc)
    cutoff = (moment - timedelta(days=retention_days)).date()
    removed = 0
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            folder_date = datetime.strptime(child.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if folder_date < cutoff:
            shutil.rmtree(child)
            removed += 1
            log.info("quarantine: removed old folder %s", child.name)
    return removed
