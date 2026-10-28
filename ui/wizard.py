from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QVBoxLayout, QWizard, QWizardPage

from core.config import AppSettings
from core.i18n import t
from win.autostart import set_autostart
from win.paths import downloads_dir


class FolderPage(QWizardPage):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setTitle(t("wizard.folder.title"))
        self.setSubTitle(t("wizard.folder.subtitle"))
        self.edit = QLineEdit(str(downloads_dir()))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("wizard.folder.label")))
        layout.addWidget(self.edit)
        self.settings = settings

    def validatePage(self) -> bool:
        self.settings.organizer.watch_dirs = [self.edit.text().strip()]
        return bool(self.edit.text().strip())


class OptionsPage(QWizardPage):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setTitle(t("wizard.options.title"))
        self.dry = QCheckBox(t("wizard.options.dry"))
        self.dry.setChecked(True)
        self.auto = QCheckBox(t("wizard.options.autostart"))
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
        self.setWindowTitle(t("wizard.title"))
        self.settings = settings
        self.addPage(FolderPage(settings))
        self.addPage(OptionsPage(settings))

    def accept(self) -> None:
        set_autostart(self.settings.autostart)
        self.settings.first_run = False
        super().accept()
