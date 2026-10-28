"""Группировка дубликатов: детерминированный выбор keep и валидация."""
import os
from pathlib import Path

import pytest

import modules.organizer.dedupe_groups as dg
from core.i18n import t
from modules.organizer.dedupe_groups import DupGroup, group_duplicates, keep_still_valid
from modules.organizer.preview import preview_rule
from modules.organizer.rules import Rule

CONTENT = b"identical payload"


def _rule(**kw) -> Rule:
    return Rule(name="Дубликаты", exts=[".txt"], name_globs=["dup*"], dedupe=True, **kw)


def _make(folder: Path, name: str, content: bytes = CONTENT, mtime: float | None = None) -> Path:
    p = folder / name
    p.write_bytes(content)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def test_keep_newest_by_mtime(tmp_path):
    a = _make(tmp_path, "dupa.txt", mtime=1_000_000)
    b = _make(tmp_path, "dupb.txt", mtime=2_000_000)
    c = _make(tmp_path, "dupc.txt", mtime=3_000_000)

    groups = group_duplicates(tmp_path, _rule())

    assert len(groups) == 1
    assert groups[0].keep == c
    assert set(groups[0].remove) == {a, b}
    assert groups[0].size == len(CONTENT)


def test_tie_prefers_shorter_path(tmp_path):
    short = _make(tmp_path, "dupa.txt", mtime=5_000_000)
    long = _make(tmp_path, "dupa_very_long_name.txt", mtime=5_000_000)

    groups = group_duplicates(tmp_path, _rule())

    assert len(groups) == 1
    assert groups[0].keep == short
    assert groups[0].remove == [long]


def test_tie_then_alphabetical(tmp_path):
    # одинаковый mtime и одинаковая длина пути: «dupa.txt» < «dupb.txt»
    a = _make(tmp_path, "dupa.txt", mtime=5_000_000)
    b = _make(tmp_path, "dupb.txt", mtime=5_000_000)
    assert len(str(a)) == len(str(b))

    groups = group_duplicates(tmp_path, _rule())

    assert len(groups) == 1
    assert groups[0].keep == a
    assert groups[0].remove == [b]


def test_no_group_for_unique_file(tmp_path):
    _make(tmp_path, "dupa.txt")
    assert group_duplicates(tmp_path, _rule()) == []


def test_hash_computed_once_per_file(tmp_path, monkeypatch):
    calls = {"n": 0}
    real = dg.sha256_full

    def counting(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(dg, "sha256_full", counting)
    for name in ("dupa.txt", "dupb.txt", "dupc.txt"):
        _make(tmp_path, name)

    groups = group_duplicates(tmp_path, _rule())

    assert len(groups) == 1
    assert calls["n"] <= 3, f"хеш считался {calls['n']} раз(а) на 3 файла"


def test_keep_still_valid_detects_change(tmp_path):
    _make(tmp_path, "dupa.txt")
    _make(tmp_path, "dupb.txt")
    group = group_duplicates(tmp_path, _rule())[0]
    assert keep_still_valid(group) is True

    group.keep.write_bytes(b"changed payload!")  # другой размер и содержимое
    assert keep_still_valid(group) is False


def test_auto_mode_does_not_group_across_extensions(tmp_path):
    """Авто-режим не склеивает одинаковые байты с разными расширениями.

    То же правило, что проверяет планировщик в
    test_auto_requires_same_extension: «installer.exe» и «installer.zip» с
    идентичным содержимым — разные файлы. Здесь оно закреплено на стороне
    исполнения, иначе group_duplicates увела бы в карантин чужой файл.
    """
    auto = Rule(name="Дубликаты", dedupe=True)
    a = _make(tmp_path, "installer.exe")
    z = _make(tmp_path, "installer (1).zip")
    _make(tmp_path, "installer (2).exe")  # настоящая копия

    groups = group_duplicates(tmp_path, auto)

    assert len(groups) == 1
    assert z not in groups[0].remove
    assert a in groups[0].remove or a == groups[0].keep


def test_planner_and_grouping_agree(tmp_path):
    """План и исполнение опираются на одну и ту же группировку.

    Раньше планировщик искал копии сам (has_masked_copy: имена сравнивались
    по подобию строк) и мог объявить дублем файл, которого group_duplicates
    не видит. Сервис тогда пересчитывал группу, не находил её и писал в лог
    «nothing moved», хотя план обещал действие.
    """
    from modules.organizer.analyzer import analyze
    from modules.organizer.learning import Learned
    from modules.organizer.planner import plan

    auto = Rule(name="Дубликаты", dedupe=True)
    # похожие имена, но разные нормализованные стемы — не одна группа
    lone = _make(tmp_path, "abcdefgh1.exe")
    _make(tmp_path, "abcdefgh2.exe")
    # настоящая пара копий
    paired = _make(tmp_path, "installer.exe")
    _make(tmp_path, "installer (1).exe")

    groups = group_duplicates(tmp_path, auto)
    in_group = {p for g in groups for p in [g.keep, *g.remove]}

    for path in (lone, paired):
        planned = plan(analyze(path), [auto], tmp_path, Learned()) is not None
        assert planned == (path in in_group), f"план разошёлся с группой: {path.name}"


def test_preview_and_execution_agree(tmp_path):
    """Предпросмотр помечает ровно те файлы, которые получит исполнение."""
    for name in ("dupa.txt", "dupb.txt", "dupc.txt"):
        _make(tmp_path, name)
    _make(tmp_path, "other.txt", content=b"different bytes")
    _make(tmp_path, "dupa.log", content=CONTENT)  # не подходит по расширению

    rule = _rule()
    preview = preview_rule(rule, tmp_path, tmp_path)
    preview_dups = {p for p, label in preview.matches if label == t("preview.dedupe_bin")}

    groups = group_duplicates(tmp_path, rule)
    execution_dups = {p for group in groups for p in group.remove}

    assert preview_dups == execution_dups
    assert len(execution_dups) == 2
