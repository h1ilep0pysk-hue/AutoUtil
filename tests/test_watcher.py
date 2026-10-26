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
