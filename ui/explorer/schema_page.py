from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsItem, QGraphicsPathItem,
    QGraphicsScene, QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.i18n import t
from core.schema import (
    ALLOWED_LINKS, KIND_TITLES, MAX_RULES, NO_BRANCH_FROM,
    Edge, Node, Schema, load_schema, save_schema,
)
from modules.organizer.rules import Rule
from modules.organizer.rules_store import save_rules
from ui.explorer.node_palette import MIME, NodePalette

NODE_W, NODE_H = 180, 72
GRID = 24
NODE_COLORS = {
    "source": "#242424",
    "filter": "#242424",
    "ask": "#242424",
    "exclude": "#242424",
    "target": "#242424",
}

NODE_ACCENT = {
    "source": "#5B8FC7",
    "filter": "#9B7FD1",
    "ask": "#D9A441",
    "exclude": "#E06C75",
    "target": "#5FB38A",
}
def _new_titles():
    return {
        "source": t("Новая папка"),
        "filter": t("Новый фильтр"),
        "ask": t("Спросить"),
        "exclude": t("Исключить"),
        "target": t("Новая цель"),
    }
def _help():
    return {
        "source": t(
            "Папка: откуда берутся файлы. Укажи полный путь в поле «Папка», например "
            "C:\\Users\\you\\Downloads. От папки тяни линию к фильтру, исключению или цели."
        ),
        "filter": (
            t("Фильтр: отбирает файлы. Все заполненные условия должны выполняться. Расширения, ключевые слова, маска имени вида invoice_*.pdf, регулярное выражение, размер в МБ, возраст в днях. Линия «Связать «нет»» ведёт в ветку для файлов, которые не прошли.")
        ),
        "ask": (
            t("Спросить: файл не переносится сам. Он попадает в раздел «Спросить», где ты решаешь: перенести или пропустить. Обычно ставится после фильтра и перед целью.")
        ),
        "exclude": (
            t("Исключить: файлы, подходящие под маски, не трогаются. Маски через запятую, например *.tmp, node_modules. Действует на все пути, которые идут через этот узел.")
        ),
        "target": (
            t("Цель: куда кладётся файл. Путь относительно домашней папки пользователя. Можно использовать {year}, например Документы/Чеки/{year}. Имя файла: шаблон вида {date}_{name}.{ext}, пусто значит оставить имя. Цель никуда не ведёт.")
        ),
    }
def _general_help():
    return (
        t("Как это работает: папка, затем фильтры, исключения или вопрос, затем цель. Каждый путь от папки до цели становится правилом. Линия «нет» из фильтра включается, когда файл не прошёл условия этого фильтра.")
    )
def _footer_help():
    return (
        t("«Запустить схему» сохраняет правила, берёт папки из узлов «Папка» и начинает наблюдение. «Только правила» обновляет правила без запуска. Перенос идёт через журнал, любой файл можно вернуть.")
    )
FIELDS = {
    "source": ["title", "folder"],
    "filter": ["title", "exts", "keywords", "name_glob", "name_regex",
               "min_mb", "max_mb", "min_age_days", "max_age_days", "gps"],
    "ask": ["title"],
    "exclude": ["title", "masks"],
    "target": ["title", "folder", "rename"],
}
def _labels():
    return [
        ("title", t("Название:")),
        ("folder", t("Папка:")),
        ("rename", t("Имя файла:")),
        ("masks", t("Что исключить:")),
        ("exts", t("Расширения:")),
        ("keywords", t("Ключевые слова:")),
        ("name_glob", t("Маска имени:")),
        ("name_regex", t("Регулярное выражение:")),
        ("min_mb", t("Больше, МБ:")),
        ("max_mb", t("Меньше, МБ:")),
        ("min_age_days", t("Старше, дней:")),
        ("max_age_days", t("Новее, дней:")),
        ("gps", ""),
    ]


