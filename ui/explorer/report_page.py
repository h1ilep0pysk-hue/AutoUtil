from pathlib import Path

from platformdirs import user_data_dir
from PySide6.QtCore import QDate, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.i18n import t
from core import report
from core.journal import Journal

TEXT = QColor("#F2F2F2")
MUTED = QColor("#9B9B9B")
ROW_H = 40
HEAD_H = 36
NUM_W = 130
PCT_W = 110


def _arrow_path() -> str:
    """Generate a down‑arrow PNG the first time it is needed."""
    path = Path(user_data_dir("AutoUtil", appauthor=False)) / "arrow_down.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        img = QImage(12, 8, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(MUTED)
        p.drawPolygon(QPolygonF([QPointF(1, 1), QPointF(11, 1), QPointF(6, 7)]))
        p.end()
        img.save(str(path))
    return path.as_posix()


def _qss() -> str:
    return f"""
QDateEdit {{
    background: #272727; border: 1px solid #363636; border-radius: 6px;
    padding: 6px 34px 6px 10px; min-width: 120px; color: #F2F2F2;
}}
QDateEdit:focus {{ border: 1px solid #8AB4F8; }}
QDateEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 30px; border: none; border-left: 1px solid #363636;
    background: transparent;
}}
QDateEdit::down-arrow {{
    image: url({_arrow_path()}); width: 12px; height: 8px;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: #1F1F1F; }}
QCalendarWidget QToolButton {{
    color: #F2F2F2; background: transparent; padding: 4px 8px; border-radius: 6px;
}}
QCalendarWidget QToolButton:hover {{ background: #313131; }}
QCalendarWidget QAbstractItemView:enabled {{
    background: #1F1F1F; color: #F2F2F2;
    selection-background-color: #F2F2F2; selection-color: #000000;
}}
QFrame#Card {{ background: #272727; border-radius: 12px; }}
QLabel#CardValue {{ font-size: 18pt; font-weight: 600; color: #F2F2F2; }}
QLabel#CardLabel {{ font-size: 8pt; color: #9B9B9B; }}
QLabel#SectionTitle {{ font-size: 11pt; font-weight: 600; color: #F2F2F2; }}
QTableWidget {{
    background: #1F1F1F; border: 1px solid #363636; border-radius: 12px;
    gridline-color: transparent; outline: none;
}}
QHeaderView::section {{
    background: #1F1F1F; color: #9B9B9B; border: none;
    padding: 0px 12px; font-size: 8pt; border-bottom: 1px solid #363636;
}}
"""


