from core.i18n import t
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.i18n import LANGUAGES, t


class LanguageDialog(QDialog):
    """Shown once on first launch. Closing it without a choice falls back to English."""

    def __init__(self) -> None:
        super().__init__()
        self.choice = "en"
        self.setWindowTitle(t("lang.title"))
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        prompt = QLabel(t("lang.prompt"))
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)

        buttons = QHBoxLayout()
        for code, label in LANGUAGES.items():
            btn = QPushButton(label)
            btn.setMinimumWidth(140)
            btn.clicked.connect(lambda _=False, c=code: self._choose(c))
            buttons.addWidget(btn)

        layout = QVBoxLayout(self)
        layout.addWidget(prompt)
        layout.addLayout(buttons)

    def _choose(self, code: str) -> None:
        self.choice = code
        self.accept()
