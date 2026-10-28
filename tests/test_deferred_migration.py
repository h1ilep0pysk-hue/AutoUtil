import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.deferred_migration import _parse_datetime, migrate_deferred_json


class FakeDB:
    """Mirrors the JournalDB.add_deferred signature used in production."""

    def __init__(self, fail_on_call: int | None = None):
        self.rows: dict[int, dict] = {}
        self.calls = 0
        self.fail_on_call = fail_on_call
        self._next = 1

    def add_deferred(self, src, dst, rule, days, ask=False, bin=False,
                     due_ts=None, status="pending", created_ts=None):
        self.calls += 1
        if self.fail_on_call is not None and self.calls == self.fail_on_call:
            raise RuntimeError("boom")
        i = self._next
        self._next += 1
        self.rows[i] = {
            "src": src, "dst": dst, "rule": rule, "days": days, "ask": ask,
            "bin": bin, "due_ts": due_ts, "status": status, "created_ts": created_ts,
        }
        return i

    def remove_deferred(self, item_id):
        self.rows.pop(item_id, None)


def _due(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _write(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _entry(src="C:/x/a.pdf", dst="C:/Docs", status="pending", **extra):
    base = {"src": src, "dst": dst, "due_ts": _due(), "status": status}
    base.update(extra)
    return base


def test_call_matches_journal_db_signature():
    from core.journal_db import JournalDB
    params = inspect.signature(JournalDB.add_deferred).parameters
    for name in ("src", "dst", "rule", "days", "ask", "bin", "due_ts", "status", "created_ts"):
        assert name in params, f"JournalDB.add_deferred lacks {name}"


def test_no_file_is_noop(tmp_path):
    db = FakeDB()
    rep = migrate_deferred_json(tmp_path / "deferred.json", db)
    assert rep.status == "no_file"
    assert db.rows == {}


def test_pending_and_done_imported(tmp_path):
    path = tmp_path / "deferred.json"
    _write(path, [_entry(src="a.pdf", status="pending"), _entry(src="b.pdf", status="done")])
    db = FakeDB()
    rep = migrate_deferred_json(path, db)
    assert rep.status == "migrated"
    assert rep.imported == 2
    assert {r["src"]: r["status"] for r in db.rows.values()} == {"a.pdf": "pending", "b.pdf": "done"}


def test_malformed_skipped(tmp_path):
    path = tmp_path / "deferred.json"
    _write(path, [
        {"dst": "C:/Docs", "due_ts": _due()},          # no src
        _entry(src="bad.pdf", due_ts="not-a-date"),    # bad date, no days fallback
        _entry(src="ok.pdf"),
    ])
    db = FakeDB()
    rep = migrate_deferred_json(path, db)
    assert rep.imported == 1
    assert rep.skipped_malformed == 2
    assert [r["src"] for r in db.rows.values()] == ["ok.pdf"]


def test_due_from_days_when_due_missing(tmp_path):
    path = tmp_path / "deferred.json"
    created = "2030-01-01T10:00:00+00:00"
    _write(path, [{"src": "a.pdf", "dst": "C:/D", "days": 3, "created_ts": created}])
    db = FakeDB()
    rep = migrate_deferred_json(path, db)
    assert rep.imported == 1
    assert db.rows[1]["due_ts"].startswith("2030-01-04T10:00:00")


def test_wrapped_list_and_numeric_timestamp(tmp_path):
    path = tmp_path / "deferred.json"
    ts = datetime.now(timezone.utc).timestamp() + 3600
    _write(path, {"items": [{"src": "a.pdf", "dst": "C:/D", "due": ts}]})
    db = FakeDB()
    rep = migrate_deferred_json(path, db)
    assert rep.imported == 1


def test_renames_to_bak(tmp_path):
    path = tmp_path / "deferred.json"
    _write(path, [_entry()])
    migrate_deferred_json(path, FakeDB())
    assert not path.exists()
    assert (tmp_path / "deferred.json.bak").exists()


def test_bak_not_overwritten(tmp_path):
    path = tmp_path / "deferred.json"
    bak = tmp_path / "deferred.json.bak"
    bak.write_text("OLD", encoding="utf-8")
    _write(path, [_entry()])
    rep = migrate_deferred_json(path, FakeDB())
    assert rep.status == "migrated"
    assert bak.read_text(encoding="utf-8") == "OLD"
    assert not path.exists()
    assert any(p.name.startswith("deferred.json.bak.") for p in tmp_path.iterdir())


def test_idempotent(tmp_path):
    path = tmp_path / "deferred.json"
    _write(path, [_entry(), _entry(src="b.pdf")])
    db = FakeDB()
    migrate_deferred_json(path, db)
    first = len(db.rows)
    rep = migrate_deferred_json(path, db)
    assert rep.status == "no_file"
    assert len(db.rows) == first


def test_rollback_on_insert_error(tmp_path):
    path = tmp_path / "deferred.json"
    _write(path, [_entry(src="a.pdf"), _entry(src="b.pdf"), _entry(src="c.pdf")])
    db = FakeDB(fail_on_call=2)
    rep = migrate_deferred_json(path, db)
    assert rep.status == "error"
    assert db.rows == {}
    assert path.exists()
    assert not (tmp_path / "deferred.json.bak").exists()


def test_broken_json_untouched(tmp_path):
    path = tmp_path / "deferred.json"
    path.write_text("{not json", encoding="utf-8")
    db = FakeDB()
    rep = migrate_deferred_json(path, db)
    assert rep.status == "error"
    assert path.read_text(encoding="utf-8") == "{not json"
    assert db.rows == {}


def test_unknown_structure_kept(tmp_path):
    path = tmp_path / "deferred.json"
    _write(path, {"version": 1, "weird": 42})
    rep = migrate_deferred_json(path, FakeDB())
    assert rep.status == "kept"
    assert path.exists()


@pytest.mark.parametrize("value,expected", [
    ("2030-01-01T10:00:00", True),
    ("2030-01-01T10:00:00Z", True),
    ("nope", False),
    (None, False),
    (True, False),
])
def test_parse_datetime(value, expected):
    assert (_parse_datetime(value) is not None) is expected


def test_deferred_store_picks_up_legacy_file(tmp_path, monkeypatch):
    """Integration: DeferredStore over real JournalDB imports legacy deferred.json."""
    from core import deferred as deferred_mod
    from core.journal_db import JournalDB

    monkeypatch.setattr(deferred_mod, "APP_DIR", tmp_path)

    _write(tmp_path / "deferred.json", [_entry(src="legacy.pdf", dst="C:/Docs")])

    store = deferred_mod.DeferredStore(JournalDB(tmp_path / "journal.sqlite"))
    items = store.all_items()

    assert [i.src for i in items] == ["legacy.pdf"]
    assert not (tmp_path / "deferred.json").exists()
    assert (tmp_path / "deferred.json.bak").exists()

    # Close the underlying connection so the GC does not raise
    # ResourceWarning/PytestUnraisableExceptionWarning in later tests.
    store._db.conn.close()
