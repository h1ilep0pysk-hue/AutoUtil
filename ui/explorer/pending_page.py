from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from core.i18n import t
from core.journal import Journal
from core.pending import PendingStore
from modules.organizer.actions import apply_move, prepare_target
from modules.organizer.learning import Learned
from modules.organizer.planner import learn_key
from win.paths import documents_dir


class PendingPage(QWidget):
    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.journal = journal
        self.store = PendingStore()
        self.learned = Learned()
        self.base = documents_dir().parent
        self._suggestion: tuple[str, str] | None = None

        title = QLabel(t("Спросить"))
        title.setProperty("role", "title")
        sub = QLabel(t("Файлы, которые правило не переносит само. Перенеси, пропусти или выбери папку."))
        sub.setProperty("role", "muted")
        sub.setWordWrap(True)

        self.suggest_label = QLabel("")
        self.suggest_label.setWordWrap(True)
        self.accept_btn = QPushButton(t("Запомнить"))
        self.accept_btn.setObjectName("Primary")
        self.reject_btn = QPushButton(t("Не сейчас"))
        self.accept_btn.clicked.connect(self._accept)
        self.reject_btn.clicked.connect(self._reject)
        sugg = QHBoxLayout()
        sugg.setSpacing(8)
        sugg.addWidget(self.suggest_label, 1)
        sugg.addWidget(self.accept_btn)
        sugg.addWidget(self.reject_btn)
        self.suggest_box = QWidget()
        self.suggest_box.setLayout(sugg)

        self.list = QListWidget()
        self.empty = QLabel(t("Пока пусто. Здесь появятся файлы, которые сработали на узел «Спросить»."))
        self.empty.setProperty("role", "muted")
        self.empty.setWordWrap(True)

        self.move_btn = QPushButton(t("Перенести"))
        self.move_btn.setObjectName("Primary")
        self.elsewhere_btn = QPushButton(t("Перенести в…"))
        self.skip_btn = QPushButton(t("Пропустить"))
        self.refresh_btn = QPushButton(t("Обновить"))
        self.status = QLabel("")
        self.status.setProperty("role", "muted")

        self.move_btn.clicked.connect(self._move)
        self.elsewhere_btn.clicked.connect(self._move_elsewhere)
        self.skip_btn.clicked.connect(self._skip)
        self.refresh_btn.clicked.connect(self.reload)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        for btn in (self.move_btn, self.elsewhere_btn, self.skip_btn, self.refresh_btn):
            bar.addWidget(btn)
        bar.addStretch()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(self.suggest_box)
        root.addLayout(bar)
        root.addWidget(self.list, 1)
        root.addWidget(self.empty)
        root.addWidget(self.status)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        items = self.store.all_items()
        for it in items:
            label = f"{Path(it.src).name}   →   {Path(it.dst).parent}   ({it.rule})"
            li = QListWidgetItem(label)
            li.setToolTip(it.src)
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            self.list.addItem(li)
        self.empty.setVisible(not items)
        self._refresh_suggestion()

    def _refresh_suggestion(self) -> None:
        found = self.learned.suggestions()
        if not found:
            self._suggestion = None
            self.suggest_box.setVisible(False)
            return
        key, folder, count = found[0]
        rule, _, ext = key.partition("|")
        self._suggestion = (key, folder)
        self.suggest_label.setText(
            t("Правило «{rule}», файлы {ext}: ты {count} раз кладёшь их в «{folder}». Запомнить и переносить туда автоматически?", rule=rule, ext=ext, count=count, folder=folder)
        )
        self.suggest_box.setVisible(True)

    def _accept(self) -> None:
        if self._suggestion:
            self.learned.accept(self._suggestion[0])
            self.status.setText(t("Запомнено. Новые файлы пойдут в эту папку."))
        self.reload()

    def _reject(self) -> None:
        if self._suggestion:
            self.learned.reject(self._suggestion[0])
            self.status.setText(t("Предложение сброшено. Спрошу снова, когда накопится."))
        self.reload()

    def _current_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _do_move(self, pid: str, dst_path: Path) -> bool:
        pm = self.store.get(pid)
        if pm is None:
            return False
        src = Path(pm.src)
        if not src.exists():
            self.store.remove(pid)
            self.status.setText(t("Файла уже нет на месте. Запись удалена."))
            return False
        dst = prepare_target(dst_path)
        try:
            self.journal.record_move(src, dst, pm.rule)
            apply_move(src, dst)
        except OSError as e:
            self.status.setText(t("Не удалось перенести: {e}", e=e))
            return False
        self.store.remove(pid)
        self.status.setText(t("Перенесено: {name}", name=dst.name))
        return True

    def _move(self) -> None:
        pid = self._current_id()
        if pid is None:
            self.status.setText(t("Выбери файл в списке."))
            return
        pm = self.store.get(pid)
        if pm is None:
            self.reload()
            return
        self._do_move(pid, Path(pm.dst))
        self.reload()

    def _move_elsewhere(self) -> None:
        pid = self._current_id()
        if pid is None:
            self.status.setText(t("Выбери файл в списке."))
            return
        pm = self.store.get(pid)
        if pm is None:
            self.reload()
            return
        folder = QFileDialog.getExistingDirectory(self, t("Куда перенести"), str(self.base))
        if not folder:
            return
        target_dir = Path(folder)
        if self._do_move(pid, target_dir / Path(pm.src).name):
            ext = Path(pm.src).suffix.lower()
            try:
                rel = target_dir.relative_to(self.base).as_posix()
            except ValueError:
                rel = ""
            if rel:
                self.learned.record(learn_key(pm.rule, ext), rel)
        self.reload()

    def _skip(self) -> None:
        pid = self._current_id()
        if pid is None:
            self.status.setText(t("Выбери файл в списке."))
            return
        self.store.remove(pid)
        self.reload()
        self.status.setText(t("Пропущено. Файл остаётся на месте."))
