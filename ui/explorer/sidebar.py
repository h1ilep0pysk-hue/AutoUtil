from core.i18n import t
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

def _sections():
    return [
        (t("Схема"), "schema"),
        (t("Спросить"), "pending"),
        (t("Журнал"), "journal"),
        (t("Отчёт"), "report"),
        (t("Правила"), "rules"),
        (t("Настройки"), "settings"),
    ]


class Sidebar(QListWidget):
    section_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(200)
        for title, key in _sections():
            item = QListWidgetItem(title)
            item.setData(0x0100, key)
            self.addItem(item)
        self.currentRowChanged.connect(self._on_row)

    def select(self, key: str) -> None:
        for row in range(self.count()):
            if self.item(row).data(0x0100) == key:
                self.setCurrentRow(row)
                return

    def _on_row(self, row: int) -> None:
        if row >= 0:
            self.section_selected.emit(self.item(row).data(0x0100))
