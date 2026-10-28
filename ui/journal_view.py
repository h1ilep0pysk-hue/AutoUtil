from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)
from pathlib import Path

from core.i18n import t
from core.journal import Journal


class JournalView(QDialog):
    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.setWindowTitle(t("journal.title"))
        self.resize(640, 420)
        self.journal = journal

        self.list = QListWidget()
        self.refresh_btn = QPushButton(t("journal.refresh"))
        self.refresh_btn.clicked.connect(self.reload)
        self.undo_btn = QPushButton(t("journal.undo"))
        self.undo_btn.clicked.connect(self.undo_selected)

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_btn)
        buttons.addWidget(self.undo_btn)

        self.status = QLabel("")
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for entry in reversed(self.journal.read_all()):
            mark = t("journal.returned") if entry.undone else ""
            if entry.kind == "bin":
                text = f"{mark}{entry.timestamp[:19]}  {t('journal.bin_row', name=Path(entry.src).name)}"
            else:
                text = f"{mark}{entry.timestamp[:19]}  {entry.dst}"
            item = QListWidgetItem(text)
            item.setData(0x0100, entry.id)
            self.list.addItem(item)

    def undo_selected(self) -> None:
        item = self.list.currentItem()
        if item is None:
            self.status.setText(t("journal.select"))
            return
        entry_id = item.data(0x0100)
        entry = next((e for e in self.journal.read_all() if e.id == entry_id), None)
        if entry is not None and entry.kind == "bin":
            self.status.setText(t("journal.bin_undone"))
            return
        ok = self.journal.undo(entry_id)
        self.status.setText(t("journal.undo_ok") if ok else t("journal.undo_fail"))
        self.reload()
