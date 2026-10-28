"""Smoke-тест окна предпросмотра дубликатов (offscreen)."""
import csv
import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

from modules.organizer.dedupe_groups import group_duplicates  # noqa: E402
from modules.organizer.rules import Rule  # noqa: E402

CONTENT = b"same bytes"


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _groups(tmp_path: Path):
    for name, mtime in (("dupa.txt", 1_000_000), ("dupb.txt", 2_000_000)):
        p = tmp_path / name
        p.write_bytes(CONTENT)
        os.utime(p, (mtime, mtime))
    rule = Rule(name="Дубликаты", exts=[".txt"], name_globs=["dup*"], dedupe=True)
    return group_duplicates(tmp_path, rule)


def test_dialog_run_button_requires_checkbox(tmp_path):
    from ui.explorer.duplicates_preview import DuplicatesPreviewDialog

    app = _app()
    dialog = DuplicatesPreviewDialog(_groups(tmp_path), "Дубликаты")
    assert dialog.run_btn.isEnabled() is False

    dialog.confirm.setChecked(True)
    assert dialog.run_btn.isEnabled() is True

    dialog.confirm.setChecked(False)
    assert dialog.run_btn.isEnabled() is False
    app.processEvents()
    dialog.deleteLater()


def test_dialog_tree_shows_group(tmp_path):
    from ui.explorer.duplicates_preview import DuplicatesPreviewDialog

    app = _app()
    groups = _groups(tmp_path)
    dialog = DuplicatesPreviewDialog(groups, "Дубликаты")
    assert dialog.tree.topLevelItemCount() == 1
    top = dialog.tree.topLevelItem(0)
    assert top.childCount() == 2  # keep + один remove
    app.processEvents()
    dialog.deleteLater()


def test_csv_export_columns(tmp_path, monkeypatch):
    from ui.explorer import duplicates_preview as mod

    app = _app()
    dialog = mod.DuplicatesPreviewDialog(_groups(tmp_path), "Дубликаты")
    out = tmp_path / "dups.csv"
    monkeypatch.setattr(
        mod.QFileDialog, "getSaveFileName", lambda *a, **kw: (str(out), "CSV (*.csv)")
    )

    dialog._export_csv()

    assert out.exists()
    with open(out, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["group_digest", "file", "action", "size", "mtime"]
    assert len(rows) == 3  # заголовок + keep + remove
    actions = {row[2] for row in rows[1:]}
    assert actions == {"keep", "quarantine"}
    app.processEvents()
    dialog.deleteLater()
