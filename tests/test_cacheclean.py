import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from modules.organizer import cacheclean
from modules.organizer.cacheclean import CacheTarget, run_clean


@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(cacheclean, "STATE_PATH", tmp_path / "cache_clean.json")


def test_clean_respects_protection_and_age(tmp_path, state):
    a = tmp_path / "cacheA"
    a.mkdir()
    (a / "old.bin").write_bytes(b"x" * 100)

    b = tmp_path / "cacheB"
    b.mkdir()
    prot = b / "opencode"
    prot.mkdir()
    (prot / "keep.txt").write_text("keep me", encoding="utf-8")
    (b / "junk.tmp").write_bytes(b"z" * 10)

    c = tmp_path / "cacheC"
    c.mkdir()
    fresh = c / "fresh.log"
    fresh.write_bytes(b"new")
    old = c / "old.log"
    old.write_bytes(b"o" * 60)
    stale = time.time() - 3 * 86400
    os.utime(old, (stale, stale))

    stats = run_clean(30, force=True, targets=[
        CacheTarget(a, "A"),
        CacheTarget(b, "B", 0, frozenset({"opencode"})),
        CacheTarget(c, "C", 1),
    ])
    assert stats is not None
    assert stats.files == 3
    assert stats.bytes == 100 + 10 + 60
    assert prot.exists() and (prot / "keep.txt").exists()
    assert not (a / "old.bin").exists()
    assert fresh.exists()  # min_age=1 день: свежий не трогаем
    assert not old.exists()


def test_no_clean_when_not_due(state):
    assert run_clean(30, force=True, targets=[]) is not None  # пишет свежий штамп
    assert run_clean(30) is None  # срок не подошёл
    assert not cacheclean.due(30)


def test_missing_target_is_skipped(state):
    stats = run_clean(30, force=True, targets=[CacheTarget(Path(r"Z:\нет-такой"), "ghost")])
    assert stats is not None and stats.files == 0


def test_due_math(state):
    # без файла штампа считаем, что чистка просрочена (last_run()=0)
    assert cacheclean.due(30) is True
