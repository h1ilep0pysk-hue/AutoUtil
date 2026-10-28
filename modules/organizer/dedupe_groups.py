"""Grouping of duplicate files for the «Дубликаты» node.

One place decides which copies are duplicates and which one stays. The
planner, the preview window and the execution path all call
:func:`group_duplicates`, so what the user sees is exactly what will happen.

Candidate selection:
- with a name mask — the rule's own conditions (``masks_match``);
- in auto mode (no mask) — the node's ``exts`` and a "similar" name,
  approximated by the normalized stem from ``dedupe.py``.

Grouping key is ``(size, sha256)``; in auto mode the extension and the
normalized stem are part of the key so unrelated files with identical bytes
never form a group.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from modules.organizer.analyzer import Features, sha256_full
from modules.organizer.dedupe import _norm_stem
from modules.organizer.rules import Rule

log = logging.getLogger("autoutil.dedupe_groups")


@dataclass
class DupGroup:
    """One set of identical files: what to keep and what to remove."""

    keep: Path
    remove: list[Path] = field(default_factory=list)
    size: int = 0
    digest: str = ""


def _keep_key(path: Path) -> tuple[float, int, str]:
    """Sort key: newest mtime wins, then shorter path, then lexicographic."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    text = str(path)
    return (-mtime, len(text), text)


def _candidate(path: Path, rule: Rule, auto: bool) -> Features | None:
    """Features of a candidate file, or None if the rule does not cover it."""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    feats = Features(path=path, ext=path.suffix.lower(), size=size)
    if auto:
        if rule.exts and feats.ext not in rule.exts:
            return None
    elif not rule.masks_match(feats):
        return None
    return feats


def group_duplicates(folder: Path, rule: Rule) -> list[DupGroup]:
    """Top-level files of *folder* grouped by identical content.

    Only groups of two or more files are returned. Each file is hashed at
    most once per call.
    """
    auto = not rule.name_globs
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []

    # First pass: cheap bucketing by size (and stem in auto mode) so that
    # hashes are computed only for files that can possibly collide.
    buckets: dict[tuple, list[Path]] = {}
    for path in entries:
        if not path.is_file():
            continue
        feats = _candidate(path, rule, auto)
        if feats is None:
            continue
        # Auto mode groups only files with the same extension: the node treats
        # «installer.exe» and «installer.zip» with identical bytes as different
        # files (pinned by test_auto_requires_same_extension).
        key = (feats.size, feats.ext, _norm_stem(path.stem)) if auto else (feats.size,)
        buckets.setdefault(key, []).append(path)

    hashes: dict[Path, str] = {}
    groups: list[DupGroup] = []
    for paths in buckets.values():
        if len(paths) < 2:
            continue
        by_digest: dict[str, list[Path]] = {}
        for path in paths:
            digest = hashes.get(path)
            if digest is None:
                try:
                    digest = sha256_full(path)
                except OSError:
                    continue
                hashes[path] = digest
            by_digest.setdefault(digest, []).append(path)
        for digest, same in by_digest.items():
            if len(same) < 2:
                continue
            keep = min(same, key=_keep_key)
            remove = sorted((p for p in same if p != keep), key=str)
            try:
                size = keep.stat().st_size
            except OSError:
                continue
            groups.append(DupGroup(keep=keep, remove=remove, size=size, digest=digest))

    groups.sort(key=lambda g: str(g.keep))
    return groups


def keep_still_valid(group: DupGroup) -> bool:
    """True if the kept file is still the same file we hashed.

    Checked right before every move: if the user (or another process)
    changed the file, the whole group must be aborted.
    """
    try:
        if group.keep.stat().st_size != group.size:
            return False
        return sha256_full(group.keep) == group.digest
    except OSError:
        log.warning("dedupe: keep file unreadable: %s", group.keep)
        return False
