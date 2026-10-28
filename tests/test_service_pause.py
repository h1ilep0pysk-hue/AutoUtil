"""Файлы, пришедшие в паузу, разбираются при возврате в активный режим. FIX

Watchdog событие приходит единожды: раньше _handle просто выходил, если режим
не активен, и файл навсегда выпадал из сортировки, пока не перезапустишь приложение.
"""
import time

import modules.organizer.service as service_mod
from core.config import OrganizerSettings
from core.state import Mode, state
from modules.organizer.rules import Rule
from modules.organizer.service import OrganizerService


class _Recorder:
    """Вместо Notifier: собирает заголовок и текст каждого уведомления."""

    def __init__(self) -> None:
        self.notes: list[str] = []

    def notify(self, notice) -> None:
        self.notes.append(f"{notice.title}: {notice.body}")


class _NoJournal:
    """При dry_run журнал не используется."""


def test_paused_files_are_sorted_on_resume(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "note.txt"
    f.write_bytes(b"x")
    home = tmp_path / "home"
    home.mkdir()
    rules = [Rule(name="Заметки", exts=[".txt"], target="ЗаметкиИзПаузы")]

    monkeypatch.setattr(service_mod, "load_rules", lambda: rules)
    monkeypatch.setattr(service_mod, "wait_stable", lambda p: True)
    monkeypatch.setattr(service_mod, "documents_dir", lambda: home)

    recorder = _Recorder()
    service = OrganizerService(OrganizerSettings(), _NoJournal(), recorder)

    try:
        state.set_mode(Mode.PAUSED)
        service.handle(f)
        service.handle(f)  # дубль события (created+moved) не должен удвоить файл
        assert service._paused_paths == {str(f)}
        assert f.exists()  # в паузу файлы не трогаем

        state.resume()  # → ModeChanged → буфер разбирается в фоне
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if any("note.txt" in n for n in recorder.notes):
                break
            time.sleep(0.05)
        assert service._paused_paths == set()
        planned = [n for n in recorder.notes if "note.txt" in n]
        assert planned, "файл, пришедший в паузу, не был разобран"
        assert "ЗаметкиИзПаузы" in planned[0]
    finally:
        state.resume()


def test_paused_duplicates_collapsed(tmp_path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"x")
    service = OrganizerService(OrganizerSettings(), _NoJournal(), _Recorder())
    try:
        state.set_mode(Mode.PAUSED)
        service.handle(f)
        service.handle(f)
        service.handle(f)
        assert len(service._paused_paths) == 1
    finally:
        state.resume()
