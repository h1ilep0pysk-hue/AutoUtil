import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from core.config import AppSettings, save_settings
from core.i18n import set_language, t
from core.journal import Journal
from core.prefs import UiPrefs, save_prefs
from modules.organizer.preview import DEFAULT_OCR_LIMIT, RulePreview, preview_rule
from modules.organizer.rules import Rule
from modules.organizer.rules_store import load_rules, save_rules
from ui.explorer.models import JournalModel, RuleModel
from win import scheduler


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
        super().__init__(t("Журнал действий"), t("Все перемещения файлов. Можно вернуть любое."))
        self.journal = journal
        self.prefs = prefs
        self.model = JournalModel()
        self.view = QListView()
        self.view.setModel(self.model)

        self.undo_btn = QPushButton(t("Вернуть выбранное"))
        self.undo_btn.clicked.connect(self._undo)
        self.refresh_btn = QPushButton(t("Обновить"))
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
            self.status.setText(t("Выберите запись."))
            return
        entry = self.model.item(idx.row())
        if entry.kind == "bin":
            self.status.setText(t("Файл в корзине. Верни его из корзины вручную."))
            return
        if self.prefs.confirm_undo:
            answer = QMessageBox.question(
                self, t("Вернуть файл"), t("Вернуть {dst} на место?", dst=entry.dst)
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        ok = self.journal.undo(entry.id)
        self.status.setText(t("Файл возвращён на место.") if ok else t("Не удалось: файл уже перемещён или удалён."))
        self.reload()


class _PreviewWorker(QObject):
    """Считает предпросмотр в фоне: анализ папки может занять время."""
    done = Signal(object)

    def __init__(self, rule: Rule, folder: str) -> None:
        super().__init__()
        self.rule = rule
        self.folder = folder

    def run(self) -> None:
        from win.paths import documents_dir

        try:
            result = preview_rule(self.rule, Path(self.folder), documents_dir().parent)
        except Exception:
            import logging
            logging.getLogger("autoutil.ui").exception("Ошибка предпросмотра правила")
            result = RulePreview()
        self.done.emit(result)


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


class RulesPage(_Page):
    def __init__(self) -> None:
        super().__init__(t("Правила сортировки"), t("Галочка включает правило. Порядок сверху вниз."))
        self.rules = load_rules()
        self.model = RuleModel(self.rules)
        self.view = QListView()
        self.view.setModel(self.model)
        self.save_btn = QPushButton(t("Сохранить правила"))
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._save)
        self.status = _muted("")

        # --- предпросмотр правила -------------------------------------
        self.preview_folder = QLineEdit(_default_preview_folder())
        self.preview_browse = QPushButton("…")
        self.preview_browse.setFixedWidth(36)
        self.preview_browse.setToolTip(t("preview.pick"))
        self.preview_browse.clicked.connect(self._pick_preview_folder)
        self.preview_btn = QPushButton(t("preview.show"))
        self.preview_btn.clicked.connect(self._run_preview)
        prow = QHBoxLayout()
        prow.addWidget(QLabel(t("preview.folder")))
        prow.addWidget(self.preview_folder, 1)
        prow.addWidget(self.preview_browse)
        prow.addWidget(self.preview_btn)
        self.preview_list = QListWidget()
        self.preview_status = _muted("")
        self._thread: QThread | None = None
        self._worker: _PreviewWorker | None = None

        self.root.addWidget(self.view, 1)
        self.root.addLayout(prow)
        self.root.addWidget(self.preview_list, 1)
        self.root.addWidget(self.preview_status)
        self.root.addWidget(self.save_btn)
        self.root.addWidget(self.status)

    def reload(self) -> None:
        self.rules = load_rules()
        self.model.set_items(self.rules)

    def _save(self) -> None:
        save_rules(self.rules)
        self.status.setText(t("Правила сохранены."))

    # --- предпросмотр ---------------------------------------------------

    def _pick_preview_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("preview.pick"), self.preview_folder.text())
        if folder:
            self.preview_folder.setText(folder)

    def _run_preview(self) -> None:
        idx = self.view.currentIndex()
        if not idx.isValid():
            self.preview_status.setText(t("preview.select_rule"))
            return
        folder = Path(self.preview_folder.text().strip())
        if not folder.is_dir():
            self.preview_status.setText(t("preview.folder_missing", path=str(folder)))
            return
        rule = self.model.item(idx.row())
        self.preview_btn.setEnabled(False)
        self.preview_status.setText(t("preview.running"))
        self._thread = QThread(self)
        self._worker = _PreviewWorker(rule, str(folder))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._show_preview)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

    def _show_preview(self, result: RulePreview) -> None:
        self.preview_btn.setEnabled(True)
        self.preview_list.clear()
        if not result.matches:
            self.preview_status.setText(
                t("preview.empty", total=result.total_files)
            )
            return
        MAX_ROWS = 500
        for path, where in result.matches[:MAX_ROWS]:
            item = QListWidgetItem(f"{path.name}   →   {where}")
            item.setToolTip(str(path))
            self.preview_list.addItem(item)
        note = t("preview.truncated", n=MAX_ROWS) if len(result.matches) > MAX_ROWS else ""
        if result.ocr_capped:
            note += " " + t("preview.ocr_capped", n=DEFAULT_OCR_LIMIT)
        self.preview_status.setText(
            t("preview.result", hits=len(result.matches), total=result.total_files) + note
        )


