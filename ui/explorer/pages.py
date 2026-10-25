from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListView, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.config import AppSettings, save_settings
from core.journal import Journal
from core.prefs import UiPrefs, save_prefs
from modules.organizer.rules_store import load_rules, save_rules
from ui.explorer.models import JournalModel, RuleModel
from win.autostart import set_autostart


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
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._save)
        self.status = _muted("")
        self.root.addWidget(self.view, 1)
        self.root.addWidget(self.save_btn)
        self.root.addWidget(self.status)

    def reload(self) -> None:
        self.rules = load_rules()
        self.model.set_items(self.rules)

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

        sections = ["schema", "journal", "rules", "settings"]
        current = prefs.default_section if prefs.default_section in sections else "schema"
        self.default_section = QComboBox()
        for title, key in [("Схема", "schema"), ("Журнал", "journal"),
                           ("Правила", "rules"), ("Настройки", "settings")]:
            self.default_section.addItem(title, key)
        self.default_section.setCurrentIndex(sections.index(current))

        self.journal_limit = QSpinBox()
        self.journal_limit.setRange(20, 2000)
        self.journal_limit.setValue(prefs.journal_limit)

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
        form.addRow("Строк в журнале:", self.journal_limit)
        form.addRow("", self.dry)
        form.addRow("", self.autostart)
        form.addRow("Не трогать папки:", self.excluded)

        self.error = _muted("")
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._save)
        self.reset_btn = QPushButton("Сбросить внешний вид")
        self.reset_btn.clicked.connect(self._reset_look)
        bar = QHBoxLayout()
        bar.addWidget(self.save_btn)
        bar.addWidget(self.reset_btn)
        bar.addStretch()

        self.root.addLayout(form)
        self.root.addWidget(_muted("Автозапуск применится после перезапуска."))
        self.root.addWidget(self.error)
        self.root.addLayout(bar)
        self.root.addStretch()

    def _reset_look(self) -> None:
        d = UiPrefs()
        self.theme.setCurrentIndex(0)
        self.font_size.setValue(d.font_size)
        self.compact.setChecked(d.compact_lists)
        self.tooltips.setChecked(d.show_tooltips)

    def _save(self) -> None:
        self.prefs.theme = self.theme.currentData()
        self.prefs.font_size = self.font_size.value()
        self.prefs.compact_lists = self.compact.isChecked()
        self.prefs.show_tooltips = self.tooltips.isChecked()
        self.prefs.confirm_undo = self.confirm.isChecked()
        self.prefs.default_section = self.default_section.currentData()
        self.prefs.journal_limit = self.journal_limit.value()
        save_prefs(self.prefs)

        self.settings.organizer.dry_run = self.dry.isChecked()
        self.settings.organizer.excluded_dirs = [s.strip() for s in self.excluded.text().split(";") if s.strip()]
        self.settings.autostart = self.autostart.isChecked()
        set_autostart(self.settings.autostart)
        save_settings(self.settings)

        self.on_prefs_changed(self.prefs)
        self.error.setText("Сохранено. Тема и размер применены сразу.")
