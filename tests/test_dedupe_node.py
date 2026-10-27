"""Узел схемы «Дубликаты»: чистит копии файла, оставляет одну.

Пример пользователя: маска robloxinstaller* + расширение exe — из кучки
таких же инсталляторов остаётся ровно один, остальное в корзину (и оттуда
его можно вернуть из журнала).
"""
import shutil
from pathlib import Path

import pytest

import modules.organizer.service as service_mod
from core.config import OrganizerSettings
from core.journal import Journal
from core.schema import Edge, Node, Schema
from modules.organizer.analyzer import analyze
from modules.organizer.dedupe import has_same_copy
from modules.organizer.learning import Learned
from modules.organizer.planner import plan
from modules.organizer.rules import Rule
from modules.organizer.service import OrganizerService

CONTENT = b"roblox installer payload"


class Recorder:
    def __init__(self) -> None:
        self.notes: list[str] = []

    def notify(self, notice) -> None:
        self.notes.append(f"{notice.title}: {notice.body}")


def _dedupe_rule(**kw) -> Rule:
    return Rule(name="Дубликаты", exts=[".exe"], name_globs=["robloxinstaller*"], dedupe=True, **kw)


# --- ядро: поиск копии рядом ------------------------------------------------

def test_has_same_copy_finds_identical_sibling(tmp_path):
    a = tmp_path / "robloxinstaller.exe"
    b = tmp_path / "robloxinstaller (1).exe"
    a.write_bytes(CONTENT)
    b.write_bytes(CONTENT)
    assert has_same_copy(a, len(CONTENT)) is True


def test_has_same_copy_ignores_different_content_and_size(tmp_path):
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    (tmp_path / "другой.exe").write_bytes(b"different payload")
    (tmp_path / "короткий.exe").write_bytes(b"rob")
    assert has_same_copy(a, len(CONTENT)) is False


# --- компиляция схемы ---------------------------------------------------------

def test_schema_compiles_dedupe_node():
    schema = Schema(
        nodes=[
            Node(id="s", kind="source", title="Папка", params={"folder": "Загрузки"}),
            Node(id="f", kind="filter", title=".exe", params={"exts": [".exe"]}),
            Node(id="d", kind="dedupe", title="Дубликаты",
                 params={"exts": [".exe"], "name_glob": "robloxinstaller*"}),
        ],
        edges=[Edge(src="s", dst="f"), Edge(src="f", dst="d")],
    )
    rules = schema.to_rules()
    assert len(rules) == 1
    r = rules[0]
    assert r.dedupe is True
    assert r.exts == [".exe"]
    assert r.name_globs == ["robloxinstaller*"]
    assert r.target == ""  # цели нет — действие получает сам сервис


def test_dedupe_node_links_allowed():
    from core.schema import ALLOWED_LINKS

    assert ("source", "dedupe") in ALLOWED_LINKS
    assert ("filter", "dedupe") in ALLOWED_LINKS


# --- планировщик -------------------------------------------------------------

def test_plan_sends_duplicate_to_bin(tmp_path):
    a = tmp_path / "robloxinstaller.exe"
    (tmp_path / "robloxinstaller (1).exe").write_bytes(CONTENT)
    a.write_bytes(CONTENT)
    feats = analyze(a)
    move = plan(feats, [_dedupe_rule()], tmp_path, Learned())
    assert move is not None
    assert move.to_bin and move.dedupe
    assert move.src == a


def test_plan_keeps_unique_file(tmp_path):
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    assert plan(analyze(a), [_dedupe_rule()], tmp_path, Learned()) is None
    # не подходит под маску — тоже ничего
    other = tmp_path / "другой.exe"
    other.write_bytes(CONTENT)
    assert plan(analyze(other), [_dedupe_rule()], tmp_path, Learned()) is None


def test_plan_respects_delay_before_dedupe(tmp_path):
    a = tmp_path / "robloxinstaller.exe"
    (tmp_path / "robloxinstaller (1).exe").write_bytes(CONTENT)
    a.write_bytes(CONTENT)
    move = plan(analyze(a), [_dedupe_rule(delay_days=30)], tmp_path, Learned())
    assert move is not None and move.delay_days == 30 and move.to_bin


