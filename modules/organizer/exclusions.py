from pathlib import Path

IGNORED_SUFFIXES = {".crdownload", ".part", ".tmp"}


def is_excluded(path: Path, excluded_dirs: list[str]) -> bool:
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True
    if path.name.startswith("~$") or path.name.startswith('.'):
        return True
    for d in excluded_dirs:
        try:
            path.resolve().relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue
    return False