def _card(value: str, label: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    v = QLabel(value)
    v.setObjectName("CardValue")
    l = QLabel(label)
    l.setObjectName("CardLabel")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(4)
    lay.addWidget(v)
    lay.addWidget(l)
    return frame


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionTitle")
    return lbl


def _cell(text: str, align: Qt.AlignmentFlag, color: QColor = TEXT) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    item.setForeground(color)
    return item


def _table(head: str, counter, empty_text: str | None = None) -> QTableWidget:
    empty_text = empty_text or t("Нет данных")
    rows = counter.most_common()
    total = sum(counter.values()) or 1
    table = QTableWidget(max(len(rows), 1), 3)
    table.setHorizontalHeaderLabels([head, t("Файлов"), t("Доля")])
    aligns = [Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight]
    for c, align in enumerate(aligns):
        hi = table.horizontalHeaderItem(c)
        hi.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    header = table.horizontalHeader()
    header.setFixedHeight(HEAD_H)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(1, NUM_W)
    table.setColumnWidth(2, PCT_W)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(ROW_H)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    if not rows:
        table.setItem(0, 0, _cell(empty_text, Qt.AlignmentFlag.AlignLeft, MUTED))
        table.setSpan(0, 0, 1, 3)
    for r, (name, count) in enumerate(rows):
        table.setItem(r, 0, _cell(str(name), Qt.AlignmentFlag.AlignLeft))
        table.setItem(r, 1, _cell(str(count), Qt.AlignmentFlag.AlignRight))
        pct = f"{count * 100 / total:.0f}%"
        table.setItem(r, 2, _cell(pct, Qt.AlignmentFlag.AlignRight, MUTED))
    table.setFixedHeight(HEAD_H + ROW_H * max(len(rows), 1) + 4)
    return table


class ReportPage(QWidget):
    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.setStyleSheet(_qss())
        self.journal = journal
        self._md = ""

        title = QLabel(t("Отчёт"))
        title.setProperty("role", "title")
        sub = QLabel(t("Что программа перенесла, куда и по каким правилам за выбранный период."))
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.start = self._date_box(QDate.currentDate().addDays(-7))
        self.end = self._date_box(QDate.currentDate())

        build_btn = QPushButton(t("Сформировать"))
        build_btn.setObjectName("Primary")
        build_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        build_btn.clicked.connect(self.reload)
        export_btn = QPushButton(t("Экспорт .md"))
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._export)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(QLabel(t("С")))
        bar.addWidget(self.start)
        bar.addWidget(QLabel(t("по")))
        bar.addWidget(self.end)
        bar.addSpacing(8)
        bar.addWidget(build_btn)
        bar.addWidget(export_btn)
        bar.addStretch()

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.content)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        root.addWidget(title)
        root.addWidget(sub)
        root.addLayout(bar)
        root.addWidget(scroll, 1)
        self.reload()

    @staticmethod
    def _date_box(d: QDate) -> QDateEdit:
        box = QDateEdit(d)
        box.setCalendarPopup(True)
        box.setDisplayFormat("dd.MM.yyyy")
        box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        return box

    def _clear(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _message(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setProperty("role", "muted")
        lbl.setWordWrap(True)
        self.content_layout.addWidget(lbl)
        self.content_layout.addStretch()

    def reload(self) -> None:
        s = self.start.date().toPython()
        e = self.end.date().toPython()
        self._clear()
        if s > e:
            self._md = ""
            self._message(t("Начало периода позже конца. Поменяй даты."))
            return
        data = report.build(self.journal.read_all(), s, e)
        self._md = report.to_markdown(data, s, e)
        self._render(data, s, e)

    def _render(self, r: dict, start, end) -> None:
        header = QLabel(t("Период: {start:%d.%m.%Y} — {end:%d.%m.%Y}", start=start, end=end))
        header.setProperty("role", "muted")
        self.content_layout.addWidget(header)
        if r["moved"] == 0 and r["undone"] == 0 and r["binned"] == 0:
            self._message(t("За период ничего не перенесено. Выбери другой период или проверь, что схема запущена."))
            return
        cards = QHBoxLayout()
        cards.setSpacing(12)
        for value, label in [
            (str(r["moved"]), t("перенесено файлов")),
            (str(r["binned"]), t("Убрано правилом в корзину")),
            (t("{size:.1f} МБ", size=r["size_mb"]), t("общий размер")),
            (str(r["undone"]), t("возвращено откатом")),
            (str(r["trashed"]), t("убрано в корзину")),
        ]:
            cards.addWidget(_card(value, label), 1)
        cards_wrap = QWidget()
        cards_wrap.setLayout(cards)
        self.content_layout.addWidget(cards_wrap)
        for title, counter, head in [
            (t("По правилам"), r["by_rule"], t("Правило")),
            (t("По папкам назначения"), r["by_folder"], t("Папка")),
            (t("По типам файлов"), r["by_ext"], t("Расширение")),
        ]:
            self.content_layout.addWidget(_section_title(title))
            self.content_layout.addWidget(_table(head, counter))
        self.content_layout.addStretch()

    def _export(self) -> None:
        if not self._md:
            return
        path, _ = QFileDialog.getSaveFileName(self, t("Экспорт отчёта"), "autoutil-report.md",
                                              "Markdown (*.md)")
        if not path:
            return
        if not path.lower().endswith('.md'):
            path += '.md'
        Path(path).write_text(self._md, encoding='utf-8')
