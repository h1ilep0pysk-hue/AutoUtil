"""Карантин дубликатов: порядок журнал → проверка keep → перемещение → done."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core import config
from core.journal_db import JournalDB
from modules.organizer.dedupe_groups import group_duplicates
from modules.organizer.quarantine import (
    move_to_quarantine, purge_quarantine, quarantine_dir, quarantine_target,
)
from modules.organizer.rules import Rule

CONTENT = b"duplicate payload"


def _rule() -> Rule:
    return Rule(name="Дубликаты", exts=[".txt"], name_globs=["dup*"], dedupe=True)


def _make(folder: Path, name: str, content: bytes = CONTENT, mtime: float = 1_000_000) -> Path:
    p = folder / name
    p.write_bytes(content)
    os.utime(p, (mtime, mtime))
    return p


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    db = JournalDB(tmp_path / "journal.sqlite")
    for name, mtime in (("dupa.txt", 1_000_000), ("dupb.txt", 2_000_000), ("dupc.txt", 3_000_000)):
        _make(src, name, mtime=mtime)
    group = group_duplicates(src, _rule())[0]
    return {"src": src, "db": db, "group": group}


def test_pending_written_before_move(env, monkeypatch):
    db: JournalDB = env["db"]
    group = env["group"]
    seen: list[list[str]] = []
    real_replace = Path.replace

    def spy(self, target):
        statuses = [r["status"] for r in db.conn.execute("SELECT status FROM moves")]
        seen.append(statuses)
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    move_to_quarantine(group, db, "Дубликаты")

    assert seen, "Path.replace не вызывался"
    assert all(s == ["pending"] for s in seen[:1]), f"статусы в момент перемещения: {seen}"
    assert len(seen) == 2


def test_failed_keep_check_moves_nothing(env):
    db: JournalDB = env["db"]
    group = env["group"]
    before = {p.name for p in env["src"].iterdir()}

    # keep изменился между планированием и перемещением
    group.keep.write_bytes(b"changed payload!!")

    moved = move_to_quarantine(group, db, "Дубликаты")

    assert moved == []
    assert {p.name for p in env["src"].iterdir()} == before, "файлы должны остаться на месте"
    statuses = [r["status"] for r in db.conn.execute("SELECT status FROM moves")]
    assert statuses == ["failed"]


def test_collision_suffix(env):
    base = quarantine_dir()
    base.mkdir(parents=True, exist_ok=True)
    existing = base / "dupa.txt"
    existing.write_bytes(b"old quarantine file")

    target = quarantine_target(env["group"].remove[0], base)
    assert target.name == "dupa_1.txt"
    assert existing.read_bytes() == b"old quarantine file"

    move_to_quarantine(env["group"], env["db"], "Дубликаты")
    assert existing.read_bytes() == b"old quarantine file", "старый файл не перезаписан"
    assert (base / "dupa_1.txt").exists()


def test_journal_failure_blocks_move(env, monkeypatch):
    db: JournalDB = env["db"]
    group = env["group"]

    def boom(self, **kwargs):
        raise RuntimeError("journal down")

    monkeypatch.setattr(JournalDB, "add_move", boom)
    moved = move_to_quarantine(group, db, "Дубликаты")

    assert moved == []
    for path in group.remove:
        assert path.exists(), f"{path.name} не должен трогаться без записи в журнал"


def test_done_after_success(env):
    db: JournalDB = env["db"]
    moved = move_to_quarantine(env["group"], db, "Дубликаты")

    assert len(moved) == 2
    statuses = [r["status"] for r in db.conn.execute("SELECT status FROM moves")]
    assert statuses == ["done", "done"]
    assert all(p.exists() for p in moved)
    assert env["group"].keep.exists()


def test_purge_by_date_folder():
    root = config.APP_DIR / "quarantine"
    old = root / "2020-01-01"
    fresh = root / "2026-10-28"
    for folder in (old, fresh):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "x.txt").write_bytes(b"x")

    removed = purge_quarantine(30, now=datetime(2026, 10, 28, tzinfo=timezone.utc))

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