def test_masked_only_scope(tmp_path):
    """Одинаковый по содержимому, но посторонний по имени файл НЕ считается
    дубликатом: маска «robloxinstaller*» учитывает только такие же по имени."""
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    (tmp_path / "corsairinstaller.exe").write_bytes(CONTENT)  # тот же байт за байтом
    assert plan(analyze(a), [_dedupe_rule()], tmp_path, Learned()) is None


# --- авто-режим: без маски -----------------------------------------------------

AUTO_RULE = Rule(name="Дубликаты", dedupe=True)  # ни маски, ни расширений


def test_auto_finds_copy_with_rename_suffixes(tmp_path):
    """«(1)», «копия», «download» и лишние нули в имени не мешают увидеть дубль."""
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    for name in ("robloxinstaller (1).exe", "robloxinstaller 2.exe",
                 "robloxinstaller - копия.exe", "ROBLOXINSTALLER download.exe"):
        path = tmp_path / name
        path.write_bytes(CONTENT)
        assert plan(analyze(a), [AUTO_RULE], tmp_path, Learned()) is not None
        path.unlink()


def test_auto_rejects_unrelated_names(tmp_path):
    """Тот же размер и байт в байт, но имя совсем другое — не дубль."""
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    (tmp_path / "совсемдругаяпрограмма.exe").write_bytes(CONTENT)
    (tmp_path / "zzsetup.exe").write_bytes(CONTENT)
    assert plan(analyze(a), [AUTO_RULE], tmp_path, Learned()) is None


def test_auto_requires_same_extension(tmp_path):
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    (tmp_path / "robloxinstaller (1).zip").write_bytes(CONTENT)
    assert plan(analyze(a), [AUTO_RULE], tmp_path, Learned()) is None


def test_auto_respects_node_ext_filter(tmp_path):
    """Расширения в узле ограничивают и авто-режим: чужие файлы не в счёт."""
    rule = Rule(name="Дубликаты", exts=[".exe"], dedupe=True)
    a = tmp_path / "robloxinstaller.exe"
    a.write_bytes(CONTENT)
    (tmp_path / "robloxinstaller (1).zip").write_bytes(CONTENT)
    # под .exe копий нет — файл остаётся
    assert plan(analyze(a), [rule], tmp_path, Learned()) is None
    # .exe копия ловится
    (tmp_path / "robloxinstaller (2).exe").write_bytes(CONTENT)
    assert plan(analyze(a), [rule], tmp_path, Learned()) is not None


def test_auto_short_stem_no_false_positive(tmp_path):
    """Вырожденные имена («(1)», «1», «2») не «сливаются» между собой."""
    from modules.organizer.dedupe import _norm_stem

    assert _norm_stem("(1)") == ""
    (tmp_path / "1.exe").write_bytes(CONTENT)
    (tmp_path / "2.exe").write_bytes(CONTENT)
    assert plan(analyze(tmp_path / "1.exe"), [AUTO_RULE], tmp_path, Learned()) is None


# --- сервис сквозь весь конвейер ---------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    src = tmp_path / "Загрузки"
    src.mkdir()
    trash = tmp_path / "fake_bin"

    monkeypatch.setattr(service_mod, "documents_dir", lambda: home)
    monkeypatch.setattr(service_mod, "wait_stable", lambda p: True)
    monkeypatch.setattr(service_mod, "load_rules", lambda: [_dedupe_rule()])

    def fake_recycle(p: Path) -> bool:
        target = trash / p.name
        target.parent.mkdir(exist_ok=True)
        shutil.move(str(p), str(target))
        return True

    monkeypatch.setattr(service_mod, "recycle", fake_recycle)

    recorder = Recorder()
    service = OrganizerService(OrganizerSettings(dry_run=False), Journal(tmp_path / "j.jsonl"), recorder)
    service.learned = Learned(tmp_path / "learned.json")
    service.base = home

    def make(name: str) -> Path:
        p = src / name
        p.write_bytes(CONTENT)
        return p

    yield {"service": service, "recorder": recorder, "src": src, "home": home,
           "trash": trash, "make": make}