def shape_path(kind: str) -> QPainterPath:
    w, h = NODE_W, NODE_H
    p = QPainterPath()
    if kind == "source":
        p.moveTo(0, 0)
        p.lineTo(w * 0.40, 0)
        p.lineTo(w * 0.46, h * 0.18)
        p.lineTo(w, h * 0.18)
        p.lineTo(w, h)
        p.lineTo(0, h)
    elif kind == "filter":
        n = 30
        p.addPolygon(QPolygonF([
            QPointF(0, 0), QPointF(w - n, 0), QPointF(w, h / 2),
            QPointF(w - n, h), QPointF(0, h), QPointF(n, h / 2)
        ]))
    elif kind == "ask":
        n = 28
        p.addPolygon(QPolygonF([
            QPointF(n, 0), QPointF(w - n, 0), QPointF(w, h / 2),
            QPointF(w - n, h), QPointF(n, h), QPointF(0, h / 2)
        ]))
    elif kind == "exclude":
        c = 14
        p.addPolygon(QPolygonF([
            QPointF(c, 0), QPointF(w - c, 0), QPointF(w, c),
            QPointF(w, h - c), QPointF(w - c, h), QPointF(c, h),
            QPointF(0, h - c), QPointF(0, c)
        ]))
    else:
        p.addRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
    p.closeSubpath()
    return p


def bezier(a: QPointF, b: QPointF) -> QPainterPath:
    dx = max(60.0, abs(b.x() - a.x()) / 2)
    path = QPainterPath(a)
    path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
    return path


class NodeItem(QGraphicsPathItem):
    LABEL_OFFSET = {"filter": 36, "ask": 34, "exclude": 20}

    def __init__(self, node: Node) -> None:
        super().__init__(shape_path(node.kind))
        self.node = node
        self.edges: list[EdgeItem] = []
        self.setPos(node.x, node.y)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setBrush(QBrush(QColor(NODE_COLORS[node.kind])))
        self.setPen(QPen(QColor(NODE_ACCENT[node.kind]), 2))
        off = self.LABEL_OFFSET.get(node.kind, 14)
        self.label = QGraphicsTextItem(self)
        self.label.setDefaultTextColor(QColor("#F2F2F2"))
        self.label.setTextWidth(NODE_W - 2 * off)
        self.label.setPos(off, 14)
        self.refresh()

    def refresh(self) -> None:
        accent = NODE_ACCENT[self.node.kind]
        title = self.node.title.replace("<", "&lt;").replace(">", "&gt;")
        self.label.setHtml(
            f'<div style="color:{accent}; font-size:7pt;">{t(KIND_TITLES[self.node.kind]).upper()}</div>'
            f'<div style="color:#F2F2F2; font-size:9pt; font-weight:600;">{title}</div>'
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, src: NodeItem, dst: NodeItem, branch: str = "yes") -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.branch = branch
        if branch == "no":
            self.setPen(QPen(QColor("#C0504D"), 2.2, Qt.PenStyle.DashLine))
        else:
            self.setPen(QPen(QColor("#9A9EA6"), 2.5))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1)
        src.edges.append(self)
        dst.edges.append(self)
        self.update_path()

    def update_path(self) -> None:
        a = self.src.pos() + QPointF(NODE_W, NODE_H / 2)
        b = self.dst.pos() + QPointF(0, NODE_H / 2)
        self.setPath(bezier(a, b))


class SchemaView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, page: "SchemaPage") -> None:
        super().__init__(scene)
        self.page = page
        self._panning = False
        self._pan_start = None
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.centerOn(0, 0)

    def drawBackground(self, painter: QPainter, rect) -> None:
        painter.fillRect(rect, QColor("#181818"))
        pen = QPen(QColor("#272727"))
        pen.setWidth(1)
        painter.setPen(pen)
        x = int(rect.left()) - int(rect.left()) % GRID
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += GRID
        y = int(rect.top()) - int(rect.top()) % GRID
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += GRID

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME):
            kind = bytes(event.mimeData().data(MIME)).decode("utf-8")
            pos = self.mapToScene(event.position().toPoint())
            self.page.add_at(kind, pos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self.page.is_linking() and self.itemAt(event.position().toPoint()) is None:
            self.page.cancel_link()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)
        self.page.update_temp_link(self.mapToScene(event.position().toPoint()))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self._pan_start = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.page.is_linking():
            self.page.cancel_link()
        super().keyPressEvent(event)


