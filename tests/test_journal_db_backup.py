"""Резервная копия перед миграцией схемы и флаг deferred_json_migrated.

Перед пересозданием legacy-таблицы deferred (колонки path/action) база
копируется в journal.sqlite.pre-migration.bak. Флаг в meta защищает от
повторного импорта deferred.json, если переименование файла упало.
Все файлы создаются в tmp_path — %LOCALAPPDATA% не трогается.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.journal_db as journal_db_mod
from core.deferred_migration import migrate_deferred_json
from core.journal_db import JournalDB

LEGACY_SCHEMA = """
CREATE TABLE deferred (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT '',
    due_ts TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_ts TEXT NOT NULL DEFAULT ''
)
"""


def _create_legacy_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO deferred (path, action) VALUES ('C:/a.pdf', 'move')"
        )
        conn.commit()
    finally:
        conn.close()


def _columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(deferred)")}
    finally:
        conn.close()


def _backups(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.pre-migration.bak*"))


@pytest.fixture
def legacy_db(tmp_path) -> Path:
    db = tmp_path / "journal.sqlite"
    _create_legacy_db(db)
    return db


def _write_json(path: Path, src: str = "C:/x/a.pdf") -> None:
    due = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    path.write_text(
        json.dumps([{"src": src, "dst": "C:/Docs", "due_ts": due}]),
        encoding="utf-8",
    )


def test_backup_created_before_schema_migration(legacy_db):
    db = JournalDB(legacy_db)
    db.close()
    backups = _backups(legacy_db.parent)
    assert len(backups) == 1
    assert backups[0].name == "journal.sqlite.pre-migration.bak"
    # Копия содержит старую схему — из неё можно восстановить данные.
    assert "path" in _columns(backups[0])


def test_no_backup_on_fresh_db(tmp_path):
    db = JournalDB(tmp_path / "journal.sqlite")
    db.close()
    assert _backups(tmp_path) == []


def test_no_backup_when_schema_current(tmp_path):
    db_path = tmp_path / "journal.sqlite"
    JournalDB(db_path).close()
    JournalDB(db_path).close()  # второе открытие: схема уже новая
    assert _backups(tmp_path) == []


def test_backup_name_collision_keeps_old(legacy_db):
    existing = legacy_db.with_name("journal.sqlite.pre-migration.bak")
    existing.write_bytes(b"OLD-BACKUP")

    db = JournalDB(legacy_db)
    db.close()

    backups = _backups(legacy_db.parent)
    assert len(backups) == 2
    assert existing.read_bytes() == b"OLD-BACKUP", "старая копия не должна перезаписываться"
    stamped = [b for b in backups if b != existing]
    assert len(stamped) == 1
    # Суффикс — временная метка YYYYMMDDHHMMSS.
    stamp = stamped[0].name.removeprefix("journal.sqlite.pre-migration.bak.")
    datetime.strptime(stamp, "%Y%m%d%H%M%S")
    assert "path" in _columns(stamped[0])


def test_backup_failure_stops_migration(legacy_db, monkeypatch):
    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(journal_db_mod.shutil, "copy2", boom)

    with pytest.raises(RuntimeError, match="backup"):
        JournalDB(legacy_db)

    # Миграция не запускалась: схема старая, данные целы, копии нет.
    assert "path" in _columns(legacy_db)
    conn = sqlite3.connect(str(legacy_db))
    try:
        rows = conn.execute("SELECT path FROM deferred").fetchall()
    finally:
        conn.close()
    assert rows == [("C:/a.pdf",)]
    assert _backups(legacy_db.parent) == []


def test_migration_flag_blocks_rerun(tmp_path):
    db = JournalDB(tmp_path / "journal.sqlite")
    json_path = tmp_path / "deferred.json"
    _write_json(json_path)

    first = migrate_deferred_json(json_path, db)
    assert first.status == "migrated"
    assert not json_path.exists()  # переименован в .bak

    _write_json(json_path)  # тот же файл появился снова (например, откат rename)
    second = migrate_deferred_json(json_path, db)
    assert second.status == "already_done"
    assert second.imported == 0
    assert len(db.list_deferred()) == 1, "записи не должны дублироваться"
    assert json_path.exists(), "файл не трогается при already_done"
    db.close()


def test_flag_set_before_rename(tmp_path, monkeypatch):
    db = JournalDB(tmp_path / "journal.sqlite")
    json_path = tmp_path / "deferred.json"
    _write_json(json_path)

    def boom(self, target):
        raise OSError("rename blocked")

    monkeypatch.setattr(Path, "replace", boom)
    rep = migrate_deferred_json(json_path, db)

    assert rep.status == "migrated"
    assert "rename failed" in rep.reason
    assert db.get_meta("deferred_json_migrated") == "1"
    assert len(db.list_deferred()) == 1, "записи остались в БД"
    assert json_path.exists(), "файл остался на месте"

    monkeypatch.undo()  # Path.replace снова рабочий
    again = migrate_deferred_json(json_path, db)
    assert again.status == "already_done"
    assert len(db.list_deferred()) == 1, "повторный запуск не дублирует записи"
    db.close()


def test_set_meta_failure_rolls_back_inserts(tmp_path, monkeypatch):
    db = JournalDB(tmp_path / "journal.sqlite")
    json_path = tmp_path / "deferred.json"
    _write_json(json_path)

    def boom(self, key, value):
        raise RuntimeError("meta write failed")

    monkeypatch.setattr(JournalDB, "set_meta", boom)
    rep = migrate_deferred_json(json_path, db)

    assert rep.status == "error"
    assert "set_meta failed" in rep.reason
    assert db.list_deferred() == [], "вставки должны быть откачены"
    assert json_path.exists(), "файл остался на месте"
    db.close()
