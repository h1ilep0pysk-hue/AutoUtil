from pathlib import Path

from core.journal import Journal
from modules.organizer.actions import apply_move, prepare_target


def test_prepare_target_avoids_overwrite(tmp_path: Path):
    existing = tmp_path / "a.pdf"
    existing.write_text("1")
    target = prepare_target(existing)
    assert target.name == "a (1).pdf"


def test_move_then_undo(tmp_path: Path):
    src = tmp_path / "check.pdf"
    src.write_text("итого 100")
    dst = prepare_target(tmp_path / "Чеки" / "check.pdf")
    j = Journal(tmp_path / "journal.jsonl")
    entry = j.record_move(src, dst, rule="Чеки")
    apply_move(src, dst)
    assert dst.exists() and not src.exists()
    assert j.undo(entry.id)
    assert src.exists() and not dst.exists()