def test_service_cleans_copies_leaves_one(env):
    src: Path = env["src"]

    copies = [
        env["make"]("robloxinstaller.exe"),
        env["make"]("robloxinstaller (1).exe"),
        env["make"]("robloxinstaller (2).exe"),
    ]
    # посторонние файлы трогать нельзя и они не считаются дубликатами
    other = src / "скачано.exe"
    other.write_bytes(b"totally different thing")
    (src / "заметка.txt").write_bytes(b"keep me")

    for p in sorted(src.iterdir()):
        if p.is_file():
            env["service"].handle(p)

    # ровно одна копия инсталлятора осталась
    leftover = [p for p in src.iterdir()
                if p.name.startswith("robloxinstaller")]
    assert len(leftover) == 1
    assert leftover[0].read_bytes() == CONTENT

    # остальные две копии — в корзине
    binned = sorted(p.name for p in env["trash"].iterdir())
    assert len(binned) == 2
    assert all("robloxinstaller" in n for n in binned)
    for name in ("robloxinstaller (1).exe", "robloxinstaller (2).exe"):
        assert name in binned

    # постороннее не тронуто
    assert other.exists()
    assert (src / "заметка.txt").exists()

    # журнал: две записи «в корзину» с правилом дубликатов — восстановимо
    bins = [e for e in env["service"].journal.read_all() if e.kind == "bin"]
    assert len(bins) == 2 and all(b.rule == "Дубликаты" for b in bins)

    # уведомление объясняет, что копия осталась
    dedup_notes = [n for n in env["recorder"].notes if "Дубликат" in n]
    assert len(dedup_notes) == 2


def test_service_auto_mode_cleans_copies(env, tmp_path, monkeypatch):
    """Пустой узел «Дубликаты» без маски сам находит копии по похожему имени."""
    src: Path = env["src"]
    monkeypatch.setattr(service_mod, "load_rules", lambda: [AUTO_RULE])

    for name in ("setup game.exe", "setup game (1).exe", "setup game download.exe"):
        env["make"](name)
    unique = src / "удалённых.exe"  # совсем другое имя
    unique.write_bytes(CONTENT)

    for p in sorted(src.iterdir()):
        if p.is_file():
            env["service"].handle(p)

    leftover = [p for p in src.iterdir()
                if p.name.startswith("setup game")]
    assert len(leftover) == 1
    binned = sorted(p.name for p in env["trash"].iterdir() if "setup game" in p.name)
    assert len(binned) == 2
    assert unique.exists()  # чужое имя не приплели: не дубль


def test_service_catches_duplicate_arriving_later(env):
    src: Path = env["src"]
    first = env["make"]("robloxinstaller.exe")
    env["service"].handle(first)
    assert first.exists()  # копий нет — файл остался

    late = src / "robloxinstaller (копия).exe"
    late.write_bytes(CONTENT)
    env["service"].handle(late)

    assert not late.exists()
    assert first.exists()  # оригинал на месте
    assert any("robloxinstaller (копия).exe" == p.name for p in env["trash"].iterdir())


def test_dry_run_only_notifies(env, tmp_path, monkeypatch):
    home = tmp_path / "home2"
    home.mkdir()
    src: Path = env["src"]
    monkeypatch.setattr(service_mod, "documents_dir", lambda: home)
    recorder2 = Recorder()
    svc = OrganizerService(OrganizerSettings(dry_run=True), Journal(tmp_path / "j2.jsonl"), recorder2)
    svc.learned = Learned(tmp_path / "learned2.json")
    svc.base = home
    a = src / "robloxinstaller.exe"
    b = src / "robloxinstaller (1).exe"
    a.write_bytes(CONTENT)
    b.write_bytes(CONTENT)
    svc.handle(a)
    svc.handle(b)
    # файлы на месте — это только план
    assert a.exists() and b.exists()
    assert recorder2.notes  # уведомления-планы приходят
