"""Регресс-тест локализации: каждый ключ t("...") в коде обязан иметь перевод.

Многострочные русские литералы резалка берёт по частям, поэтому допускается
совпадение по началу настоящего ключа (фрагмент >= 20 символов).
"""
import re
from pathlib import Path

from core.i18n import _STRINGS
from core.ru_en import RU_EN

PROJECT = Path(__file__).resolve().parent.parent
KNOWN = set(RU_EN) | set(_STRINGS)
PATTERN = re.compile(r"""\bt\(\s*(['"])(.+?)\1""", re.S)


def _collect(path: Path, missing: list) -> None:
    if not path.exists():
        return
    for m in PATTERN.finditer(path.read_text(encoding="utf-8")):
        key = m.group(2).replace("\\n", "\n")
        if key in KNOWN:
            continue
        frag = key.rstrip("\\").rstrip()
        if len(frag) >= 20 and any(k.startswith(frag) for k in KNOWN):
            continue
        missing.append((path.name, key[:80]))


def test_all_t_keys_have_translations():
    missing: list = []
    for pattern in ("ui/**/*.py", "core/*.py", "modules/**/*.py"):
        for p in PROJECT.glob(pattern):
            _collect(p, missing)
    _collect(PROJECT / "main.py", missing)
    assert not missing, f"нет перевода для: {missing}"


def test_new_strings_bilingual():
    for key in ("journal.old_copy", "journal.old_copy_n", "naming.unknown_vendor",
                "schema.rejected_target", "cache.title", "notify.bin_title"):
        assert key in _STRINGS, key
        assert _STRINGS[key]["en"] and _STRINGS[key]["ru"]
