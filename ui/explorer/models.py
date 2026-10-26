from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from core.i18n import t
from core.journal import JournalEntry
from pathlib import Path
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
            mark = t("[возвращён] ") if e.undone else ""
            if e.kind == "bin":
                return f"{mark}{e.timestamp[:19]}   {t('убрано в корзину')}: {Path(e.src).name}"
            return f"{mark}{e.timestamp[:19]}   {e.dst}"
        if role == Qt.ItemDataRole.ToolTipRole:
            dst = t("Корзина") if e.kind == "bin" else e.dst
            return t("Откуда: {src}\nКуда: {dst}\nПравило: {rule}", src=e.src, dst=dst, rule=e.rule)
        return None


class RuleModel(_BaseModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r: Rule = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            dst = t("Корзина") if r.to_bin else r.target
            if r.delay_days:
                dst += f" ({t('через {n} дн.', n=r.delay_days)})"
            return f"{r.name}   →   {dst}"
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
