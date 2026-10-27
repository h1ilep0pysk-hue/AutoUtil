import time
from pathlib import Path

from modules.organizer.watcher import _Handler, wait_stable


def test_wait_stable_empty_file_is_quick(tmp_path):
    """Раньше пустой файл ждал весь таймаут (10 минут) и возвращал False."""
    p = tmp_path / "empty.log"
    p.write_bytes(b"")
    start = time.monotonic()
    assert wait_stable(p, polls=1, interval=0.01, timeout=5) is True
    assert time.monotonic() - start < 2


def test_wait_stable_missing_file(tmp_path):
    assert wait_stable(tmp_path / "nope.txt", polls=1, interval=0.01, timeout=1) is False


def test_wait_stable_regular_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"x" * 10)
    assert wait_stable(p, polls=1, interval=0.01, timeout=5) is True


class _Event:
    def __init__(self, path: str):
        self.src_path = path
        self.is_directory = False


def test_dedupe_same_path_in_window(tmp_path):
    calls = []
    handler = _Handler(lambda p: calls.append(p))
    target = tmp_path / "a.txt"
    handler._dispatch(target)
    handler._dispatch(target)  # дубль (on_created + on_moved) — должен отфильтроваться
    time.sleep(0.3)
    assert len(calls) == 1


def test_dedupe_different_paths_pass(tmp_path):
    calls = []
    handler = _Handler(lambda p: calls.append(p))
    handler._dispatch(tmp_path / "a.txt")
    handler._dispatch(tmp_path / "b.txt")
    time.sleep(0.3)
    assert len(calls) == 2


def test_dedupe_ignores_partial_downloads(tmp_path):
    calls = []
    handler = _Handler(lambda p: calls.append(p))
    handler._dispatch(tmp_path / "movie.crdownload")
    time.sleep(0.2)
    assert calls == []


def _slow_handler(calls: list, moved_name: str = ""):
    """Обработчик, который «отсортировал» файл (исчез с исходного пути)."""
    def on_file(p: Path) -> None:
        calls.append(p)
        if moved_name and p.name == moved_name:
            p.rename(p.with_name(moved_name + ".out"))
    return _Handler(on_file)


def test_same_name_recreated_after_move_is_processed(tmp_path):
    """Дедуп-окно 10 с не должно «съедать» новый файл с тем же именем,
    когда прежний уже уехал со своего места. FIX"""
    calls: list[Path] = []
    handler = _slow_handler(calls, moved_name="dup.bin")
    target = tmp_path / "dup.bin"
    target.write_bytes(b"x")
    handler._dispatch(target)
    time.sleep(0.3)  # обработчик успел перенести файл
    assert not target.exists()

    target.write_bytes(b"new copy")  # пользователь докачал то же имя снова
    handler._dispatch(target)  # < 10 с от первого события
    time.sleep(0.3)
    assert len(calls) == 2, "вновь созданный файл с тем же именем должен обработаться"


def test_same_name_while_still_here_is_deduped(tmp_path):
    """Пока файл ещё на месте (тот же экземпляр), дедуп работает как раньше."""
    calls: list[Path] = []
    handler = _slow_handler(calls)
    target = tmp_path / "same.bin"
    target.write_bytes(b"x")
    handler._dispatch(target)
    handler._dispatch(target)  # дубль события того же экземпляра
    time.sleep(0.3)
    assert len(calls) == 1
