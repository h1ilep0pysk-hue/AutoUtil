import ctypes
import errno
import os
import re
import shutil
import time
from pathlib import Path

try:
    from send2trash import send2trash as _send2trash
except ImportError:  # запасной вариант, если библиотеки нет
    _send2trash = None

_BAD_CHARS = re.compile(r'[<>:"/\\|?*]')
LONG_PATH = 240


class UnsafeTargetError(ValueError):  # FIX: новый класс ошибки
    pass


def resolve_target(base: Path, folder: str) -> Path:  # FIX: новая функция
    """Возвращает папку назначения или бросает UnsafeTargetError.

    Относительные пути (например «Документы/PDF/{year}») разрешаются внутри
    base и не имеют права из него выйти. Абсолютные пути разрешаются как есть,
    но только внутри домашней папки пользователя — чужая импортированная
    схема не сможет отправить файлы на другой диск или в системные папки.
    """
    p = Path(folder)
    if p.is_absolute():
        resolved = p.resolve()
        if not resolved.is_relative_to(Path.home().resolve()):
            raise UnsafeTargetError(f"Абсолютный путь вне домашней папки: {folder}")
        return resolved
    base_resolved = base.resolve()
    dst = (base_resolved / folder).resolve()
    if not dst.is_relative_to(base_resolved):
        raise UnsafeTargetError(f"Путь выходит за пределы домашней папки: {folder}")
    return dst


def recycle(path: Path) -> bool:
    """Убирает файл в корзину Windows (потом можно восстановить).

    Сначала пробует SHFileOperationW (стандартная корзина), при неудаче —
    send2trash. Возвращает True, если файл действительно исчез с места.
    """
    path = Path(path)
    if not path.exists():
        return False

    # Вариант 1: Win32 SHFileOperationW с флагом «в корзину».
    try:
        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x40
        FOF_NOCONFIRMATION = 0x10
        FOF_SILENT = 0x4
        FOF_NOERRORUI = 0x400

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", ctypes.c_int),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = str(path) + "\0"
        op.pTo = ""
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res == 0 and not op.fAnyOperationsAborted and not path.exists():
            return True
    except Exception:
        pass

    # Вариант 2: send2trash (тоже кладёт в корзину).
    if _send2trash is not None:
        try:
            _send2trash(str(path))
            return not path.exists()
        except Exception:
            return False
    return False


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


def apply_move(src: Path, dst: Path, retries: int = 3, delay: float = 2.0) -> Path:
    """Перемещает файл и возвращает фактический путь назначения.

    Ничего не удаляет и не перезаписывает: если цель успел занять другой файл
    (гонка после prepare_target), os.rename бросит FileExistsError и мы подберём
    имя с суффиксом. shutil.move так не умеет — он молча перезаписал бы цель
    копией. Повторяет попытку при блокировке антивирусом.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    attempt = 0
    while True:
        try:
            try:
                os.rename(_long(src), _long(dst))
                return dst
            except OSError as e:
                if e.errno != errno.EXDEV:
                    raise
                shutil.move(_long(src), _long(dst))  # перенос на другой диск
                return dst
        except FileExistsError:
            dst = prepare_target(dst)
        except PermissionError:
            if attempt >= retries - 1:
                raise
            attempt += 1
            time.sleep(delay)
