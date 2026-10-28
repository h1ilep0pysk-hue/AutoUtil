import json

from core import journal as journal_mod
from core.journal import Journal


def make_journal(tmp_path):
    return Journal(path=tmp_path / "journal.jsonl")


def test_record_and_read(tmp_path):
    j = make_journal(tmp_path)
    j.record_move(tmp_path / "a.txt", tmp_path / "b" / "a.txt", "правило1")
    j.record_bin(tmp_path / "c.log", "Корзина: тест")
    entries = j.read_all()
    assert len(entries) == 2
    assert entries[0].kind == "move"
    assert entries[1].kind == "bin" and entries[1].dst == ""


def test_undo_move(tmp_path):
    j = make_journal(tmp_path)
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    src = src_dir / "f.txt"
    entry = j.record_move(src, dst_dir / "f.txt", "правило1")
    (dst_dir / "f.txt").write_text("moved", encoding="utf-8")
    assert j.undo(entry.id) is True
    assert (src_dir / "f.txt").read_text(encoding="utf-8") == "moved"
    assert not (dst_dir / "f.txt").exists()
    assert j.read_all()[0].undone is True


def test_undo_second_time_fails(tmp_path):
    j = make_journal(tmp_path)
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    entry = j.record_move(src_dir / "f.txt", dst_dir / "f.txt", "r")
    (dst_dir / "f.txt").write_text("x", encoding="utf-8")
    assert j.undo(entry.id) is True
    assert j.undo(entry.id) is False  # уже откатано


def test_undo_blocked_src_renamed_beside_not_deleted(tmp_path, monkeypatch):
    """Мешающий файл на месте src: переименовывается рядом, не в корзину."""
    j = make_journal(tmp_path)
    src = tmp_path / "f.txt"
    src.write_text("blocker", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    entry = j.record_move(src, out / "f.txt", "r")
    (out / "f.txt").write_text("moved-back", encoding="utf-8")
    # подменяем set_aside, чтобы не отправлять файл в настоящую корзину при тесте
    monkeypatch.setattr(journal_mod, "set_aside", lambda p: str(p))
    assert j.undo(entry.id) is True
    entries = j.read_all()
    assert entries[0].undone is True and entries[0].trashed
    assert not (out / "f.txt").exists()
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "moved-back"
    aside = [p for p in tmp_path.iterdir() if p.is_file() and p.name.startswith("f (")]
    assert aside and aside[0].read_text(encoding="utf-8") == "blocker"


def test_undo_bin_entry_returns_false(tmp_path):
    j = make_journal(tmp_path)
    entry = j.record_bin(tmp_path / "x.log", "Корзина: тест")
    assert j.undo(entry.id) is False







def test_migration_with_corrupt_line(tmp_path):
    # Prepare legacy JSONL with a corrupt line
    legacy_path = tmp_path / "journal.jsonl"
    # good entry
    good = json.dumps({"id": "id1", "timestamp": "2023-01-01T00:00:00Z", "kind": "move", "src": "a", "dst": "b", "rule": "r", "undone": False}, ensure_ascii=False)
    # bad entry
    bad = "{bad json"
    # another good entry
    good2 = json.dumps({"id": "id2", "timestamp": "2023-01-02T00:00:00Z", "kind": "bin", "src": "c", "dst": "", "rule": "r", "undone": False}, ensure_ascii=False)
    legacy_path.write_text("\n".join([good, bad, good2]), encoding="utf-8")
    # Instantiate Journal which should migrate
    j = Journal(path=legacy_path)
    entries = j.read_all()
    # Should have only the two good entries
    assert len(entries) == 2
    ids = {e.id for e in entries}
    assert {"id1", "id2"} == ids
    # Legacy file should be renamed to .bak
    assert not legacy_path.exists()
    assert legacy_path.with_name("journal.jsonl.bak").exists()



def test_migration_extra_fields(tmp_path):
    # Legacy JSONL with extra unknown field
    legacy_path = tmp_path / "journal.jsonl"
    raw = {"id": "x1", "timestamp": "t", "kind": "move", "src": "s", "dst": "d", "rule": "r", "чужоеполе": 1}
    legacy_path.write_text(json.dumps(raw, ensure_ascii=False) + "\n", encoding="utf-8")
    j = Journal(path=legacy_path)
    entries = j.read_all()
    assert entries and entries[0].id == "x1"
    # Ensure extra field is ignored and not cause failure
    # Legacy file should be renamed
    assert not legacy_path.exists()
    assert legacy_path.with_name("journal.jsonl.bak").exists()
