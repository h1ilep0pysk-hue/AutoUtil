import difflib
import re
from pathlib import Path

from modules.organizer.analyzer import Features, sha256_full
from modules.organizer.rules import Rule


def find_duplicate(src: Path, target_dir: Path, size: int) -> Path | None:
    """Ищет в целевой папке файл того же размера с тем же полным хешем."""
    if not target_dir.is_dir():
        return None
    src_hash: str | None = None
    for candidate in target_dir.iterdir():
        if not candidate.is_file():
            continue
        try:
            if candidate.stat().st_size != size:
                continue
            if src_hash is None:
                src_hash = sha256_full(src)
            if sha256_full(candidate) == src_hash:
                return candidate
        except OSError:
            continue
    return None


def has_same_copy(src: Path, size: int | None = None) -> bool:
    """Есть ли рядом с src ещё один файл с тем же содержимым.

    Дубликат = тот же размер и тот же SHA-256. Хеш считается только у
    соседей совпадающего размера, поэтому на папке с сотнями файлов это
    быстро: сначала отсев, чтение только у кандидатов.
    """
    if size is None:
        try:
            size = src.stat().st_size
        except OSError:
            return False
    try:
        entries = list(src.parent.iterdir())
    except OSError:
        return False
    src_hash: str | None = None
    for candidate in entries:
        if candidate == src or not candidate.is_file():
            continue
        try:
            if candidate.stat().st_size != size:
                continue
            if src_hash is None:
                src_hash = sha256_full(src)
            if sha256_full(candidate) == src_hash:
                return True
        except OSError:
            continue
    return False


def _norm_stem(stem: str) -> str:
    """Простая нормализация имени без «мусора» от повторных скачиваний.

    «robloxinstaller (1)», «robloxinstaller - копия», «ROBLOX INSTALLER» —
    одно и то же слово. Хеш всё равно гарантирует идентичность содержимого,
    поэтому нормализация может быть смелой.
    """
    s = stem.lower().strip()
    for _ in range(4):
        prev = s
        s = re.sub(r"[(\[]\s*\d{1,4}\s*[)\]]", " ", s)  # хвост «(1)»
        s = re.sub(
            r"[([].{0,20}?(?:копия|copy|дубликат|duplicate|download|скачано).{0,12}[)\]]",
            " ", s, flags=re.IGNORECASE,
        )
        s = re.sub(
            r"[-–_ ]+\s*(?:копия|copy|дубликат|duplicate|download|скачано)\s*(?:\d{1,4})?\s*$",
            " ", s, flags=re.IGNORECASE,  # хвост «- копия 2», «(download»
        )
        s = re.sub(r"\d{1,4}$", " ", s) if re.search(r"[-–_ ]\d{1,4}\s*$", s) else s
        s = re.sub(r"[\s_\-–]+", " ", s).strip()
        if s == prev:
            break
    return s


def _similar_name(a: Path, b: Path) -> bool:
    """Похожие ли имена файлов? Тот же стем после нормализации, либо
    строки совпадают примерно на 80% и больше."""
    sa, sb = _norm_stem(a.stem), _norm_stem(b.stem)
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    return difflib.SequenceMatcher(None, sa, sb).ratio() >= 0.8


def has_masked_copy(rule: Rule, feats: Features) -> bool:
    """Есть ли рядом ещё один файл-копия с тем же содержимым.

    С маской: отбор — как у самого файла (маски, расширения, возраст):
    маска «robloxinstaller*» считает дубликатами только такие же по
    имени файлы, посторонние совпадения по размеру не влияют.
    Без маски (авто-режим узла «Дубликаты»): похожее имя, тот же
    размер и тот же SHA-256 — и копия считается найденной.
    """
    try:
        entries = list(feats.path.parent.iterdir())
    except OSError:
        return False
    auto = not rule.name_globs
    src_hash: str | None = None
    for candidate in entries:
        if candidate == feats.path or not candidate.is_file():
            continue
        try:
            size = candidate.stat().st_size
            if size != feats.size:
                continue
            cand_feats = Features(path=candidate, ext=candidate.suffix.lower(), size=size)
            if auto:
                # Авто: расширение совпадает у самого файла или задано в узле,
                # имя «плюс-минус то же».
                if cand_feats.ext != feats.ext:
                    continue
                if rule.exts and cand_feats.ext not in rule.exts:
                    continue
                if not _similar_name(candidate, feats.path):
                    continue
            elif not rule.masks_match(cand_feats):
                continue
            if src_hash is None:
                src_hash = sha256_full(feats.path)
            if sha256_full(candidate) == src_hash:
                return True
        except OSError:
            continue
    return False
