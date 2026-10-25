from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from core.journal import JournalEntry
from modules.organizer.rules import Rule


class _BaseModel(QAbstractListModel):
    def __init__(self, items: list | None = None) -> None:
        super().__init__()
        self._items = list(items or [])

    def set_items(self, items: list) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def item(self, row: int):
        return self._items[row]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)


class JournalModel(_BaseModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        e: JournalEntry = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            mark = "[возвращён] " if e.undone else ""
            return f"{mark}{e.timestamp[:19]}   {e.dst}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"Откуда: {e.src}\nКуда: {e.dst}\nПравило: {e.rule}"
        return None


class RuleModel(_BaseModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r: Rule = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{r.name}   →   {r.target}"
        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if r.enabled else Qt.CheckState.Unchecked
        return None

    def flags(self, index):
        return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role == Qt.ItemDataRole.CheckStateRole and index.isValid():
            self._items[index.row()].enabled = (
                value == Qt.CheckState.Checked or value == Qt.CheckState.Checked.value
            )
            self.dataChanged.emit(index, index)
            return True
        return False
