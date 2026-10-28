"""Окно сухого прогона узла «Дубликаты».

Показывает группы одинаковых файлов: что останется (keep) и что уедет в
карантин (remove). Ничего не делает без явной галочки подтверждения.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from core.config import AppSettings, save_settings
from core.i18n import t
from modules.organizer.dedupe_groups import DupGroup
from modules.organizer.quarantine import move_to_quarantine

log = logging.getLogger("autoutil.ui.duplicates")

KEEP_COLOR = QColor("#d7f0d7")
REMOVE_COLOR = QColor("#f6d6d6")
MB = 1024 * 1024


class DuplicatesPreviewDialog(QDialog):
    """Groups view + CSV export + confirmed execution into quarantine."""

    def __init__(self, groups: list[DupGroup], rule_name: str,
                 settings: AppSettings | None = None, journal=None,
                 parent=None) -> None:
        super().__init__(parent)
        self.groups = groups
        self.rule_name = rule_name
        self.settings = settings
        self.journal = journal
        self.moved: list[Path] = []

        self.setWindowTitle(t("dup.preview.title"))
        self.resize(860, 560)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([
            t("dup.preview.file"), t("dup.preview.size"),
            t("dup.preview.mtime"), t("dup.preview.action"),
        ])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._populate()

        total = sum(len(g.remove) for g in groups)
        total_mb = sum(g.size for g in groups for _ in g.remove) / MB
        self.summary = QLabel(t("dup.preview.summary", n=total, size=f"{total_mb:.1f}"))

        self.confirm = QCheckBox(t("dup.preview.confirm"))
        self.confirm.toggled.connect(self._sync_run_button)

        self.export_btn = QPushButton(t("dup.preview.export"))
        self.export_btn.clicked.connect(self._export_csv)
        self.run_btn = QPushButton(t("dup.preview.run"))
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QPushButton(t("Отменить"))
        self.cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.export_btn)
        buttons.addStretch()
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.run_btn)

        root = QVBoxLayout(self)
        root.addWidget(self.tree, 1)
        root.addWidget(self.summary)
        root.addWidget(self.confirm)
        root.addLayout(buttons)

        self._sync_run_button()

    # --- построение дерева --------------------------------------------------
    def _populate(self) -> None:
        for group in self.groups:
            top = QTreeWidgetItem([
                t("dup.preview.group", digest=group.digest[:12], count=len(group.remove) + 1),
                f"{group.size / MB:.2f} {t('dup.preview.mb')}",
                "",
                "",
            ])
            top.setExpanded(True)
            self.tree.addTopLevelItem(top)
            for path, action in [(group.keep, "keep")] + [
                (p, "remove") for p in group.remove
            ]:
                child = QTreeWidgetItem([
                    str(path),
                    f"{group.size / MB:.2f}",
                    _mtime_text(path),
                    t("dup.preview.action_keep") if action == "keep"
                    else t("dup.preview.action_quarantine"),
                ])
                color = KEEP_COLOR if action == "keep" else REMOVE_COLOR
                for column in range(4):
                    child.setBackground(column, color)
                top.addChild(child)

    # --- действия -----------------------------------------------------------
    def _sync_run_button(self) -> None:
        self.run_btn.setEnabled(bool(self.confirm.isChecked()) and bool(self.groups))

    def _rows(self) -> list[tuple[str, str, str, int, str]]:
        rows = []
        for group in self.groups:
            for path, action in [(group.keep, "keep")] + [
                (p, "quarantine") for p in group.remove
            ]:
                rows.append((group.digest, str(path), action, group.size, _mtime_text(path)))
        return rows

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, t("dup.preview.export"), "duplicates.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["group_digest", "file", "action", "size", "mtime"])
            writer.writerows(self._rows())
        log.info("duplicates: CSV exported (%d rows)", len(self._rows()))

    def _run(self) -> None:
        if not self.confirm.isChecked():
            return
        if self.settings is not None:
            self.settings.organizer.duplicates_confirmed = True
            save_settings(self.settings)
        for group in self.groups:
            if self.journal is None:
                continue
            self.moved.extend(move_to_quarantine(group, self.journal, self.rule_name))
        self.accept()


def _mtime_text(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""
