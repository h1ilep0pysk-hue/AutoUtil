import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path

import exifread
from PIL import Image
from pypdf import PdfReader

from modules.organizer.ocr import recognize

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".heic"}
MAX_TEXT = 2000


@dataclass
class Features:
    path: Path
    ext: str
    size: int
    exif_date: datetime.datetime | None = None
    exif_has_gps: bool = False
    text: str = ""
    sha256_head: str = ""


def sha256_head(path: Path, n: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(n))
    return h.hexdigest()


def sha256_full(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _exif(path: Path) -> tuple[datetime.datetime | None, bool]:
    try:
        with path.open("rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        return None, False
    date = None
    raw = tags.get("EXIF DateTimeOriginal")
    if raw:
        try:
            date = datetime.datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            date = None
    return date, "GPS GPSLatitude" in tags


def _pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        parts = [p.extract_text() or "" for p in reader.pages[:2]]
        return "\n".join(parts)[:MAX_TEXT]
    except Exception:
        return ""


def _image_text(path: Path) -> str:
    try:
        with Image.open(path) as img:
            return recognize(img.convert("RGB"))[:MAX_TEXT]
    except Exception:
        return ""


def analyze(path: Path, need_text: bool = False) -> Features:
    ext = path.suffix.lower()
    feats = Features(path=path, ext=ext, size=path.stat().st_size)
    if ext in IMAGE_EXT:
        feats.exif_date, feats.exif_has_gps = _exif(path)
    if need_text:
        if ext == ".pdf":
            feats.text = _pdf_text(path)
        elif ext in IMAGE_EXT:
            feats.text = _image_text(path)
    feats.sha256_head = sha256_head(path)
    return feats
