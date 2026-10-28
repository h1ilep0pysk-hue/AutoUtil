"""One-time import of legacy deferred.json into the SQLite deferred table.

Rules:
- The source file is never deleted. It is renamed to *.bak only after all
  inserts succeeded.
- Unknown root structure: file is kept untouched (status "kept").
- Any insert error: already inserted rows are removed again (status "error").
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("autoutil.deferred_migration")

_LIST_KEYS = ("items", "deferred", "entries", "actions")
_SRC_KEYS = ("src", "path", "file", "source")
_DST_KEYS = ("dst", "target", "dest", "destination")
_DUE_KEYS = ("due_ts", "due", "due_at", "due_time")
_CREATED_KEYS = ("created_ts", "created", "created_at")
_RULE_KEYS = ("rule", "rule_id")
_DONE_VALUES = ("done", "executed", "completed")
_BIN_ACTIONS = ("bin", "recycle", "trash")


@dataclass
class MigrationReport:
    imported: int = 0
    skipped_malformed: int = 0
    # no_file | migrated | error | kept | already_done
    status: str = "no_file"
    reason: str = ""


def _first(raw: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_datetime(value: Any) -> datetime | None:
    """Return an aware UTC datetime, or None. Accepts ISO strings and numeric timestamps."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _extract_items(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        if data and all(isinstance(v, dict) for v in data.values()):
            return list(data.values())
    return None


def _normalize(raw: Any) -> dict | None:
    """Turn one legacy entry into kwargs for JournalDB.add_deferred, or None if malformed."""
    if not isinstance(raw, dict):
        return None

    src = _first(raw, _SRC_KEYS)
    if not isinstance(src, str) or not src.strip():
        return None

    dst_raw = _first(raw, _DST_KEYS)
    dst = str(dst_raw) if dst_raw is not None else ""

    action_raw = str(raw.get("action", "")).lower()
    is_bin = bool(raw.get("bin")) or action_raw in _BIN_ACTIONS
    if not is_bin and not dst:
        return None

    days_raw = raw.get("days", 0)
    try:
        days = int(days_raw) if days_raw not in (None, "") else 0
    except (TypeError, ValueError):
        return None
    if days < 0:
        return None

    created = _parse_datetime(_first(raw, _CREATED_KEYS)) or datetime.now(timezone.utc)

    due = _parse_datetime(_first(raw, _DUE_KEYS))
    if due is None:
        # Only fall back to created + days when a day count is actually given;
        # an unparseable due_* value without days means the entry is malformed.
        if raw.get("days") is None:
            return None
        due = created + timedelta(days=days)

    status_raw = str(raw.get("status", "")).lower()
    done = status_raw in _DONE_VALUES or raw.get("done") is True

    return {
        "src": src,
        "dst": dst,
        "rule": str(_first(raw, _RULE_KEYS) or ""),
        "days": days,
        "ask": bool(raw.get("ask", False)),
        "bin": is_bin,
        "due_ts": due.isoformat(),
        "status": "done" if done else "pending",
        "created_ts": created.isoformat(),
    }


def _rename_to_bak(path: Path) -> None:
    bak = path.with_name(path.name + ".bak")
    if bak.exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        bak = path.with_name(f"{path.name}.bak.{stamp}")
    path.replace(bak)


def migrate_deferred_json(json_path: Path, db: Any) -> MigrationReport:
    report = MigrationReport()

    if not json_path.exists():
        report.status = "no_file"
        log.info("deferred migration: no_file imported=0 skipped_malformed=0")
        return report

    # One-time migration flag: if a previous run already imported the rows
    # (even if the final rename failed), do not insert them again.
    if db.get_meta("deferred_json_migrated") == "1":
        report.status = "already_done"
        log.info("deferred migration: already_done, %s left untouched", json_path)
        return report

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.status = "error"
        report.reason = f"unreadable: {exc}"
        log.error("deferred migration: cannot read %s: %s", json_path, exc)
        return report

    raw_items = _extract_items(data)
    if raw_items is None:
        report.status = "kept"
        report.reason = "unknown root structure"
        log.error("deferred migration: unknown structure in %s, file kept", json_path)
        return report

    prepared: list[dict] = []
    for index, raw in enumerate(raw_items):
        rec = _normalize(raw)
        if rec is None:
            report.skipped_malformed += 1
            log.warning("deferred migration: item %d skipped (malformed)", index)
            continue
        prepared.append(rec)

    inserted_ids: list[int] = []
    try:
        for rec in prepared:
            inserted_ids.append(db.add_deferred(**rec))
    except Exception as exc:  # noqa: BLE001 - rollback below, then report
        log.exception("deferred migration: insert failed, rolling back")
        for item_id in inserted_ids:
            try:
                db.remove_deferred(item_id)
            except Exception:  # noqa: BLE001
                log.exception("deferred migration: rollback failed for id=%s", item_id)
        report.status = "error"
        report.reason = f"insert failed: {exc}"
        return report

    report.imported = len(inserted_ids)

    # Set the one-time flag BEFORE renaming the file. If the rename fails,
    # the flag is already set, so the next run reports already_done and does
    # not duplicate the rows; the file stays in place for a manual rename.
    try:
        db.set_meta("deferred_json_migrated", "1")
    except Exception as exc:  # noqa: BLE001 - rollback below, then report
        log.exception("deferred migration: set_meta failed, rolling back inserts")
        for item_id in inserted_ids:
            try:
                db.remove_deferred(item_id)
            except Exception:  # noqa: BLE001
                log.exception("deferred migration: rollback failed for id=%s", item_id)
        report.status = "error"
        report.reason = f"set_meta failed: {exc}"
        return report

    report.status = "migrated"

    try:
        _rename_to_bak(json_path)
    except OSError as exc:
        # Rows are in the DB and the flag is set: a re-run is a safe no-op.
        # The file remains in place and can be renamed manually.
        report.reason = (
            f"rename failed, file kept in place (flag set, re-run is a no-op): {exc}"
        )
        log.error("deferred migration: %s", report.reason)

    log.info(
        "deferred migration: %s imported=%d skipped_malformed=%d",
        report.status, report.imported, report.skipped_malformed,
    )
    return report
