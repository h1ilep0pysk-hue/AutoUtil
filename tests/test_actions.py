import os
from pathlib import Path

import pytest

from modules.organizer.actions import (
    UnsafeTargetError,
    apply_move,
    clean_name,
    prepare_target,
    resolve_target,
)


# --- resolve_target ------------------------------------------------------

def test_relative_target_inside_base(tmp_path):
    dst = resolve_target(tmp_path, "Документы/PDF/2026")
    assert dst == (tmp_path / "Документы" / "PDF" / "2026").resolve()


def test_relative_escape_rejected(tmp_path):
    with pytest.raises(UnsafeTargetError):
        resolve_target(tmp_path, "../../Windows")


def test_absolute_inside_home_allowed(tmp_path):
    # tmp_path лежит внутри домашней папки пользователя — цели «Загрузок» работают.
    dst = resolve_target(tmp_path, str(tmp_path / "Установщики"))
    assert dst == (tmp_path / "Установщики").resolve()


def test_absolute_outside_home_rejected():
    # Чужая схема не должна уметь писать вне домашней папки.
    with pytest.raises(UnsafeTargetError):
        resolve_target(Path.home(), r"C:\Windows\Temp\evil")


# --- clean_name / prepare_target ----------------------------------------

def test_clean_name_replaces_bad_chars():
    assert clean_name('a<b>c:"d/e\\f|g?h*i') == "a_b_c__d_e_f_g_h_i"


def test_prepare_target_free_name(tmp_path):
    dst = tmp_path / "a.txt"
    assert prepare_target(dst) == dst


def test_prepare_target_avoids_existing(tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    got = prepare_target(tmp_path / "a.txt")
    assert got.name == "a (1).txt"


# --- apply_move ----------------------------------------------------------

def test_apply_move_plain(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("data", encoding="utf-8")
    out = tmp_path / "sub"
    out.mkdir()
    final = apply_move(src, out / "f.txt")
    assert final == out / "f.txt"
    assert (out / "f.txt").read_text(encoding="utf-8") == "data"
    assert not src.exists()


def test_apply_move_never_overwrites_busy_target(tmp_path):
    """Гонка после prepare_target: цель успели занять — не перезаписываем, а суффиксуем."""
    src = tmp_path / "new.txt"
    src.write_text("new", encoding="utf-8")
    busy = tmp_path / "busy.txt"
    busy.write_text("busy", encoding="utf-8")
    final = apply_move(src, busy)
    assert final != busy
    assert busy.read_text(encoding="utf-8") == "busy"
    assert final.read_text(encoding="utf-8") == "new"
    assert not src.exists()


def test_apply_move_creates_parent_dirs(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("d", encoding="utf-8")
    final = apply_move(src, tmp_path / "x" / "y" / "z" / "f.txt")
    assert final.read_text(encoding="utf-8") == "d"
