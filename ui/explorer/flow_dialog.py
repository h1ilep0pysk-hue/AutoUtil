"""Окно «Предпросмотр сортировки».

Слева — папка-источник, справа — цели (папки и корзина). Файлеты по очереди
летят по дугам к своим целям с цветом группы-получателя — ровно так, как их
разложит сервис: первое совпавшее правило, шаблон имени, корзина, «Спросить»
и «Через N дней» учитываются.

Анимируются первые MAX_ANIMATIONS файлов; полный список — под сценой.

Каркас сцены тёмный весь — как на странице «Схема» (drawBackground там тоже
залит константным #181818 независимо от темы), чтобы картинка всегда читалась.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGraphicsPathItem, QGraphicsScene, QGraphicsTextItem,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from core.i18n import t
from modules.organizer.preview import DEFAULT_OCR_LIMIT, FolderPreview, preview_folder

log = logging.getLogger("autoutil.ui.flow")

NODE_W, NODE_H = 210, 64
SOURCE_X = 48
DEST_X = 520
GAP_Y = 34             # просвет между узлами-целями
SPEED = 520.0          # скорость полёта файла, px/сек
TICK_MS = 25
STAGGER_TICKS = 4      # тики между запусками файлов (~100 мс)
LIST_HEIGHT = 170      # высота списка «файл → куда»
MAX_ANIMATIONS = 60    # сколько файлов анимируем, остальное — в списке
MAX_ROWS = 500         # сколько строк показываем в списке

CHIP_COLORS = [
    "#5B8FC7", "#9B7FD1", "#D9A441", "#4E9FA8", "#D45D5D", "#5FB38A",
    "#8AB4F8", "#C98BB8", "#7FB3A6", "#B0A44E",
]
BG = "#181818"
NODE_FILL = "#242424"
TEXT = "#F2F2F2"
MUTED = "#9B9B9F"


def _curve(a: QPointF, b: QPointF) -> QPainterPath:
    dx = max(80.0, abs(b.x() - a.x()) / 2)
    path = QPainterPath(a)
    path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
    return path


class _FlowView(QGraphicsView):
    """Сцена, которую можно двигать перетаскиванием и стрелками, зум колесом."""

    KEY_STEP = 80  # строка за клавишу-стрелку

    def __init__(self, scene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pan_last: QPointF | None = None

    # --- перетаскивание ---------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._pan_last = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_last is not None:
            pos = event.position()
            delta = pos - self._pan_last
            self._pan_last = pos
            # Значение скролла — в пикселях сцены, курсор — в пикселях окна.
            scale = max(abs(self.transform().m11()), 1e-6)
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x() / scale)
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y() / scale)
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --- колесо: зум вокруг курсора --------------------------------------

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.scale(factor, factor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        event.accept()

    # --- клавиатура: стрелки двигают сцену --------------------------------

    def keyPressEvent(self, event) -> None:
        h = self.horizontalScrollBar()
        v = self.verticalScrollBar()
        key = event.key()
        if key == Qt.Key.Key_Left:
            h.setValue(h.value() - self.KEY_STEP)
        elif key == Qt.Key.Key_Right:
            h.setValue(h.value() + self.KEY_STEP)
        elif key == Qt.Key.Key_Up:
            v.setValue(v.value() - self.KEY_STEP)
        elif key == Qt.Key.Key_Down:
            v.setValue(v.value() + self.KEY_STEP)
        elif key == Qt.Key.Key_PageUp:
            v.setValue(v.value() - v.pageStep())
        elif key == Qt.Key.Key_PageDown:
            v.setValue(v.value() + v.pageStep())
        elif key == Qt.Key.Key_Home:
            h.setValue(h.minimum()); v.setValue(v.minimum())
        elif key == Qt.Key.Key_End:
            h.setValue(h.maximum()); v.setValue(v.maximum())
        else:
            super().keyPressEvent(event)
            return
        event.accept()


def _tail(dst: str, parts: int = 2) -> str:
    p = Path(dst)
    return " / ".join(x for x in p.parts[-parts:] if x)


class _Chip(QGraphicsPathItem):
    """Маленькая «табличка» с именем файла, которая летит по дуге."""

    def __init__(self, name: str, color: QColor) -> None:
        super().__init__()
        cap = name if len(name) <= 28 else name[:27] + "…"
        fm = QFontMetricsF(QFont())
        width = max(fm.horizontalAdvance(cap) + 20.0, 42.0)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0, 0, width, 24), 12, 12)
        self.setPath(shape)
        self.setBrush(QBrush(color))
        self.setPen(QPen(color, 0))
        self.setOpacity(0.95)
        text = QGraphicsTextItem(cap, self)
        text.setDefaultTextColor(QColor("#101014"))
        text.setPos(9, -2)

    def center(self) -> QPointF:
        r = self.boundingRect()
        return QPointF(r.width() / 2, r.height() / 2)


class _NodeBox(QGraphicsPathItem):
    """Узел-папка: заголовок, подпись и счётчик прибывших файлов."""

    def __init__(self, title: str, sub: str, accent: str) -> None:
        super().__init__()
        self._accent = QColor(accent)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0, 0, NODE_W, NODE_H), 14, 14)
        self.setPath(shape)
        self.setBrush(QBrush(QColor(NODE_FILL)))
        self.setPen(QPen(QColor(accent), 2))
        self.setZValue(2)
        self.counter = 0
        title_item = QGraphicsTextItem(self)
        title_item.setDefaultTextColor(QColor(TEXT))
        title_item.setTextWidth(NODE_W - 24)
        title_item.setPos(12, 8)
        title_item.setHtml(f"<b>{title}</b>")
        sub_item = QGraphicsTextItem(sub, self)
        sub_item.setDefaultTextColor(QColor(MUTED))
        sub_item.setTextWidth(NODE_W - 24)
        sub_item.setPos(12, 34)
        self._count_item = QGraphicsTextItem("", self)
        self._count_item.setDefaultTextColor(QColor(accent))
        self._count_item.setPos(NODE_W - 46, NODE_H - 36)

    def bump(self) -> None:
        self.counter += 1
        self._count_item.setPlainText(f"+{self.counter}")
        self.setPen(QPen(QColor("#FFFFFF"), 3))
        QTimer.singleShot(260, self._unflash)

    def _unflash(self) -> None:
        self.setPen(QPen(self._accent, 2))

    def reset(self) -> None:
        self.counter = 0
        self._count_item.setPlainText("")
        self.setPen(QPen(self._accent, 2))

    def left_center(self) -> QPointF:
        return self.pos() + QPointF(0, NODE_H / 2)

    def right_center(self) -> QPointF:
        return self.pos() + QPointF(NODE_W, NODE_H / 2)


class _Edge(QGraphicsPathItem):
    """Дуга от источника к цели — цвет группы."""

    def __init__(self, a: QPointF, b: QPointF, color: str) -> None:
        super().__init__()
        pen = QPen(QColor(color))
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setPath(_curve(a, b))
        self.setZValue(-2)


@dataclass
class _Template:
    """Заготовка полёта: имя файла, цвет группы, дуга, узел-получатель."""
    name: str
    color: QColor
    path: QPainterPath
    node: _NodeBox


@dataclass
class _Flight:
    """Один полёт файла: чип на дуге и пройденное расстояние."""
    chip: _Chip
    tpl: _Template
    travelled: float = 0.0
    fading: bool = False


def _flow_summary(preview: FolderPreview) -> str:
    if not preview.moves:
        text = t("flow.no_moves", total=preview.total_files)
    else:
        text = t("flow.summary", moves=len(preview.moves), total=preview.total_files)
        unmatched = preview.total_files - len(preview.moves)
        if unmatched > 0:
            text += t("flow.unmatched", n=unmatched)
    if preview.ocr_capped:
        text += " " + t("preview.ocr_capped", n=DEFAULT_OCR_LIMIT)
    return text


class _FlowWorker(QObject):
    """Считает предпросмотр в фоне: анализ папки может занять время."""
    done = Signal(object)

    def __init__(self, folder: str, rules: list | None) -> None:
        super().__init__()
        self.folder = folder
        self.rules = rules

    def run(self) -> None:
        from win.paths import documents_dir

        try:
            result = preview_folder(
                Path(self.folder), documents_dir().parent, rules=self.rules or None,
            )
        except Exception:
            log.exception("Ошибка предпросмотра сортировки")
            result = FolderPreview()
        self.done.emit(result)


class SortingPreviewDialog(QDialog):
    def __init__(self, default_folder: str = "", rules: list | None = None, parent=None) -> None:
        super().__init__(parent or None)
        if not default_folder:
            default_folder = _default_preview_folder()
        self.rules = rules or None
        self.setWindowTitle(t("flow.title"))
        self.resize(1000, 700)
        self.setMinimumWidth(760)
        # FIX: всегда открывается развёрнутым на весь экран.
        self.setWindowState(Qt.WindowState.WindowMaximized)

        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QColor(BG))
        self.view = _FlowView(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)

        self.folder_edit = QLineEdit(default_folder)
        self.folder_browse = QPushButton("…")
        self.folder_browse.setFixedWidth(36)
        self.folder_browse.setToolTip(t("preview.pick"))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"color: {MUTED}; background: transparent;")
        self.moves_list = QListWidget()
        self.moves_list.setFixedHeight(LIST_HEIGHT)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {MUTED}; background: transparent;")

        top = QHBoxLayout()
        top.addWidget(QLabel(t("preview.folder")))
        top.addWidget(self.folder_edit, 1)
        top.addWidget(self.folder_browse)

        bottom = QHBoxLayout()
        self.replay_btn = QPushButton(t("flow.replay"))
        self.close_btn = QPushButton(t("flow.close"))
        bottom.addWidget(self.replay_btn)
        bottom.addStretch()
        bottom.addWidget(self.close_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(10)
        title = QLabel(f"<b>{t('flow.title')}</b>")
        title.setStyleSheet("background: transparent;")
        root.addWidget(title)
        root.addLayout(top)
        root.addWidget(self.summary)
        hint = QLabel(t("flow.nav_tip"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED}; background: transparent;")
        root.addWidget(hint)
        root.addWidget(self.view, 1)
        root.addWidget(self.status_label)
        root.addWidget(self.moves_list)
        root.addLayout(bottom)

        self.replay_btn.clicked.connect(self._replay)
        self.close_btn.clicked.connect(self.accept)
        self.folder_browse.clicked.connect(self._pick_folder)
        self.folder_edit.returnPressed.connect(self._rescan)

        self._thread: QThread | None = None
        self._worker: _FlowWorker | None = None
        self._requested = ""
        self._source: _NodeBox | None = None
        self._transient: list = []
        self._templates: list[_Template] = []
        self._queue: list[_Template] = []
        self._active: list[_Flight] = []
        self._launch_gap = 0

        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)

        self._rescan()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Развёрнутое окно: сцена всегда занимает весь доступный размер.
        self._fit_scene()

    MAX_FIT_SCALE = 1.8  # не раздувать карту сверх этого на больших экранах

    def _fit_scene(self) -> None:
        rect = self.scene.sceneRect()
        if rect.isEmpty():
            return
        self.view.resetTransform()
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        scale = abs(self.view.transform().m11())
        if scale > self.MAX_FIT_SCALE:
            self.view.resetTransform()
            self.view.scale(self.MAX_FIT_SCALE, self.MAX_FIT_SCALE)
            self.view.centerOn(rect.center())

    # --- данные ---------------------------------------------------------

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("preview.pick"), self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)
            self._rescan()

    def _rescan(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return  # уже считаем; перезапустимся, когда придёт результат
        folder = Path(self.folder_edit.text().strip())
        if not folder.is_dir():
            self.status_label.setText(t("preview.folder_missing", path=str(folder)))
            return
        self.status_label.setText(t("preview.running"))
        self.replay_btn.setEnabled(False)
        self._requested = str(folder)
        self._thread = QThread(self)
        self._worker = _FlowWorker(self._requested, self.rules)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._show)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

    def _show(self, preview: FolderPreview) -> None:
        self.replay_btn.setEnabled(True)
        # Папку успели поменять, пока шёл расчёт — пересчитываем для новой.
        current = self.folder_edit.text().strip()
        if current and current != self._requested:
            self._rescan()
            return
        self.status_label.setText("")
        self._layout_nodes(preview)
        self._fill_list(preview)
        self.summary.setText(_flow_summary(preview))
        self._replay()

    def _fill_list(self, preview: FolderPreview) -> None:
        self.moves_list.clear()
        for move in preview.moves[:MAX_ROWS]:
            flags = []
            if move.ask:
                flags.append(t("flow.ask"))
            if move.delay_days:
                flags.append(t("flow.delay", days=move.delay_days))
            extra = f" • {', '.join(flags)}" if flags else ""
            row = (
                f"{move.src.name}   →   {_tail(move.dst)}"
                if not move.to_bin else
                f"{move.src.name}   →   {move.dst}"
            )
            item = QListWidgetItem(f"{row}{extra}   ({t('flow.rule')}: {move.rule})")
            item.setToolTip(str(move.src))
            self.moves_list.addItem(item)
        if len(preview.moves) > MAX_ROWS:
            self.status_label.setText(t("preview.truncated", n=MAX_ROWS).strip())

    # --- сцена ----------------------------------------------------------

    def _clear_scene(self) -> None:
        for item in self._transient:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._transient = []
        self.timer.stop()
        for fl in self._active:
            if fl.chip.scene() is self.scene:
                self.scene.removeItem(fl.chip)
        self._active = []
        self._queue = []
        self._templates = []
        if self._source is not None and self._source.scene() is self.scene:
            self.scene.removeItem(self._source)
        self._source = None

    def _layout_nodes(self, preview: FolderPreview) -> None:
        self._clear_scene()
        if not preview.moves:
            self._show_empty()
            return

        groups: dict[str, list] = {}
        for move in preview.moves:
            key = move.dst if move.to_bin else _tail(move.dst)
            if move.ask:
                key += " • " + t("flow.ask")
            elif move.delay_days:
                key += " • " + t("flow.delay", days=move.delay_days)
            groups.setdefault(key, []).append(move)

        # Логическая раскладка зависит только от числа целей: сцена строится
        # так, чтобы ВСЕ блоки помещались при любом размере экрана, а затем
        # целиком масштабируется под окно — блоки не убегают за экран. FIX
        n = len(groups)
        step = NODE_H + GAP_Y
        stack_h = step * (n - 1) + NODE_H
        top = 40.0

        source = _NodeBox(
            Path(self.folder_edit.text().strip()).name, t("preview.folder"), "#5B8FC7",
        )
        source.setPos(SOURCE_X, top + stack_h / 2 - NODE_H / 2)
        self._source = source

        for idx, (key, moves) in enumerate(sorted(groups.items())):
            color = QColor(CHIP_COLORS[idx % len(CHIP_COLORS)])
            to_bin = moves[0].to_bin
            node = _NodeBox(key, "", "#E06C75" if to_bin else color.name())
            node.setPos(DEST_X, top + step * idx)
            start, end = source.right_center(), node.left_center()
            for move in moves[:MAX_ANIMATIONS]:
                self._templates.append(
                    _Template(name=move.src.name, color=color, path=_curve(start, end), node=node)
                )
            self._transient.append(node)
            self._transient.append(_Edge(start, end, color.name()))

        self.scene.addItem(source)
        for item in self._transient:
            self.scene.addItem(item)

        scene_w = DEST_X + NODE_W + 70
        scene_h = stack_h + 2 * top
        self.scene.setSceneRect(QRectF(0, 0, scene_w, scene_h))
        self._fit_scene()

    def _show_empty(self) -> None:
        notice = QGraphicsTextItem(t("flow.no_moves", total=0))
        notice.setDefaultTextColor(QColor(MUTED))
        notice.setPos(40, 40)
        self.scene.addItem(notice)
        self._transient.append(notice)
        self.scene.setSceneRect(QRectF(0, 0, 900, 320))
        self._fit_scene()

    def _replay(self) -> None:
        if not self._templates:
            return
        for fl in self._active:
            if fl.chip.scene() is self.scene:
                self.scene.removeItem(fl.chip)
        self._active = []
        self._queue = list(self._templates)
        self._launch_gap = 0
        for tpl in self._templates:
            tpl.node.reset()
        self.timer.start()

    # --- анимация -------------------------------------------------------

    def _start_flight(self, tpl: _Template) -> None:
        chip = _Chip(tpl.name, tpl.color)
        self.scene.addItem(chip)
        start = tpl.path.pointAtPercent(0.0)
        c = chip.center()
        chip.setPos(start.x() - c.x(), start.y() - c.y())
        chip.setZValue(5)
        self._active.append(_Flight(chip=chip, tpl=tpl))

    def _tick(self) -> None:
        if self._queue and self._launch_gap <= 0:
            self._start_flight(self._queue.pop(0))
            self._launch_gap = STAGGER_TICKS
        self._launch_gap -= 1
        step = SPEED * (TICK_MS / 1000.0)
        for fl in list(self._active):
            if fl.fading:
                fl.chip.setOpacity(fl.chip.opacity() - 0.055)
                if fl.chip.opacity() <= 0.0:
                    if fl.chip.scene() is self.scene:
                        self.scene.removeItem(fl.chip)
                    self._active.remove(fl)
                continue
            fl.travelled += step
            frac = min(fl.travelled / max(fl.tpl.path.length(), 1.0), 1.0)
            ease = frac * frac * (3.0 - 2.0 * frac)  # smoothstep: разгон и торможение
            point = fl.tpl.path.pointAtPercent(ease)
            c = fl.chip.center()
            fl.chip.setPos(point.x() - c.x(), point.y() - c.y())
            if frac >= 1.0:
                self._arrive(fl)

        if not self._active and not self._queue:
            self.timer.stop()

    def _arrive(self, fl: _Flight) -> None:
        tpl = fl.tpl
        point = tpl.path.pointAtPercent(1.0)
        c = fl.chip.center()
        fl.chip.setPos(point.x() - c.x(), point.y() - c.y())
        tpl.node.bump()
        fl.fading = True

    def closeEvent(self, event) -> None:  # сцена и таймер не должны переживать окно
        self.timer.stop()
        super().closeEvent(event)


def _default_preview_folder() -> str:
    """Первая папка-источник из живой схемы, иначе «Загрузки»."""
    try:
        from core.schema import load_schema

        for f in load_schema().source_folders():
            if Path(f).is_dir():
                return f
    except Exception:
        pass
    from win.paths import downloads_dir

    return str(downloads_dir())
