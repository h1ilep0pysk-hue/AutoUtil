from PySide6.QtCore import QMimeData, Qt, Signal

from core.i18n import t
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

MIME = "application/x-autoutil-node"
USER = int(Qt.ItemDataRole.UserRole)
KEYS = USER + 1

def _node_info():
    return [
        (
            "source", t("Папка"),
            t("Откуда берутся файлы. Укажи полный путь в поле «Папка», например "
            "C:\\Users\\you\\Downloads. От папки тяни линию к фильтру, исключению или цели. "
            "Без связи с целью папка ничего не делает."),
            t("папка источник загрузки путь"),
        ),
        (
            "filter", t("Фильтр"),
            t("Отбирает файлы по условиям: расширения, ключевые слова, маска имени (invoice_*.pdf), регулярное выражение, размер в МБ, возраст в днях, GPS. Все заполненные условия должны выполняться. Линия «Связать «нет»» ведёт к файлам, которые не прошли фильтр."),
            t("фильтр условие расширение размер дата маска регулярка"),
        ),
        (
            "ask", t("Спросить"),
            t("Файл не переносится сам. Он попадает в раздел «Спросить», где ты нажимаешь «Перенести» или «Пропустить». Удобно, когда не уверен, что файл нужно убирать именно туда."),
            t("спросить вопрос подтверждение решение"),
        ),
        (
            "exclude", t("Исключить"),
            t("Файлы, подходящие под маски, не трогаются. Маски через запятую: *.tmp, node_modules. Ставь между папкой и целью, тогда исключение действует на все пути через этот узел."),
            t("исключить маска игнор пропустить tmp"),
        ),
        (
            "delay", t("Через N дней"),
            t("Через N дней: откладывает действие на N дней с момента изменения файла. Когда срок пройдёт, файл будет перенесён в цель или убран в корзину. Ставь узел после фильтра и перед целью или корзиной. Отложенное видно в разделе «Спросить»."),
            t("дней отложить задержка срок повременить позже postpone delay schedule days later"),
        ),
        (
            "dedupe", t("Дубликаты"),
            t("Дубликаты: убирает копии файлов, у которых рядом лежит точный дубль — "
            "тот же размер и то же содержимое (SHA-256). Укажи маску имени "
            "(например robloxinstaller*) и расширения (например exe), тогда копии "
            "ищутся только по маске. Можно оставить поля пустыми — узел найдёт "
            "дубликаты сам: плюс-минус похожее имя («(1)», «копия», «download»), "
            "тот же размер и тот же хеш. Из набора копий остаётся ровно одна; "
            "убранное лежит в корзине, и его можно вернуть."),
            "дубликат копия одинаковые повтор дубль очистить duplicate dup same twin",
        ),
        (
            "bin", t("В корзину"),
            t("В корзину: файл отправляется в корзину Windows. Его можно вернуть оттуда вручную в любой момент. Ставь узел последним — после папки, фильтра или исключения."),
            t("корзина удалить выброшенное мусор очистить bin trash delete recycle"),
        ),
        (
            "target", t("Цель"),
            t("Куда кладётся файл. Путь относительно домашней папки пользователя. Можно использовать {year}, например Документы/Чеки/{year}. Цель никуда не ведёт, это конец пути."),
            t("цель назначение папка перенос куда"),
        ),
    ]


class _PaletteList(QListWidget):
    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(MIME, item.data(USER).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class NodePalette(QWidget):
    node_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(300)

        heading = QLabel(t("Функции"))
        heading.setObjectName("Heading")

        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Поиск функции"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.list = _PaletteList()
        self.list.setDragEnabled(True)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.itemClicked.connect(self._clicked)

        for kind, title, info, keys in _node_info():
            item = QListWidgetItem(title)
            item.setData(USER, kind)
            item.setData(KEYS, keys)
            item.setToolTip(
                f"{title}\n\n{info}\n\n" + t("Клик добавляет узел в центр холста. Перетащи на холст, чтобы поставить в нужное место.")
            )
            self.list.addItem(item)

        hint = QLabel(
            t("Ветка «нет» настраивается кнопкой «Связать «нет»» в шапке. Она работает только от фильтра.")
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(heading)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addWidget(hint)

    def _clicked(self, item: QListWidgetItem) -> None:
        self.node_clicked.emit(item.data(USER))

    def _filter(self, text: str) -> None:
        q = text.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            hay = f"{it.text()} {it.data(KEYS)}".lower()
            it.setHidden(bool(q) and q not in hay)
