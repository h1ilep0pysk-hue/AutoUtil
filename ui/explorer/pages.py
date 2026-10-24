import pyperclip
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.config import AppSettings, save_settings
from core.journal import Journal
from core.prefs import UiPrefs, save_prefs
from modules.grabber.history import History
from modules.organizer.rules_store import load_rules, save_rules
from ui.explorer.models import CaptureModel, JournalModel, RuleModel
from win.autostart import set_autostart
from win.hotkeys import parse_hotkey


def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "title")
    return lbl


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "muted")
    lbl.setWordWrap(True)
    return lbl


class _Page(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(12)
        self.root.addWidget(_title(title))
        if subtitle:
            self.root.addWidget(_muted(subtitle))


class CapturesPage(_Page):
    def __init__(self, history: History, prefs: UiPrefs) -> None:
        super().__init__("Захваты текста", "Последние распознанные фрагменты. Двойной клик копирует.")
        self.history = history
        self.prefs = prefs
        self.model = CaptureModel()
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.doubleClicked.connect(self._copy_index)

        self.copy_btn = QPushButton("Копировать")
        self.copy_btn.clicked.connect(lambda: self._copy_index(self.view.currentIndex()))
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.reload)
        bar = QHBoxLayout()
        bar.addWidget(self.copy_btn)
        bar.addWidget(self.refresh_btn)
        bar.addStretch()

        self.root.addLayout(bar)
        self.root.addWidget(self.view, 1)
        self.reload()

    def reload(self) -> None:
        self.model.set_items(self.history.list()[: self.prefs.history_limit])

    def _copy_index(self, idx) -> None:
        if idx.isValid():
            pyperclip.copy(self.model.item(idx.row()).text)


