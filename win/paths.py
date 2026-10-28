import ctypes
from ctypes import wintypes
from pathlib import Path

_DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"
_DOCUMENTS_GUID = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    import uuid
    u = uuid.UUID(text)
    g = _GUID()
    g.Data1 = u.time_low
    g.Data2 = u.time_mid
    g.Data3 = u.time_hi_version
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


def _known_folder(guid: str) -> Path:
    ptr = ctypes.c_wchar_p()
    g = _guid(guid)
    res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ptr))
    if res != 0:
        return Path.home() / "Downloads"
    path = Path(ptr.value)
    ctypes.windll.ole32.CoTaskMemFree(ptr)
    return path


def downloads_dir() -> Path:
    return _known_folder(_DOWNLOADS_GUID)


def documents_dir() -> Path:
    return _known_folder(_DOCUMENTS_GUID)
