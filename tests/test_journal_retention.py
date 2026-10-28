"""Срок хранения журнала: purge_older_than и настройка journal_retention_days.

Все БД создаются в tmp_path — %LOCALAPPDATA% не трогается (isolated_app_dir).
"""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.config import OrganizerSettings
from core.journal import Journal
from core.journal_db import JournalDB
from modules.organizer.service import OrganizerService


class _Recorder:
    def notify(self, notice) -> None:
        pass


def _db(tmp_path: Path) -> JournalDB:
    return JournalDB(tmp_path / "journal.sqlite")


def _insert(db: JournalDB, src: str, ts: datetime, status: str = "done",
            action: str = "move") -> str:
    """Прямая вставка с произвольной датой (add_move всегда ставит «сейчас»)."""
    move_id = uuid.uuid4().hex
    cur = db.conn.cursor()
    cur.execute(
        "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
        "VALUES (?, ?, NULL, 'r', ?, ?, 'C:/D', NULL, NULL, ?)",
        (move_id, ts.isoformat(), action, src, status),
    )
    db.conn.commit()
    return move_id


def _ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_purge_removes_old_done_and_undone(tmp_path):
    db = _db(tmp_path)
    _insert(db, "C:/old_done.pdf", _ago(400), status="done")
    _insert(db, "C:/old_undone.pdf", _ago(500), status="undone")

    removed = db.purge_older_than(365)

    assert removed == 2
    assert db.find_moves(limit=100) == []


def test_purge_keeps_recent_rows(tmp_path):
    db = _db(tmp_path)
    _insert(db, "C:/fresh.pdf", _ago(1))
    _insert(db, "C:/week.pdf", _ago(7))

    assert db.purge_older_than(365) == 0
    assert {m.src for m in db.find_moves(limit=100)} == {"C:/fresh.pdf", "C:/week.pdf"}


def test_purge_keeps_pending(tmp_path):
    db = _db(tmp_path)
    _insert(db, "C:/pending_old.pdf", _ago(1000), status="pending")

    assert db.purge_older_than(30) == 0
    assert [m.src for m in db.find_moves(limit=100)] == ["C:/pending_old.pdf"]


def test_purge_respects_zero_rows(tmp_path):
    db = _db(tmp_path)
    assert db.purge_older_than(365) == 0


def test_retention_setting_default_and_clamp():
    assert OrganizerSettings(journal_retention_days=0).journal_retention_days == 365
    assert OrganizerSettings(journal_retention_days=99999).journal_retention_days == 365
    assert OrganizerSettings(journal_retention_days=30).journal_retention_days == 30
    assert OrganizerSettings().journal_retention_days == 365


def test_purge_runs_once_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.organizer.service.documents_dir", lambda: tmp_path / "docs"
    )
    journal = Journal(tmp_path / "journal.jsonl")
    service = OrganizerService(
        OrganizerSettings(journal_retention_days=365), journal, _Recorder()
    )
    # __init__ уже сделал очистку; кладём старую строку уже после неё.
    _insert(journal.db, "C:/old.pdf", _ago(400), status="done")

    journal.db.set_meta("last_journal_purge", datetime.now(timezone.utc).isoformat())
    service._purge_journal()
    assert [m.src for m in journal.db.find_moves(limit=10)] == ["C:/old.pdf"], (
        "свежая отметка: очистка не должна запускаться"
    )

    journal.db.set_meta(
        "last_journal_purge",
        (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
    )
    service._purge_journal()
    assert journal.db.find_moves(limit=10) == [], "старше суток: очистка обязана пройти"
