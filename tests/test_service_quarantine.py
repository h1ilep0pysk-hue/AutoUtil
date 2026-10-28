"""Автоматический путь узла «Дубликаты»: карантин вместо корзины.

Сервис получает событие на один файл, но действует над всей группой:
- файл-keep остаётся на месте;
- копии уходят в карантин (а не в корзину), с записью журнала «done»;
- если keep изменился между планированием и переносом — не двигаем ничего;
- правила без dedupe по-прежнему работают через корзину.
"""
import os
import shutil
from pathlib import Path

import pytest

import modules.organizer.quarantine as quarantine_mod
import modules.organizer.service as service_mod
from core import config
from core.config import OrganizerSettings
from core.events import FileMoved, FileTrashed, bus
from core.journal import Journal
from modules.organizer.learning import Learned
from modules.organizer.rules import Rule
from modules.organizer.service import OrganizerService

CONTENT = b"duplicate payload"


class Recorder:
    def __init__(self) -> None:
        self.notes: list[str] = []

    def notify(self, notice) -> None:
        self.notes.append(f"{notice.title}: {notice.body}")


def _dedupe_rule() -> Rule:
    return Rule(name="Дубликаты", exts=[".exe"], name_globs=["dup*"], dedupe=True)


def _quarantine_files() -> list[Path]:
    """Файлы в <APP_DIR>/quarantine/<дата>/* — вне зависимости от даты."""
    root = config.APP_DIR / "quarantine"
    if not root.is_dir():
        return []
    return sorted(
        p for folder in root.iterdir() if folder.is_dir() for p in folder.iterdir()
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    src = tmp_path / "Загрузки"
    src.mkdir()
    trash = tmp_path / "fake_bin"

    monkeypatch.setattr(service_mod, "documents_dir", lambda: home)
    monkeypatch.setattr(service_mod, "wait_stable", lambda p: True)

    def fake_recycle(p: Path) -> bool:
        trash.mkdir(exist_ok=True)
        shutil.move(str(p), str(trash / p.name))
        return True

    monkeypatch.setattr(service_mod, "recycle", fake_recycle)

    def make(name: str, content: bytes = CONTENT, mtime: float | None = None) -> Path:
        p = src / name
        p.write_bytes(content)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    recorder = Recorder()

    def build(rules: list[Rule], *, confirmed: bool = True, dry_run: bool = False):
        monkeypatch.setattr(service_mod, "load_rules", lambda: rules)
        svc = OrganizerService(
            OrganizerSettings(dry_run=dry_run, duplicates_confirmed=confirmed),
            Journal(tmp_path / "journal.jsonl"), recorder,
        )
        svc.learned = Learned(tmp_path / "learned.json")
        svc.base = home
        return svc

    yield {"src": src, "home": home, "trash": trash, "make": make,
           "recorder": recorder, "build": build}


# --- keep остаётся -----------------------------------------------------------

def test_auto_keep_file_stays(env):
    """Файл, выбранный как keep, не трогается — даже когда он же и триггер."""
    keep = env["make"]("dup original.exe", mtime=2_000_000)
    env["make"]("dup copy.exe", mtime=1_000_000)

    svc = env["build"]([_dedupe_rule()])
    svc.handle(keep)

    assert keep.exists(), "keep должен остаться на месте"
    assert keep.read_bytes() == CONTENT
    # второй файл группы при этом ушёл в карантин — группа обработана целиком
    assert [p.name for p in _quarantine_files()] == ["dup copy.exe"]


# --- копия уходит в карантин -------------------------------------------------

def test_auto_remove_goes_to_quarantine(env):
    """Копия не удаляется: она лежит в карантине, в журнале — done."""
    keep = env["make"]("dup original.exe", mtime=2_000_000)
    copy = env["make"]("dup copy.exe", mtime=1_000_000)

    moved: list[FileMoved] = []
    bus.subscribe(FileMoved, moved.append)
    try:
        svc = env["build"]([_dedupe_rule()])
        svc.handle(copy)
    finally:
        bus.unsubscribe(FileMoved, moved.append)

    assert not copy.exists(), "копия должна уйти из исходной папки"
    assert keep.exists()

    held = _quarantine_files()
    assert [p.name for p in held] == ["dup copy.exe"]
    assert held[0].read_bytes() == CONTENT

    rows = svc.journal.db.find_moves()
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "move"
    assert row.status == "done"
    assert row.rule_id == "Дубликаты"
    assert Path(row.src) == copy
    assert Path(row.dst) == held[0]

    # событие несёт исходный путь, а не путь триггера
    assert [e.src for e in moved] == [str(copy)]
    assert not env["trash"].exists(), "корзина не используется"


# --- keep изменился: группа отменяется ---------------------------------------

def test_auto_keep_changed_aborts(env, monkeypatch):
    """Если keep изменился между планированием и переносом — не двигаем ничего."""
    keep = env["make"]("dup original.exe", mtime=2_000_000)
    copy = env["make"]("dup copy.exe", mtime=1_000_000)

    # Сервис пересчитывает группу сам, поэтому подменяем именно проверку
    # валидности keep — ту, что стоит между записью в журнал и перемещением.
    monkeypatch.setattr(quarantine_mod, "keep_still_valid", lambda group: False)

    svc = env["build"]([_dedupe_rule()])
    svc.handle(copy)

    assert copy.exists(), "при изменившемся keep копию не трогаем"
    assert keep.exists()
    assert _quarantine_files() == []

    rows = svc.journal.db.find_moves()
    assert [r.status for r in rows] == ["failed"]
    assert not env["trash"].exists()


# --- обычное правило «В корзину» не изменилось --------------------------------

def test_non_dedupe_rule_still_uses_bin(env):
    """Правило без dedupe по-прежнему отправляет файл в корзину, не в карантин."""
    # .tmp игнорируется watcher'ом целиком (IGNORED_SUFFIXES), берём .bak
    junk = env["make"]("dump.bak", content=b"junk", mtime=1_000_000)

    rule = Rule(name="Мусор", exts=[".bak"], to_bin=True)

    trashed: list[FileTrashed] = []
    bus.subscribe(FileTrashed, trashed.append)
    try:
        svc = env["build"]([rule])
        svc.handle(junk)
    finally:
        bus.unsubscribe(FileTrashed, trashed.append)

    assert not junk.exists()
    assert (env["trash"] / "dump.bak").exists(), "файл должен быть в корзине"
    assert _quarantine_files() == [], "карантин — только для дубликатов"
    assert [e.src for e in trashed] == [str(junk)]

    rows = svc.journal.db.find_moves()
    assert [r.action for r in rows] == ["bin"]
