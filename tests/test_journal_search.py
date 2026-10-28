"""Поиск и пагинация журнала: JournalDB.find_moves / Journal.find_entries."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.journal import Journal
from core.journal_db import JournalDB


def _db(tmp_path: Path) -> JournalDB:
    return JournalDB(tmp_path / "journal.sqlite")


def _insert(db: JournalDB, src: str, ts: datetime, status: str = "done") -> str:
    move_id = uuid.uuid4().hex
    cur = db.conn.cursor()
    cur.execute(
        "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
        "VALUES (?, ?, NULL, 'r', 'move', ?, 'C:/D', NULL, NULL, ?)",
        (move_id, ts.isoformat(), src, status),
    )
    return move_id


def _seed(db: JournalDB, rows: list[tuple[str, datetime]]) -> None:
    for src, ts in rows:
        _insert(db, src, ts)
    db.conn.commit()


def test_find_moves_by_name_substring(tmp_path):
    db = _db(tmp_path)
    now = datetime.now(timezone.utc)
    _seed(db, [
        ("C:/Docs/Отчёт_2026.pdf", now),
        ("C:/Docs/report_final.pdf", now),
        ("C:/Music/song.mp3", now),
    ])

    found = db.find_moves(name="отчёт")
    assert [m.src for m in found] == ["C:/Docs/Отчёт_2026.pdf"]

    found = db.find_moves(name="REPORT")  # регистр не важен
    assert [m.src for m in found] == ["C:/Docs/report_final.pdf"]

    assert db.find_moves(name="нет-такого") == []


def test_find_moves_by_date_range(tmp_path):
    db = _db(tmp_path)
    base = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    _seed(db, [
        ("C:/a.pdf", base - timedelta(days=10)),
        ("C:/b.pdf", base),
        ("C:/c.pdf", base + timedelta(days=10)),
    ])

    found = db.find_moves(
        since=base - timedelta(days=1), until=base + timedelta(days=1)
    )
    assert [m.src for m in found] == ["C:/b.pdf"]

    found = db.find_moves(since=base)
    assert {m.src for m in found} == {"C:/b.pdf", "C:/c.pdf"}

    found = db.find_moves(until=base)
    assert {m.src for m in found} == {"C:/a.pdf", "C:/b.pdf"}


def test_find_moves_pagination(tmp_path):
    db = _db(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _seed(db, [(f"C:/file_{i:03d}.pdf", base + timedelta(minutes=i)) for i in range(450)])

    seen: list[str] = []
    for offset in (0, 200, 400):
        page = db.find_moves(limit=200, offset=offset)
        seen.extend(m.src for m in page)

    assert [len(db.find_moves(limit=200, offset=o)) for o in (0, 200, 400)] == [200, 200, 50]
    assert len(seen) == 450
    assert len(set(seen)) == 450, "страницы не должны пересекаться"
    assert set(seen) == {f"C:/file_{i:03d}.pdf" for i in range(450)}, "пропусков быть не должно"


def test_find_moves_performance(tmp_path):
    db = _db(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(10_000):
        rows.append((
            uuid.uuid4().hex,
            (base + timedelta(seconds=i)).isoformat(),
            f"C:/files/doc_{i:05d}.pdf",
        ))
    db.conn.executemany(
        "INSERT INTO moves (id, ts, batch_id, rule_id, action, src, dst, sha256, size, status) "
        "VALUES (?, ?, NULL, 'r', 'move', ?, 'C:/D', NULL, NULL, 'done')",
        rows,
    )
    db.conn.commit()

    started = time.perf_counter()
    found = db.find_moves(name="doc_09999", limit=200)
    elapsed = time.perf_counter() - started

    print(f"\nfind_moves over 10k rows: {elapsed * 1000:.1f} ms")
    assert found, "поиск должен найти совпадение"
    assert elapsed < 0.2, f"поиск занял {elapsed:.3f} c — больше 0.2 c"


def test_journal_find_entries_delegates(tmp_path):
    journal = Journal(tmp_path / "journal.jsonl")
    now = datetime.now(timezone.utc)
    _insert(journal.db, "C:/Docs/смета.xlsx", now)
    journal.db.conn.commit()

    entries = journal.find_entries(name="смета", limit=200, offset=0)
    assert [e.src for e in entries] == ["C:/Docs/смета.xlsx"]
    assert entries[0].kind == "move"