class SettingsPage(_Page):
    def __init__(self, settings: AppSettings, prefs: UiPrefs, on_prefs_changed,
                 on_language_changed=None) -> None:
        super().__init__(t("Настройки"), t("Изменения применяются после нажатия «Сохранить»."))
        self.settings = settings
        self.prefs = prefs
        self.on_prefs_changed = on_prefs_changed
        self.on_language_changed = on_language_changed

        form = QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(12)

        self.theme = QComboBox()
        self.theme.addItem(t("Серая (тёмная)"), "graphite")
        self.theme.addItem(t("Светлая серая"), "light")
        self.theme.setCurrentIndex(0 if prefs.theme == "graphite" else 1)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 16)
        self.font_size.setValue(prefs.font_size)

        self.compact = QCheckBox(t("Компактные списки"))
        self.compact.setChecked(prefs.compact_lists)
        self.tooltips = QCheckBox(t("Подсказки при наведении"))
        self.tooltips.setChecked(prefs.show_tooltips)
        self.confirm = QCheckBox(t("Спрашивать перед возвратом файла"))
        self.confirm.setChecked(prefs.confirm_undo)

        sections = ["schema", "journal", "rules", "settings"]
        current = prefs.default_section if prefs.default_section in sections else "schema"
        self.default_section = QComboBox()
        for title, key in [(t("Схема"), "schema"), (t("Журнал"), "journal"),
                           (t("Правила"), "rules"), (t("Настройки"), "settings")]:
            self.default_section.addItem(title, key)
        self.default_section.setCurrentIndex(sections.index(current))

        self.journal_limit = QSpinBox()
        self.journal_limit.setRange(20, 2000)
        self.journal_limit.setValue(prefs.journal_limit)

        self.dry = QCheckBox(t("Только показывать план, без переносов"))
        self.dry.setChecked(settings.organizer.dry_run)
        # FIX: состояние автозапуска берём из реестра (источник правды),
        # а не из сохранённой конфигурации.
        self.autostart = QCheckBox(t("Запускать вместе с Windows"))
        self.autostart.setChecked(autostart_enabled())
        self.deferred_background = QCheckBox(t("settings.deferred_background"))
        self.deferred_background.setChecked(scheduler.is_task_installed())
        self.excluded = QLineEdit("; ".join(settings.organizer.excluded_dirs))

        form.addRow(t("Тема:"), self.theme)
        form.addRow(t("Размер шрифта:"), self.font_size)
        form.addRow("", self.compact)
        form.addRow("", self.tooltips)
        form.addRow("", self.confirm)
        form.addRow(t("Открывать сначала:"), self.default_section)
        form.addRow(t("Строк в журнале:"), self.journal_limit)
        form.addRow("", self.dry)
        form.addRow("", self.deferred_background)
        form.addRow(t("Не трогать папки:"), self.excluded)

        # --- отдельная плашка «Язык»: применяется сразу, без «Сохранить» ---
        lang_box = QFrame()
        lang_box.setObjectName("LangPlate")
        lang_lay = QHBoxLayout(lang_box)
        lang_lay.setContentsMargins(14, 10, 14, 10)
        lang_lay.setSpacing(14)
        lang_title = QLabel(t("settings.language"))
        lang_title.setObjectName("Heading")
        self.language = QComboBox()
        self.language.addItem("Русский", "ru")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(1 if prefs.language == "en" else 0)
        lang_lay.addWidget(lang_title)
        lang_lay.addWidget(self.language)
        lang_hint = _muted(t("settings.language.hint"))
        lang_hint.setWordWrap(True)
        lang_lay.addWidget(lang_hint, 1)
        self.language.currentIndexChanged.connect(self._apply_language)

        self.error = _muted("")
        self.save_btn = QPushButton(t("Сохранить"))
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._save)
        self.reset_btn = QPushButton(t("Сбросить внешний вид"))
        self.reset_btn.clicked.connect(self._reset_look)
        bar = QHBoxLayout()
        bar.addWidget(self.save_btn)
        bar.addWidget(self.reset_btn)
        bar.addStretch()

        self.root.addLayout(form)
        self.root.addWidget(lang_box)
        self.root.addWidget(self.autostart_status)
        self.root.addWidget(self.error)
        self.root.addLayout(bar)
        self.root.addStretch()

    def _apply_language(self, index: int = -1) -> None:
        """Смена языка сразу: сохранить выбор и пересобрать интерфейс."""
        lang = self.language.currentData()
        if not lang:
            return
        self.prefs.language = lang
        set_language(lang)
        save_prefs(self.prefs)
        if self.on_language_changed is not None:
            self.on_language_changed()

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
        # FIX: результат автозапуска показываем пользователю (раньше ошибка
        # терялась и настройка «не работала» молча).
        if not set_autostart(self.settings.autostart):
            hint = "%APPDATA%\\AutoUtil\\logs\\autoutil.log"
            self.error.setText(t("settings.autostart.fail", hint=hint))
        else:
            self.autostart_status.setText(
                t("settings.autostart.on" if self.settings.autostart else "settings.autostart.off")
            )
        # Deferred background task handling
        bg_enabled = self.deferred_background.isChecked()
        task_installed = scheduler.is_task_installed()
        if bg_enabled != task_installed:
            if bg_enabled:
                if not scheduler.install_task():
                    # roll back UI and inform user
                    self.deferred_background.setChecked(False)
                    self.error.setText(t("settings.deferred_install_fail"))
            else:
                if not scheduler.remove_task():
                    self.deferred_background.setChecked(True)
                    self.error.setText(t("settings.deferred_remove_fail"))


        self.on_prefs_changed(self.prefs)
        # FIX: явно сообщаем, какой режим сортировки теперь активен
        note = (t("settings.dry_note_on") if self.settings.organizer.dry_run
                else t("settings.dry_note_off"))
        self.error.setText(t("Сохранено. Тема и размер применены сразу.") + " " + note)