def _split(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]

def _exts(text: str) -> list[str]:
    return ["." + s.lstrip(".").lower() for s in _split(text)]


class SchemaPage(QWidget):
    def __init__(self, on_apply: Callable[[list[Rule], list[str]], None] | None = None,
                 on_run: Callable[[list[str]], None] | None = None) -> None:
        super().__init__()
        self.on_apply = on_apply
        self.on_run = on_run
        self.schema: Schema = load_schema()
        self.scene = QGraphicsScene(-3000, -3000, 6000, 6000)
        self.view = SchemaView(self.scene, self)

        self.nodes: dict[str, NodeItem] = {}
        self.edges: list[EdgeItem] = []
        self._link_src: NodeItem | None = None
        self._link_branch = "yes"
        self._temp: QGraphicsPathItem | None = None
        self._current: NodeItem | None = None

        self.w = {
            "title": QLineEdit(), "folder": QLineEdit(), "masks": QLineEdit(),
            "exts": QLineEdit(), "keywords": QLineEdit(), "name_glob": QLineEdit(),
            "name_regex": QLineEdit(),
            "min_mb": self._mb_box(), "max_mb": self._mb_box(),
            "min_age_days": self._days_box(), "max_age_days": self._days_box(),
            "gps": QCheckBox(t("Только фото с GPS")),
            "rename": QLineEdit(),
        }
        self.w["masks"].setPlaceholderText("*.tmp, node_modules")
        self.w["exts"].setPlaceholderText("pdf, jpg")
        self.w["keywords"].setPlaceholderText(t("итого, чек"))
        self.w["name_glob"].setPlaceholderText("invoice_*.pdf")
        self.w["name_regex"].setPlaceholderText("^IMG_\\d+")
        self.w["rename"].setPlaceholderText("{date}_{name}.{ext}")

        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.rows: dict[str, tuple[QLabel, QWidget]] = {}
        for key, text in _labels():
            lbl = QLabel(text)
            form.addRow(lbl, self.w[key])
            self.rows[key] = (lbl, self.w[key])

        heading = QLabel(t("Свойства узла"))
        heading.setObjectName("Heading")
        self.help = QLabel(_general_help())
        self.help.setObjectName("Help")
        self.help.setWordWrap(True)

        ins = QVBoxLayout()
        ins.setContentsMargins(0, 0, 0, 0)
        ins.addWidget(heading)
        ins.addLayout(form)
        ins.addWidget(self._btn(t("Применить поля"), "", self._apply_fields,
                                t("Сохраняет изменения выбранного узла в схеме")))
        ins.addSpacing(12)
        ins.addWidget(self.help)
        ins.addStretch()
        inspector = QWidget()
        inspector.setLayout(ins)
        inspector.setFixedWidth(300)

        self.palette = NodePalette()
        self.palette.node_clicked.connect(self._add)

        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self.palette, 1)
        right.addWidget(inspector, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._btn(t("Связать"), "", lambda: self._start_link("yes"),
                                t("Выдели узел и нажми, затем кликни узел-получатель. Ведёт «да»")))
        row.addWidget(self._btn(t("Связать «нет»"), "", lambda: self._start_link("no"),
                                t("Ветка для файлов, которые не прошли фильтр. Только от фильтра")))
        row.addWidget(self._btn(t("Удалить"), "DangerBtn", self._delete,
                                t("Удаляет выделенные узлы и связи")))
        row.addWidget(self._btn(t("Сохранить"), "", self._save,
                                t("Записывает схему на диск, в папку AutoUtil")))
        row.addWidget(self._btn(t("Экспорт"), "", self._export,
                                t("Сохраняет схему в файл .json, чтобы передать другому человеку")))
        row.addWidget(self._btn(t("Импорт"), "", self._import,
                                t("Загружает схему из файла .json, заменяет текущую")))
        row.addStretch()

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.view, 1)
        body.addLayout(right)

        footer_text = QLabel(_footer_help())
        footer_text.setObjectName("Muted")
        footer_text.setWordWrap(True)
        footer = QHBoxLayout()
        footer.addWidget(footer_text, 1)
        footer.addSpacing(12)
        footer.addWidget(self._btn(t("Только правила"), "", self._apply,
                                   t("Обновляет правила, но не запускает наблюдение за папками")),
                         0, Qt.AlignmentFlag.AlignVCenter)
        footer.addSpacing(8)
        footer.addWidget(self._btn(t("Запустить схему"), "Primary", self._run,
                                   t("Сохраняет правила и начинает следить за папками из схемы")),
                         0, Qt.AlignmentFlag.AlignVCenter)

        self.status = QLabel("")
        self.status.setObjectName("Muted")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        root.addLayout(row)
        root.addLayout(body, 1)
        root.addSpacing(8)
        root.addLayout(footer)
        root.addWidget(self.status)

        self.scene.selectionChanged.connect(self._on_selection)
        self._load()
        self._fill(None)

    @staticmethod
    def _mb_box() -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(0, 1_000_000)
        box.setDecimals(1)
        box.setSpecialValueText(t("выкл"))
        return box

    @staticmethod
    def _days_box() -> QSpinBox:
        box = QSpinBox()
        box.setRange(0, 36500)
        box.setSpecialValueText(t("выкл"))
        return box

    def _btn(self, text: str, name: str, handler, tip: str = "") -> QPushButton:
        b = QPushButton(text)
        if name:
            b.setObjectName(name)
        if tip:
            b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(handler)
        return b

    def _load(self) -> None:
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        for n in self.schema.nodes:
            item = NodeItem(n)
            self.scene.addItem(item)
            self.nodes[n.id] = item
        for e in self.schema.edges:
            if e.src in self.nodes and e.dst in self.nodes:
                self._add_edge_item(e.src, e.dst, e.branch)

    def _add_edge_item(self, src_id: str, dst_id: str, branch: str = "yes") -> None:
        edge = EdgeItem(self.nodes[src_id], self.nodes[dst_id], branch)
        self.scene.addItem(edge)
        self.edges.append(edge)

    def _say(self, text: str) -> None:
        self.status.setText(text)

    def _single_node(self) -> NodeItem | None:
        items = [i for i in self.scene.selectedItems() if isinstance(i, NodeItem)]
        return items[0] if len(items) == 1 else None

    def is_linking(self) -> bool:
        return self._link_src is not None

    def _start_link(self, branch: str) -> None:
        src = self._single_node()
        if src is None:
            self._say(t("Выдели узел-источник и нажми «Связать»."))
            return
        if branch == "no" and src.node.kind not in NO_BRANCH_FROM:
            self._say(t("Ветка «нет» есть только у фильтра."))
            return
        self._link_src = src
        self._link_branch = branch
        self._temp = QGraphicsPathItem()
        color = "#C0504D" if branch == "no" else "#4A8FD8"
        self._temp.setPen(QPen(QColor(color), 2.5, Qt.PenStyle.DashLine))
        self._temp.setZValue(-0.5)
        self.scene.addItem(self._temp)
        self._say(t("Кликни узел-получатель для связи из «{title}». Esc отмена.", title=src.node.title))

    def update_temp_link(self, pos: QPointF) -> None:
        if self._link_src is None or self._temp is None:
            return
        a = self._link_src.pos() + QPointF(NODE_W, NODE_H / 2)
        self._temp.setPath(bezier(a, pos))

    def cancel_link(self) -> None:
        self._end_link()
        self._say(t("Связывание отменено."))

    def _end_link(self) -> None:
        if self._temp and self._temp.scene() is self.scene:
            self.scene.removeItem(self._temp)
        self._temp = None
        self._link_src = None

    def _finish_link(self, src: NodeItem, dst: NodeItem) -> None:
        if (src.node.kind, dst.node.kind) not in ALLOWED_LINKS:
            self._say(t("Такая связь не поддерживается."))
            return
        if self._link_branch == "no" and src.node.kind not in NO_BRANCH_FROM:
            self._say(t("Ветка «нет» есть только у фильтра."))
            return
        exists = any(e.src == src.node.id and e.dst == dst.node.id and e.branch == self._link_branch for e in self.schema.edges)
        if exists:
            self._say(t("Такая связь уже есть."))
            return
        self.schema.edges.append(Edge(src.node.id, dst.node.id, self._link_branch))
        self._add_edge_item(src.node.id, dst.node.id, self._link_branch)
        self._say(t("Связано."))

    def _add(self, kind: str) -> None:
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.add_at(kind, center)

    def add_at(self, kind: str, pos: QPointF) -> None:
        if kind not in _new_titles():
            return
        node = Node(id=uuid.uuid4().hex[:8], kind=kind, title=_new_titles()[kind],
                    x=pos.x() - NODE_W / 2, y=pos.y() - NODE_H / 2)
        self.schema.nodes.append(node)
        item = NodeItem(node)
        self.scene.addItem(item)
        self.nodes[node.id] = item
        self.scene.clearSelection()
        item.setSelected(True)
        self._say(t("Добавлен узел: {kind}. Заполни поля справа.", kind=t(KIND_TITLES[kind])))

    def _remove_edge(self, edge: EdgeItem) -> None:
        sid, did, br = edge.src.node.id, edge.dst.node.id, edge.branch
        self.schema.edges = [e for e in self.schema.edges if not (e.src == sid and e.dst == did and e.branch == br)]
        for n in (edge.src, edge.dst):
            if edge in n.edges:
                n.edges.remove(edge)
        if edge in self.edges:
            self.edges.remove(edge)
        if edge.scene() is self.scene:
            self.scene.removeItem(edge)

    def _delete(self) -> None:
        for item in list(self.scene.selectedItems()):
            if isinstance(item, EdgeItem):
                self._remove_edge(item)
            elif isinstance(item, NodeItem):
                for edge in list(item.edges):
                    self._remove_edge(edge)
                self.schema.nodes = [n for n in self.schema.nodes if n.id != item.node.id]
                self.nodes.pop(item.node.id, None)
                if item.scene() is self.scene:
                    self.scene.removeItem(item)
                if self._link_src is item:
                    self._end_link()
        self._say(t("Удалено."))

    def _save(self) -> None:
        for n in self.schema.nodes:
            item = self.nodes.get(n.id)
            if item is not None:
                n.x, n.y = item.pos().x(), item.pos().y()
        save_schema(self.schema)
        self._say(t("Схема сохранена."))

    def _run(self) -> None:
        self._save()
        rules = self.schema.to_rules()
        folders = self.schema.source_folders()
        if not rules:
            self._say(t("Нет ни одного пути «Папка → Цель». Соедини узлы и попробуй снова."))
            return
        if not folders:
            self._say(t("У папки-источника не заполнено поле «Папка»."))
            return
        missing = [f for f in folders if not Path(f).is_dir()]
        if missing:
            self._say(t("Папка не найдена: {path}. Укажи полный путь.", path=missing[0]))
            return
        save_rules(rules)
        if self.on_run:
            self.on_run(folders)
        note = t(" Достигнут лимит правил, часть схемы не применена.") if len(rules) >= MAX_RULES else ""
        self._say(t("Схема запущена: правил {rules}, папок {folders}.{note}", rules=len(rules), folders=len(folders), note=note))

    def _apply(self) -> None:
        self._save()
        rules = self.schema.to_rules()
        if not rules:
            self._say(t("Нет ни одного пути «Папка → Цель». Соедини узлы и попробуй снова."))
            return
        answer = QMessageBox.question(
            self, t("Применить схему"), t("Заменить текущие правила на {n} правил из схемы?", n=len(rules)),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        save_rules(rules)
        if self.on_apply:
            self.on_apply(rules, self.schema.source_folders())
        self._say(t("Применено правил: {n}.", n=len(rules)))

    def _export(self) -> None:
        self._save()
        path, _ = QFileDialog.getSaveFileName(self, t("Экспорт схемы"), "schema.json",
                                              t(t("Схема AutoUtil (*.json)")))
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        save_schema(self.schema, Path(path))
        self._say(t("Схема экспортирована: {path}", path=path))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("Импорт схемы"), "", t("Схема AutoUtil (*.json)"))
        if not path:
            return
        try:
            imported = load_schema(Path(path))
        except Exception as e:
            self._say(t("Не удалось прочитать схему: {e}", e=e))
            return
        if not imported.nodes:
            self._say(t("В файле нет ни одного узла."))
            return
        answer = QMessageBox.question(
            self, t(t("Импорт схемы")),
            t("Заменить текущую схему импортированной? Несохранённые изменения пропадут."),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.schema = imported
        self._load()
        self._fill(None)
        self._save()
        self._say(t("Схема импортирована: узлов {nodes}, связей {edges}.", nodes=len(imported.nodes), edges=len(imported.edges)))

    def _on_selection(self) -> None:
        node_item = self._single_node()
        if self._link_src is not None and node_item is not None and node_item is not self._link_src:
            self._finish_link(self._link_src, node_item)
            self._end_link()
        self._current = node_item
        self._fill(node_item.node if node_item else None)

    def _fill(self, node: Node | None) -> None:
        p = node.params if node else {}
        self.w["title"].setText(node.title if node else "")
        self.w["folder"].setText(p.get("folder", ""))
        self.w["masks"].setText(", ".join(p.get("masks", [])))
        self.w["exts"].setText(", ".join(p.get("exts", [])))
        self.w["keywords"].setText(", ".join(p.get("keywords", [])))
        self.w["name_glob"].setText(p.get("name_glob", ""))
        self.w["name_regex"].setText(p.get("name_regex", ""))
        self.w["min_mb"].setValue(float(p.get("min_mb") or 0))
        self.w["max_mb"].setValue(float(p.get("max_mb") or 0))
        self.w["min_age_days"].setValue(int(p.get("min_age_days") or 0))
        self.w["max_age_days"].setValue(int(p.get("max_age_days") or 0))
        self.w["gps"].setChecked(bool(p.get("requires_gps")))
        self.w["rename"].setText(p.get("rename", ""))
        visible = set(FIELDS[node.kind]) if node else set()
        for key, (lbl, widget) in self.rows.items():
            show = key in visible
            lbl.setVisible(show)
            widget.setVisible(show)
        self.help.setText(_help().get(node.kind) if node else _general_help())

    def _params(self, kind: str) -> dict:
        w = self.w
        if kind == "source":
            return {"folder": w["folder"].text().strip()}
        if kind == "target":
            return {"folder": w["folder"].text().strip(), "rename": w["rename"].text().strip()}
        if kind == "filter":
            return {
                "exts": _exts(w["exts"].text()),
                "keywords": _split(w["keywords"].text()),
                "name_glob": w["name_glob"].text().strip(),
                "name_regex": w["name_regex"].text().strip(),
                "min_mb": w["min_mb"].value(),
                "max_mb": w["max_mb"].value(),
                "min_age_days": w["min_age_days"].value(),
                "max_age_days": w["max_age_days"].value(),
                "requires_gps": w["gps"].isChecked(),
            }
        if kind == "exclude":
            return {"masks": _split(w["masks"].text())}
        return {}

    def _apply_fields(self) -> None:
        if self._current is None:
            return
        n = self._current.node
        pattern = self.w["name_regex"].text().strip()
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                self._say(t("Регулярное выражение не работает: {e}", e=e))
                return
        n.title = self.w["title"].text().strip() or n.title
        n.params = self._params(n.kind)
        self._current.refresh()
        self._say(t("Поля применены. Не забудь \"Сохранить\"."))
