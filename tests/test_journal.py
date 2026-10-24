from pathlib import Path
from core.journal import Journal


def test_move_and_undo(tmp_path: Path):
    j = Journal(tmp_path / "journal.jsonl")
    src = tmp_path / "a.txt"
    dst = tmp_path / "sub" / "a.txt"
    src.write_text("hi")

    dst.parent.mkdir()
    entry = j.record_move(src, dst, rule="test")
    src.rename(dst)

    assert j.undo(entry.id)
    assert src.exists() and not dst.exists()