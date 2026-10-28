"""Миграция legacy-схемы таблицы deferred (path/action -> src/rule).

Старая таблица содержит колонки ``path TEXT NOT NULL`` и ``action``, которых
нет в текущей схеме. INSERT в текущем коде не заполняет ``path`` и падал с
IntegrityError. Миграция пересоздаёт таблицу на месте, перенося ``path`` в
``src``. Все фикстуры создаются в tmp_path — %LOCALAPPDATA% не трогается.
"""
import sqlite3
from pathlib import Path

import pytest

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


def _create_legacy_db(db_path: Path, rows: list[tuple]) -> None:
    """Создать БД со старой схемой deferred и заданными строками."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(LEGACY_SCHEMA)
        conn.executemany(
            "INSERT INTO deferred (path, action, due_ts, status, created_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _column_names(db_path: Path, table: str = "deferred") -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


@pytest.fixture
def legacy_db(tmp_path) -> Path:
    db = tmp_path / "journal.sqlite"
    _create_legacy_db(db, [("C:/a.pdf", "move", "2026-01-01T00:00:00+00:00",
                            "pending", "2025-12-01T00:00:00+00:00")])
    return db


def test_legacy_schema_add_deferred_works(legacy_db):
    """INSERT в мигрированную БД не падает с IntegrityError."""
    store = JournalDB(legacy_db)
    row_id = store.add_deferred("C:/b.pdf", "C:/Docs", "Правило", days=30)
    assert row_id > 0
    assert "path" not in _column_names(legacy_db)


def test_legacy_rows_preserved(legacy_db):
    """Строка с path='C:/a.pdf' после миграции читается как src='C:/a.pdf'."""
    store = JournalDB(legacy_db)
    items = store.list_deferred()
    assert len(items) == 1
    assert items[0]["src"] == "C:/a.pdf"
    assert items[0]["status"] == "pending"


def test_migration_idempotent(legacy_db):
    """Повторное открытие не пересоздаёт таблицу и не дублирует данные."""
    first = JournalDB(legacy_db)
    first.add_deferred("C:/b.pdf", "C:/Docs", "Правило", days=30)
    first.close()

    second = JournalDB(legacy_db)  # повторный запуск миграции — no-op
    items = second.list_deferred()
    assert len(items) == 2
    assert {i["src"] for i in items} == {"C:/a.pdf", "C:/b.pdf"}
    assert "path" not in _column_names(legacy_db)
    assert "action" not in _column_names(legacy_db)


def test_migration_rollback_on_error(legacy_db, monkeypatch):
    """Падение копирования откатывает транзакцию: схема и данные на месте."""

    def boom(self, cur, old_cols):
        raise RuntimeError("copy failed")

    monkeypatch.setattr(JournalDB, "_copy_deferred_rows", boom)
    with pytest.raises(RuntimeError, match="copy failed"):
        JournalDB(legacy_db)

    # Таблица осталась в исходном виде: legacy-колонки и строка не потеряны.
    assert {"path", "action"} <= _column_names(legacy_db)
    conn = sqlite3.connect(str(legacy_db))
    try:
        rows = conn.execute("SELECT path, action FROM deferred").fetchall()
        assert rows == [("C:/a.pdf", "move")]
        # deferred_new не должна утечь из откаченной транзакции.
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "deferred_new" not in names
    finally:
        conn.close()


def test_fresh_db_has_no_legacy_columns(tmp_path):
    """На пустой базе ни path, ни action в deferred не появляются."""
    store = JournalDB(tmp_path / "journal.sqlite")
    cols = {row["name"] for row in store.conn.execute("PRAGMA table_info(deferred)")}
    assert "path" not in cols
    assert "action" not in cols
    assert "src" in cols
