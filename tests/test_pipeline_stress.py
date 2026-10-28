"""Большой конвейерный тест: 20+ файлов, 12 правил, реальные переносы.

Прогоняет каждый файл через полный цикл обработки сервиса (как это делает
watchdog, только без живого наблюдателя) и проверяет, что:

- каждый файл, подходящий под правила, уходит ровно в свою папку;
- «Спросить» и «Через N дней» не переносят файл, а кладут в очереди;
- корзина уезжает в фейковую корзину и попадает в журнал;
- дубликат не затирается, источник остаётся на месте, а новая копия
  засчитывается рядом с суффиксом;
- временные, скрытые, системные файлы и файлы без правила не двигаются;
- повторный прогон тех же путей (дубль события) ничего не ломает и не плодит
  двойных записей в «Спросить»;
- файл, залоченный в момент события, всё же доезжает до цели (retry). FIX.

Все прошлые ошибки «файл иногда не переносится» были тихими — этот тест
матрицей ловит потерю сразу.
"""
import os
import shutil
import time
from datetime import date, datetime
from pathlib import Path

import pytest

import modules.organizer.service as service_mod
from core.config import OrganizerSettings
from core.deferred import DeferredStore
from core.journal import Journal
from core.journal_db import JournalDB
from core.pending import PendingStore
from core.state import state
from modules.organizer.learning import Learned
from modules.organizer.rules import Rule
from modules.organizer.service import OrganizerService

YEAR = datetime.now().year
TODAY = date.today().strftime("%Y-%m-%d")


class Recorder:
    def __init__(self) -> None:
        self.notes: list[str] = []

    def notify(self, notice) -> None:
        self.notes.append(f"{notice.title}: {notice.body}")


