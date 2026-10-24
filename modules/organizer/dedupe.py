from pathlib import Path

from modules.organizer.analyzer import sha256_full


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
