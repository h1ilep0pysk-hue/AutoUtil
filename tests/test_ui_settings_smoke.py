"""Smoke-тест страницы «Настройки» в offscreen-режиме.

Регрессия: страница падала с
``AttributeError: 'SettingsPage' object has no attribute 'autostart_status'``
при сборке — подпись о состоянии автозапуска использовалась, но не создавалась,
а сам чекбокс автозапуска не попадал в форму.
"""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel  # noqa: E402

import ui.explorer.pages as pages_mod  # noqa: E402
from core.config import load_settings  # noqa: E402
from core.prefs import UiPrefs  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(monkeypatch):
    """Страница настроек с подменённым системным окружением.

    Реестр автозапуска и планировщик задач не трогаем: тесты не должны
    менять систему пользователя.
    """
    monkeypatch.setattr(pages_mod, "autostart_enabled", lambda: False)
    monkeypatch.setattr(pages_mod, "set_autostart", lambda enabled: True)
    monkeypatch.setattr(pages_mod.scheduler, "is_task_installed", lambda: False)
    monkeypatch.setattr(pages_mod.scheduler, "install_task", lambda: True)
    monkeypatch.setattr(pages_mod.scheduler, "remove_task", lambda: True)

    app = _app()
    widget = pages_mod.SettingsPage(load_settings(), UiPrefs(), lambda prefs: None)
    app.processEvents()
    yield widget
    widget.deleteLater()


def test_settings_page_constructs(page):
    """Страница собирается и содержит все виджеты, которые потом сохраняет."""
    assert isinstance(page.autostart, QCheckBox)
    assert isinstance(page.autostart_status, QLabel)
    assert page.autostart_status.text(), "подпись о состоянии не должна быть пустой"


def test_autostart_row_is_in_the_form(page):
    """Чекбокс автозапуска действительно показан, а не просто создан."""
    shown = page.findChildren(QCheckBox)
    assert page.autostart in shown, "чекбокс автозапуска не добавлен в форму"
    assert page.autostart_status in page.findChildren(QLabel)


def test_save_reports_autostart_state(page, monkeypatch):
    """После сохранения подпись отражает новое состояние автозапуска."""
    monkeypatch.setattr(pages_mod, "set_autostart", lambda enabled: True)

    page.autostart.setChecked(True)
    page._save()
    on_text = page.autostart_status.text()
    assert on_text

    page.autostart.setChecked(False)
    page._save()
    off_text = page.autostart_status.text()

    assert on_text != off_text, "подпись должна меняться вместе с состоянием"


def test_save_failure_is_shown(page, monkeypatch):
    """Ошибка автозапуска не теряется: пользователь видит текст в блоке ошибок."""
    monkeypatch.setattr(pages_mod, "set_autostart", lambda enabled: False)

    page.autostart.setChecked(True)
    page._save()

    assert page.error.text(), "о неудаче автозапуска нужно сообщить"
