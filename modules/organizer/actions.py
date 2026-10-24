import re
import shutil
import time
from pathlib import Path

_BAD_CHARS = re.compile(r'[<>:"/\\|?*]')
LONG_PATH = 240


def clean_name(name: str) -> str:
    return _BAD_CHARS.sub("_", name)


def _long(p: Path) -> str:
    s = str(p)
    if len(s) > LONG_PATH and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def prepare_target(dst: Path) -> Path:
    """Подбирает свободное имя с суффиксом, не перезаписывая существующие файлы."""
    dst = dst.with_name(clean_name(dst.name))
    if not dst.exists():
        return dst
    stem, suffix = dst.stem, dst.suffix
    i = 1
    while True:
        candidate = dst.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def apply_move(src: Path, dst: Path, retries: int = 3, delay: float = 2.0) -> None:
    """Перемещает файл. Ничего не удаляет. Повторяет при блокировке антивирусом."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            shutil.move(_long(src), _long(dst))
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)