class JournalPage(_Page):
    def __init__(self, journal: Journal, prefs: UiPrefs) -> None:
        super().__init__("Журнал действий", "Все перемещения файлов. Можно вернуть любое.")
        self.journal = journal
        self.prefs = prefs
        self.model = JournalModel()
        self.view = QListView()
        self.view.setModel(self.model)

        self.undo_btn = QPushButton("Вернуть выбранное")
        self.undo_btn.clicked.connect(self._undo)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.reload)
        self.status = _muted("")
        bar = QHBoxLayout()
        bar.addWidget(self.undo_btn)
        bar.addWidget(self.refresh_btn)
        bar.addStretch()

        self.root.addLayout(bar)
        self.root.addWidget(self.view, 1)
        self.root.addWidget(self.status)
        self.reload()

    def reload(self) -> None:
        entries = list(reversed(self.journal.read_all()))[: self.prefs.journal_limit]
        self.model.set_items(entries)

    def _undo(self) -> None:
        idx = self.view.currentIndex()
        if not idx.isValid():
            self.status.setText("Выберите запись.")
            return
        entry = self.model.item(idx.row())
        if self.prefs.confirm_undo:
            answer = QMessageBox.question(
                self, "Вернуть файл", f"Вернуть {entry.dst} на место?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        ok = self.journal.undo(entry.id)
        self.status.setText("Файл возвращён на место." if ok else "Не удалось: файл уже перемещён или удалён.")
        self.reload()


class RulesPage(_Page):
    def __init__(self) -> None:
        super().__init__("Правила сортировки", "Галочка включает правило. Порядок сверху вниз.")
        self.rules = load_rules()
        self.model = RuleModel(self.rules)
        self.view = QListView()
        self.view.setModel(self.model)
        self.save_btn = QPushButton("Сохранить правила")
        self.save_btn.clicked.connect(self._save)
        self.status = _muted("")
        self.root.addWidget(self.view, 1)
        self.root.addWidget(self.save_btn)
        self.root.addWidget(self.status)

    def reload(self) -> None:
        pass

    def _save(self) -> None:
        save_rules(self.rules)
        self.status.setText("Правила сохранены.")


class SettingsPage(_Page):
    def __init__(self, settings: AppSettings, prefs: UiPrefs, on_prefs_changed) -> None:
        super().__init__("Настройки", "Изменения применяются после нажатия «Сохранить».")
        self.settings = settings
        self.prefs = prefs
        self.on_prefs_changed = on_prefs_changed

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)

        self.theme = QComboBox()
        self.theme.addItem("Серая (тёмная)", "graphite")
        self.theme.addItem("Светлая серая", "light")
        self.theme.setCurrentIndex(0 if prefs.theme == "graphite" else 1)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 16)
        self.font_size.setValue(prefs.font_size)

        self.compact = QCheckBox("Компактные списки")
        self.compact.setChecked(prefs.compact_lists)
        self.tooltips = QCheckBox("Подсказки при наведении")
        self.tooltips.setChecked(prefs.show_tooltips)
        self.confirm = QCheckBox("Спрашивать перед возвратом файла")
        self.confirm.setChecked(prefs.confirm_undo)

        self.default_section = QComboBox()
        for title, key in [("Захваты", "captures"), ("Журнал", "journal"),
                           ("Правила", "rules"), ("Настройки", "settings")]:
            self.default_section.addItem(title, key)
        self.default_section.setCurrentIndex(["captures", "journal", "rules", "settings"].index(prefs.default_section))

        self.history_limit = QSpinBox()
        self.history_limit.setRange(5, 100)
        self.history_limit.setValue(prefs.history_limit)
        self.journal_limit = QSpinBox()
        self.journal_limit.setRange(20, 2000)
        self.journal_limit.setValue(prefs.journal_limit)

        self.hotkey = QLineEdit(settings.grabber.hotkey)
        self.dry = QCheckBox("Только показывать план, без переносов")
        self.dry.setChecked(settings.organizer.dry_run)
        self.autostart = QCheckBox("Запускать вместе с Windows")
        self.autostart.setChecked(settings.autostart)
        self.excluded = QLineEdit("; ".join(settings.organizer.excluded_dirs))

        form.addRow("Тема:", self.theme)
        form.addRow("Размер шрифта:", self.font_size)
        form.addRow("", self.compact)
        form.addRow("", self.tooltips)
        form.addRow("", self.confirm)
        form.addRow("Открывать сначала:", self.default_section)
        form.addRow("Хранить захватов:", self.history_limit)
        form.addRow("Строк в журнале:", self.journal_limit)
        form.addRow("Горячая клавиша:", self.hotkey)
        form.addRow("", self.dry)
        form.addRow("", self.autostart)
        form.addRow("Не трогать папки:", self.excluded)

        self.error = _muted("")
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._save)
        self.reset_btn = QPushButton("Сбросить внешний вид")
        self.reset_btn.clicked.connect(self._reset_look)
        bar = QHBoxLayout()
        bar.addWidget(self.save_btn)
        bar.addWidget(self.reset_btn)
        bar.addStretch()

        self.root.addLayout(form)
        self.root.addWidget(_muted("Хоткей и автозапуск применятся после перезапуска."))
        self.root.addWidget(self.error)
        self.root.addLayout(bar)
        self.root.addStretch()

    def _reset_look(self) -> None:
        from core.prefs import UiPrefs as _U
        d = _U()
        self.theme.setCurrentIndex(0)
        self.font_size.setValue(d.font_size)
        self.compact.setChecked(d.compact_lists)
        self.tooltips.setChecked(d.show_tooltips)

    def _save(self) -> None:
        spec = self.hotkey.text().strip().lower()
        try:
            parse_hotkey(spec)
        except ValueError as e:
            self.error.setText(f"Хоткей: {e}")
            return

        self.prefs.theme = self.theme.currentData()
        self.prefs.font_size = self.font_size.value()
        self.prefs.compact_lists = self.compact.isChecked()
        self.prefs.show_tooltips = self.tooltips.isChecked()
        self.prefs.confirm_undo = self.confirm.isChecked()
        self.prefs.default_section = self.default_section.currentData()
        self.prefs.history_limit = self.history_limit.value()
        self.prefs.journal_limit = self.journal_limit.value()
        save_prefs(self.prefs)

        self.settings.grabber.hotkey = spec
        self.settings.organizer.dry_run = self.dry.isChecked()
        self.settings.organizer.excluded_dirs = [s.strip() for s in self.excluded.text().split(";") if s.strip()]
        self.settings.autostart = self.autostart.isChecked()
        set_autostart(self.settings.autostart)
        save_settings(self.settings)

        self.on_prefs_changed(self.prefs)
        self.error.setText("Сохранено. Тема и размер применены сразу.")
