from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from core.deferred import DeferredStore
from core.i18n import t
from core.journal import Journal
from core.pending import PendingStore
from modules.organizer.actions import apply_move, prepare_target, recycle
from modules.organizer.learning import Learned
from modules.organizer.planner import learn_key
from win.paths import documents_dir


class PendingPage(QWidget):
    def __init__(self, journal: Journal) -> None:
        super().__init__()
        self.journal = journal
        self.store = PendingStore()
        self.deferred = DeferredStore()
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

        # Отложенные файлы («Через N дней»): срок ещё не наступил.
        self.dtitle = QLabel(t("Отложенные файлы"))
        self.dtitle.setProperty("role", "title")
        self.dsub = QLabel(t("Файлы, у которых действие «Через N дней» ещё не наступило. Можно выполнить сейчас или отменить."))
        self.dsub.setProperty("role", "muted")
        self.dsub.setWordWrap(True)
        self.dlist = QListWidget()
        self.dempty = QLabel(t("Пока нет отложенных файлов."))
        self.dempty.setProperty("role", "muted")
        self.dempty.setWordWrap(True)
        self.drun_btn = QPushButton(t("Выполнить сейчас"))
        self.dcancel_btn = QPushButton(t("Отменить"))
        self.drun_btn.clicked.connect(self._run_now)
        self.dcancel_btn.clicked.connect(self._cancel_deferred)
        dbar = QHBoxLayout()
        dbar.setSpacing(8)
        dbar.addWidget(self.drun_btn)
        dbar.addWidget(self.dcancel_btn)
        dbar.addStretch()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(self.suggest_box)
        root.addLayout(bar)
        root.addWidget(self.list, 1)
        root.addWidget(self.empty)
        root.addSpacing(10)
        root.addWidget(self.dtitle)
        root.addWidget(self.dsub)
        root.addLayout(dbar)
        root.addWidget(self.dlist, 1)
        root.addWidget(self.dempty)
        root.addWidget(self.status)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        items = self.store.all_items()
        for it in items:
            dst_label = t("Корзина") if it.bin else Path(it.dst).parent
            label = f"{Path(it.src).name}   →   {dst_label}   ({it.rule})"
            li = QListWidgetItem(label)
            li.setToolTip(it.src)
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            self.list.addItem(li)
        self.empty.setVisible(not items)
        self._refresh_suggestion()
        self._reload_deferred()

    def _reload_deferred(self) -> None:
        self.dlist.clear()
        items = self.deferred.all_items()
        for it in items:
            when = t("через {n} дн.", n=it.days)
            dst_label = t("Корзина") if it.bin else Path(it.dst).parent
            ask_mark = f"  [{t('Спросить')}]" if it.ask else ""
            label = f"{Path(it.src).name}   →   {dst_label}{ask_mark}   ({when}; {it.rule})"
            li = QListWidgetItem(label)
            li.setToolTip(it.src)
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            self.dlist.addItem(li)
        self.dempty.setVisible(not items)

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

    def _deferred_id(self) -> str | None:
        item = self.dlist.currentItem()
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
            dst = apply_move(src, dst)  # FIX: перенос первым, запись в журнал после успеха
            self.journal.record_move(src, dst, pm.rule)
        except OSError as e:
            self.status.setText(t("Не удалось перенести: {e}", e=e))
            return False
        self.store.remove(pid)
        self.status.setText(t("Перенесено: {name}", name=dst.name))
        return True

    def _do_bin(self, pid: str) -> bool:
        pm = self.store.get(pid)
        if pm is None:
            return False
        src = Path(pm.src)
        if not src.exists():
            self.store.remove(pid)
            self.status.setText(t("Файла уже нет на месте. Запись удалена."))
            return False
        ok = recycle(src)
        if not ok:
            self.status.setText(t("Не удалось убрать в корзину."))
            return False
        self.journal.record_bin(src, pm.rule)
        self.store.remove(pid)
        self.status.setText(t("Убрано в корзину: {name}", name=src.name))
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
        if pm.bin:
            self._do_bin(pid)
        else:
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

    # --- Отложенные файлы («Через N дней») ------------------------------

    def _run_now(self) -> None:
        did = self._deferred_id()
        if did is None:
            self.status.setText(t("Выбери отложенный файл в списке."))
            return
        di = self.deferred.get(did)
        if di is None:
            self.reload()
            return
        src = Path(di.src)
        if not src.exists():
            self.deferred.remove(did)
            self.reload()
            self.status.setText(t("Файла уже нет на месте. Запись удалена."))
            return
        self.deferred.remove(did)
        if di.ask:
            self.pending.add(str(src), di.dst, di.rule, bin=di.bin)
            self.status.setText(t("Файл вернулся в раздел «Спросить»."))
            self.reload()
            return
        try:
            if di.bin:
                if not recycle(src):
                    self.status.setText(t("Не удалось убрать в корзину."))
                    self.reload()
                    return
                self.journal.record_bin(src, di.rule)
                self.status.setText(t("Убрано в корзину: {name}", name=src.name))
            else:
                dst = prepare_target(Path(di.dst))
                dst = apply_move(src, dst)  # FIX: перенос первым, запись после успеха
                self.journal.record_move(src, dst, di.rule)
                self.status.setText(t("Перенесено: {name}", name=dst.name))
        except OSError as e:
            self.status.setText(t("Не удалось перенести: {e}", e=e))
        self.reload()

    def _cancel_deferred(self) -> None:
        did = self._deferred_id()
        if did is None:
            self.status.setText(t("Выбери отложенный файл в списке."))
            return
        di = self.deferred.get(did)
        if di is None:
            self.reload()
            return
        self.deferred.remove(did)
        self.reload()
        self.status.setText(t("Отменено: {name} остаётся на месте.", name=Path(di.src).name))