def _service(tmp_path: Path, home: Path, monkeypatch,
             settings: OrganizerSettings | None = None) -> tuple[OrganizerService, Recorder]:
    """Сервис со всеми хранилищами в tmp: журнал, pending, deferred, learned."""
    if monkeypatch is not None:
        monkeypatch.setattr(service_mod, "documents_dir", lambda: home)

    recorder = Recorder()
    service = OrganizerService(
        settings or OrganizerSettings(),
        Journal(tmp_path / "journal.jsonl"),
        recorder,
    )
    service.pending = PendingStore(tmp_path / "pending.json")
    service.deferred = DeferredStore(JournalDB(tmp_path / "journal.sqlite"))
    service.learned = Learned(tmp_path / "learned.json")
    service.base = home
    return service, recorder


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Матрица: 12 правил, десятки файлов, реальные переносы (dry_run off)."""
    home = tmp_path / "home"
    home.mkdir()
    src = tmp_path / "src"
    src.mkdir()

    rules = [
        Rule(name="Чеки", exts=[".pdf"], name_globs=["check_*"], target="Чеки/{year}"),
        Rule(name="PDF-доки", exts=[".pdf"], target="Документы/{year}"),
        Rule(name="Фото", exts=[".jpg", ".jpeg"], target="Изображения"),
        Rule(name="Скриншоты", exts=[".png"], target="Изображения/Скрины"),
        Rule(name="Документы", exts=[".docx", ".xlsx", ".pptx", ".txt"], target="Доки/{year}"),
        Rule(name="Инсталлы", exts=[".exe", ".msi"], target="Установщики"),
        Rule(name="Кино", exts=[".mp4"], min_mb=1, target="Видео"),
        Rule(name="Логи-старые", exts=[".log"], min_age_days=7, to_bin=True),
        Rule(name="Архивы позже", exts=[".zip"], delay_days=30, target="Архивы"),
        Rule(name="Спросить-архив", exts=[".rar"], ask=True, target="Спрошено"),
        Rule(name="Музыка", exts=[".mp3", ".wav"], target="Музыка"),
        Rule(name="Таблица+имя", exts=[".csv"], rename="{name}_{date}.{ext}", target="Таблы/{year}"),
    ]
    monkeypatch.setattr(service_mod, "documents_dir", lambda: home)
    monkeypatch.setattr(service_mod, "wait_stable", lambda p: True)
    monkeypatch.setattr(service_mod, "load_rules", lambda: rules)

    def fake_recycle(p: Path) -> bool:
        target = home / ".trash" / p.name
        target.parent.mkdir(exist_ok=True)
        shutil.move(str(p), str(target))
        return True

    monkeypatch.setattr(service_mod, "recycle", fake_recycle)

    settings = OrganizerSettings(
        dry_run=False,
        watch_dirs=[str(src)],
        excluded_dirs=[str(src / "НетТрогать")],
    )
    service, recorder = _service(tmp_path, home, monkeypatch, settings)

    def make(name: str, size: int = 3) -> Path:
        p = src / name
        # Разное содержимое у каждого файла — иначе find_duplicate примет
        # однофамильцев за дубликаты и не перенесёт их. FIX
        p.write_bytes((f"[{name}] ".encode("utf-8")) * 4)
        return p

    reality: dict[str, Path] = {}
    for name in (
        "check_иван.pdf", "check_июнь.pdf",
        "договор.pdf", "dup.pdf",
        "IMG_2222.jpg", "img_receipt.jpeg",
        "shot.png", "screenshot_2026.png",
        "акт.docx", "смета.xlsx", "прочее.pptx", "заметка.txt",
        "setup.exe", "программа.msi",
        "movie_small.mp4", "movie_big.mp4",
        "old_error.log", "fresh.log",
        "backup.zip", "data.zip",
        "проект.rar",
        "song.mp3", "гимн.wav",
        "склад.csv",
    ):
        reality[name] = make(name)

    # большой mp4 проходит min_mb=1, маленький нет
    reality["movie_big.mp4"].write_bytes(b"m" * (1024 * 1024 + 17))

    # старый лог (9 дней) — под корзину
    old = datetime.now().timestamp() - 9 * 86400
    os.utime(reality["old_error.log"], (old, old))

    # дубликат уже живёт в месте назначения: то же имя, размер и содержимое
    dst_dir = home / "Документы" / str(YEAR)
    dst_dir.mkdir(parents=True, exist_ok=True)
    (dst_dir / "dup.pdf").write_bytes(reality["dup.pdf"].read_bytes())
    # что система не должна тронуть
    keep: list[Path] = [
        make("movie.crdownload"),
        make("scratch.tmp"),
        make("~$акт.docx"),
        make(".конфиг.txt"),
        make("странник.xyz"),
        make("fresh.log"),
        reality["movie_small.mp4"],
    ]
    nested = src / "Папка2" / "внутри.txt"
    nested.parent.mkdir(exist_ok=True)
    nested.write_bytes(b"z")
    keep.append(nested)
    excluded = src / "НетТрогать" / "секрет.docx"
    excluded.parent.mkdir(exist_ok=True)
    excluded.write_bytes(b"s")
    keep.append(excluded)

    yield {
        "service": service, "recorder": recorder, "src": src, "home": home,
        "rules": rules, "reality": reality, "keep": keep, "dst_dir": dst_dir,
    }


def test_pipeline_moves_every_relevant_file(env):
    svc: OrganizerService = env["service"]
    src: Path = env["src"]
    home: Path = env["home"]
    dst_dir = env["dst_dir"]

    top = sorted(p for p in src.iterdir() if p.is_file())
    assert len(top) >= 20, "матрица неожиданно сжалась"
    for p in top:
        svc.handle(p)
    assert svc._retry == set(), "на чистой потоке ничего не должно висеть в retry"

    # --- все файлы, которыми должны уехать -------------------------------------------------
    expected = {
        "check_иван.pdf": home / "Чеки" / str(YEAR),
        "check_июнь.pdf": home / "Чеки" / str(YEAR),
        "договор.pdf": home / "Документы" / str(YEAR),
        "IMG_2222.jpg": home / "Изображения",
        "img_receipt.jpeg": home / "Изображения",
        "shot.png": home / "Изображения" / "Скрины",
        "screenshot_2026.png": home / "Изображения" / "Скрины",
        "акт.docx": home / "Доки" / str(YEAR),
        "смета.xlsx": home / "Доки" / str(YEAR),
        "прочее.pptx": home / "Доки" / str(YEAR),
        "заметка.txt": home / "Доки" / str(YEAR),
        "setup.exe": home / "Установщики",
        "программа.msi": home / "Установщики",
        "movie_big.mp4": home / "Видео",
        "song.mp3": home / "Музыка",
        "гимн.wav": home / "Музыка",
        f"склад_{TODAY}.csv": home / "Таблы" / str(YEAR),  # переименование по шаблону
    }
    for name, folder in expected.items():
        assert (folder / name).exists(), f"{name} не доехал до {folder}"

    # --- корзина ---------------------------------------------------------------------------
    assert (home / ".trash" / "old_error.log").exists()
    bin_entries = [e for e in svc.journal.read_all() if e.kind == "bin"]
    assert len(bin_entries) == 1 and bin_entries[0].rule == "Логи-старые"

    # --- «Спросить»: файл на месте, запись в pending ровно одна ---------------------------
    assert (src / "проект.rar").exists()
    pending = svc.pending.all_items()
    assert len(pending) == 1 and pending[0].rule == "Спросить-архив"

    # --- «Через N дней»: оба архива на месте и отложены -----------------------------------
    for name in ("backup.zip", "data.zip"):
        assert (src / name).exists()
    deferred = svc.deferred.all_items()
    assert len(deferred) == 2
    assert all(i.rule == "Архивы позже" and i.days == 30 for i in deferred)

    # --- дубликат: источник остался, цель не затерта ---------------------------------------
    assert (src / "dup.pdf").exists()
    dup_content = (dst_dir / "dup.pdf").read_bytes()
    assert dup_content.startswith(b"[dup.pdf]"), "содержимое оригинала должно сохраниться"

    # --- не трогать ------------------------------------------------------------------------
    for path in env["keep"]:
        assert path.exists(), f"{path} не должен был тронуться"

    # уведомления по дубликату и о планах есть
    assert any("dup" in n.lower() for n in env["recorder"].notes)

    # --- вторая волна (дубль событий watchdog): ничего не ломается -------------------------
    changed = src / "dup.pdf"
    changed.write_bytes(b"changed-content")  # теперь это не дубликат: уедет с суффиксом
    svc.handle(changed)
    variants = sorted(dst_dir.glob("dup*.pdf"))
    assert len(variants) == 2, "новый файл с тем же именем получает суффикс"

    for p in sorted(src.glob("*")):
        if p.is_file():
            svc.handle(p)  # задвоение событий, паузы и просто тряска
    assert svc._retry == set()

    pending = svc.pending.all_items()
    assert len(pending) == 1, "повтор «Спросить» на тот же файл плодит записи. FIX"
    assert len(svc.deferred.all_items()) == 2, "повторы архивов задваивают отложенные. FIX"

    state.resume()


def test_retry_rescues_locked_file(tmp_path, monkeypatch):
    """Регрессия бага «иногда не видит файл»: залоченный в момент события
    файл всё равно должен доехать до цели. FIX"""
    home = tmp_path / "home"
    home.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    f = src / "залочен.txt"
    f.write_bytes(b"x")

    monkeypatch.setattr(service_mod, "load_rules",
                        lambda: [Rule(name="Заметки", exts=[".txt"], target="Заметки")])
    monkeypatch.setattr(service_mod, "RETRY_INTERVAL_SECONDS", 0.02)

    calls = {"n": 0}

    def flaky_wait(p):
        calls["n"] += 1
        return calls["n"] > 2  # первые два раза «файл ещё не устоялся»

    monkeypatch.setattr(service_mod, "wait_stable", flaky_wait)

    service, _ = _service(tmp_path, home, monkeypatch,
                          OrganizerSettings(dry_run=False))

    service.handle(f)
    assert f.exists() and not (home / "Заметки" / f.name).exists()
    assert str(f) in service._retry

    service._start_retry()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (home / "Заметки" / f.name).exists():
                break
            time.sleep(0.02)
        assert (home / "Заметки" / "залочен.txt").exists(), "retry не спас залоченный файл"
        assert str(f) not in service._retry
    finally:
        service._stop_retry()


def test_retry_forgets_ghost(tmp_path):
    """Путь из очереди, чей файл исчез, выметается при проходе."""
    home = tmp_path / "home"
    home.mkdir()
    service, _ = _service(tmp_path, home, None)

    service._retry.add(str(tmp_path / "исчезнувший.txt"))
    service._pump_retries()
    assert service._retry == set()


def test_retry_thread_starts_and_stops(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    service, _ = _service(tmp_path, home, None)

    assert service._retry_thread is None
    service._start_retry()
    assert service._retry_thread is not None
    time.sleep(0.05)  # пару тиков: пустая очередь не роняет поток
    service._stop_retry()
    assert service._retry_thread is None
