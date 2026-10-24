from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from core.journal import Journal


class JournalView(QDialog):
    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.setWindowTitle("AutoUtil: журнал действий")
        self.resize(640, 420)
        self.journal = journal

        self.list = QListWidget()
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.reload)
        self.undo_btn = QPushButton("Вернуть выбранное")
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
            mark = "[возвращён] " if entry.undone else ""
            text = f"{mark}{entry.timestamp[:19]}  {entry.dst}"
            item = QListWidgetItem(text)
            item.setData(0x0100, entry.id)
            self.list.addItem(item)

    def undo_selected(self) -> None:
        item = self.list.currentItem()
        if item is None:
            self.status.setText("Выберите запись.")
            return
        entry_id = item.data(0x0100)
        ok = self.journal.undo(entry_id)
        self.status.setText("Файл возвращён на место." if ok
                            else "Вернуть не удалось: файл уже перемещён или удалён.")
        self.reload()
