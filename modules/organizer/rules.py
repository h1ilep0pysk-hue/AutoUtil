import datetime
from dataclasses import dataclass, field
from pathlib import Path

from modules.organizer.analyzer import Features


@dataclass
class Rule:
    name: str
    exts: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    requires_gps: bool = False
    target: str = ""
    enabled: bool = True

    @property
    def needs_text(self) -> bool:
        return self.enabled and bool(self.keywords)

    def match(self, f: Features) -> str | None:
        """Возвращает относительную папку назначения или None."""
        if not self.enabled:
            return None
        if self.exts and f.ext not in self.exts:
            return None
        if self.keywords:
            low = f.text.lower()
            if not any(k.lower() in low for k in self.keywords):
                return None
        if self.requires_gps and not f.exif_has_gps:
            return None
        year = _year(f)
        return self.target.format(year=year)


def _year(f: Features) -> int:
    if f.exif_date:
        return f.exif_date.year
    try:
        return datetime.datetime.fromtimestamp(f.path.stat().st_mtime).year
    except OSError:
        return datetime.datetime.now().year
