from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from core.config import AppSettings, save_settings
from modules.organizer.rules_store import load_rules, save_rules
from win.hotkeys import parse_hotkey


class SettingsWindow(QDialog):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.setWindowTitle("AutoUtil: настройки")
        self.settings = settings
        self.rules = load_rules()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Правила сортировки:"))
        self.rule_boxes: list[QCheckBox] = []
        for rule in self.rules:
            box = QCheckBox(f"{rule.name} → {rule.target}")
            box.setChecked(rule.enabled)
            self.rule_boxes.append(box)
            layout.addWidget(box)

        self.dry = QCheckBox("Только показывать план (без переносов)")
        self.dry.setChecked(settings.organizer.dry_run)
        layout.addWidget(self.dry)

        layout.addWidget(QLabel("Горячая клавиша захвата:"))
        self.hotkey = QLineEdit(settings.grabber.hotkey)
        layout.addWidget(self.hotkey)

        layout.addWidget(QLabel("Не трогать папки (по одной в строке):"))
        self.excluded = QLineEdit("; ".join(settings.organizer.excluded_dirs))
        layout.addWidget(self.excluded)

        self.info_label = QLabel("Хоткей применится после перезапуска")
        layout.addWidget(self.info_label)

        self.error = QLabel("")
        layout.addWidget(self.error)

        buttons = QHBoxLayout()
        save = QPushButton("Сохранить")
        save.clicked.connect(self._save)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _save(self) -> None:
        try:
            parse_hotkey(self.hotkey.text().strip().lower())
        except ValueError as e:
            self.error.setText(f"Хоткей: {e}")
            return
        for rule, box in zip(self.rules, self.rule_boxes):
            rule.enabled = box.isChecked()
        save_rules(self.rules)
        self.settings.organizer.dry_run = self.dry.isChecked()
        self.settings.grabber.hotkey = self.hotkey.text().strip().lower()
        self.settings.organizer.excluded_dirs = [s.strip() for s in self.excluded.text().split(";") if s.strip()]
        save_settings(self.settings)
        self.accept()
