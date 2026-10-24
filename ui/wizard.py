from PySide6.QtWidgets import (
    QCheckBox, QLabel, QLineEdit, QVBoxLayout, QWizard, QWizardPage,
)

from core.config import AppSettings
from win.autostart import set_autostart
from win.paths import downloads_dir
from win.hotkeys import parse_hotkey


class FolderPage(QWizardPage):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setTitle("Папка для отслеживания")
        self.setSubTitle("AutoUtil будет следить за этой папкой и раскладывать новые файлы.")
        self.edit = QLineEdit(str(downloads_dir()))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Путь к папке:"))
        layout.addWidget(self.edit)
        self.settings = settings

    def validatePage(self) -> bool:
        self.settings.organizer.watch_dirs = [self.edit.text().strip()]
        return bool(self.edit.text().strip())


class HotkeyPage(QWizardPage):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setTitle("Горячая клавиша захвата текста")
        self.setSubTitle("Например: ctrl+shift+o")
        self.edit = QLineEdit(settings.grabber.hotkey)
        layout = QVBoxLayout(self)
        layout.addWidget(self.edit)
        self.settings = settings

    def validatePage(self) -> bool:
        spec = self.edit.text().strip().lower()
        try:
            parse_hotkey(spec)
        except ValueError:
            return False
        self.settings.grabber.hotkey = spec
        return True


class OptionsPage(QWizardPage):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setTitle("Настройки")
        self.dry = QCheckBox("Первые 7 дней только показывать план, без переносов (рекомендуется)")
        self.dry.setChecked(True)
        self.auto = QCheckBox("Запускать вместе с Windows")
        self.auto.setChecked(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.dry)
        layout.addWidget(self.auto)
        self.settings = settings

    def validatePage(self) -> bool:
        self.settings.organizer.dry_run = self.dry.isChecked()
        self.settings.autostart = self.auto.isChecked()
        return True


class SetupWizard(QWizard):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setWindowTitle("AutoUtil: первый запуск")
        self.settings = settings
        self.addPage(FolderPage(settings))
        self.addPage(HotkeyPage(settings))
        self.addPage(OptionsPage(settings))

    def accept(self) -> None:
        set_autostart(self.settings.autostart)
        self.settings.first_run = False
        super().accept()
