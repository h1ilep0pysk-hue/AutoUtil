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


def test_undo_is_append_only(tmp_path):
    """Откат не переписывает файл журнала, а дописывает запись kind=undo."""
    j = make_journal(tmp_path)
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    entry = j.record_move(src_dir / "f.txt", dst_dir / "f.txt", "r")
    (dst_dir / "f.txt").write_text("x", encoding="utf-8")
    before = j.path.read_text(encoding="utf-8").splitlines()
    assert j.undo(entry.id) is True
    after = j.path.read_text(encoding="utf-8").splitlines()
    # исходная строка не изменилась, добавилась ровно одна запись
    assert before[0] == after[0]
    assert len(after) == len(before) + 1
    undo_entry = json.loads(after[-1])
    assert undo_entry["kind"] == "undo" and undo_entry["dst"] == entry.id
    # read_all склеивает: undo-записи скрыты, исходная помечена возвращённой
    entries = j.read_all()
    assert len(entries) == 1 and entries[0].undone is True
    assert all(e.kind != "undo" for e in entries)


# --- ротация -------------------------------------------------------------

def test_rotation_and_prune(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_mod, "MAX_JOURNAL_BYTES", 200)
    monkeypatch.setattr(journal_mod, "KEEP_ROTATIONS", 2)
    j = make_journal(tmp_path)
    for i in range(120):
        j.record_move(tmp_path / f"f{i}.txt", tmp_path / "out" / f"f{i}.txt", "правило")
    rotated = list(tmp_path.glob("journal-*.jsonl"))
    assert rotated, "ротация не сработала"
    assert len(rotated) <= journal_mod.KEEP_ROTATIONS  # старые копии удаляются
    assert j.path.exists()
    # журнал продолжает работать после ротаций
    j.record_bin(tmp_path / "x.log", "Корзина")
    assert j.read_all()[-1].kind == "bin"


def test_corrupt_line_tolerated(tmp_path):
    j = make_journal(tmp_path)
    entry = j.record_move(tmp_path / "a", tmp_path / "b", "r")
    with j.path.open("a", encoding="utf-8") as f:
        f.write("{битая json строка\n")
    entries = j.read_all()
    assert len(entries) == 1
    assert entries[0].id == entry.id


def test_extra_fields_dropped(tmp_path):
    j = make_journal(tmp_path)
    raw = {"id": "x1", "timestamp": "t", "kind": "move", "src": "s", "dst": "d",
           "rule": "r", "чужоеполе": 1}
    with j.path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(raw, ensure_ascii=False) + "\n")
    entries = j.read_all()
    assert entries and entries[0].id == "x1"
