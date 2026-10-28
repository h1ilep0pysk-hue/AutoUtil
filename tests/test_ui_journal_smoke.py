"""Smoke-тест страницы «Журнал» в offscreen-режиме (без реального дисплея)."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.journal import Journal  # noqa: E402
from core.prefs import UiPrefs  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_journal_page_constructs(tmp_path):
    from ui.explorer.pages import JournalPage

    app = _app()
    page = JournalPage(Journal(tmp_path / "journal.jsonl"), UiPrefs())
    assert page.model.rowCount() == 0
    assert page.next_btn.isEnabled() is False
    app.processEvents()
    page.deleteLater()


def test_journal_page_search_does_not_crash(tmp_path):
    from ui.explorer.pages import JournalPage

    app = _app()
    journal = Journal(tmp_path / "journal.jsonl")
    journal.record_move(tmp_path / "a.pdf", tmp_path / "out" / "a.pdf", "Правило")

    page = JournalPage(journal, UiPrefs())
    page.search.setText("a.pdf")
    page._apply_filters()  # то, что делает таймер через 300 мс
    app.processEvents()
    assert page.model.rowCount() == 1

    page.search.setText("нет-такого")
    page._apply_filters()
    app.processEvents()
    assert page.model.rowCount() == 0
    page.deleteLater()
