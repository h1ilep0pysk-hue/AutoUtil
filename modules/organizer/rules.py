import datetime
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from modules.organizer.analyzer import Features

MB = 1024 * 1024


@dataclass
class Rule:
    name: str
    exts: list[str] = field(default_factory=list)
    exclude_exts: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)          # любое из слов
    keyword_groups: list[list[str]] = field(default_factory=list)  # все группы должны совпасть
    exclude_keywords: list[str] = field(default_factory=list)  # ни одного из слов
    name_globs: list[str] = field(default_factory=list)        # маска имени, все должны совпасть
    name_regexes: list[str] = field(default_factory=list)
    exclude_regexes: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)     # маска имени или любой папки в пути
    min_mb: float = 0.0       # 0 = без ограничения
    max_mb: float = 0.0
    min_age_days: int = 0     # файл старше N дней
    max_age_days: int = 0     # файл новее N дней
    requires_gps: bool = False
    forbid_gps: bool = False
    ask: bool = False         # не переносить сразу, положить в «Спросить»
    rename: str = ""          # шаблон имени, например {date}_{name}.{ext}
    target: str = "",
    enabled: bool = True

    @property
    def needs_text(self) -> bool:
        if not self.enabled:
            return False
        return bool(self.keywords or self.keyword_groups or self.exclude_keywords
                    or "{vendor}" in self.rename)

    def match(self, f: Features) -> str | None:
        """Возвращает относительную папку назначения или None."""
        if not self.enabled:
            return None
        if self.exts and f.ext not in self.exts:
            return None
        if f.ext in self.exclude_exts:
            return None
        if _masked(f.path, self.exclude_globs):
            return None

        name = f.path.name
        if self.name_globs and not all(
            fnmatch.fnmatch(name.lower(), g.lower()) for g in self.name_globs
        ):
            return None
        if self.name_regexes and not all(_search(p, name) for p in self.name_regexes):
            return None
        if any(_search(p, name) for p in self.exclude_regexes):
            return None

        mb = f.size / MB
        if self.min_mb and mb < self.min_mb:
            return None
        if self.max_mb and mb > self.max_mb:
            return None

        age = _age_days(f.path)
        if self.min_age_days and age < self.min_age_days:
            return None
        if self.max_age_days and age > self.max_age_days:
            return None

        if self.requires_gps and not f.exif_has_gps:
            return None
        if self.forbid_gps and f.exif_has_gps:
            return None

        low = f.text.lower()
        groups = ([self.keywords] if self.keywords else []) + self.keyword_groups
        for group in groups:
            if not any(k.lower() in low for k in group):
                return None
        if any(k.lower() in low for k in self.exclude_keywords):
            return None

        return self.target.format(year=_year(f))


def _masked(path: Path, globs: list[str]) -> bool:
    if not globs:
        return False
    parts = [p.lower() for p in path.parts]
    return any(fnmatch.fnmatch(part, g.lower()) for g in globs for part in parts)


def _search(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, re.IGNORECASE) is not None
    except re.error:
        return False


def _age_days(path: Path) -> int:
    try:
        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return 0
    return (datetime.datetime.now() - mtime).days


def _year(f: Features) -> int:
    if f.exif_date:
        return f.exif_date.year
    try:
        return datetime.datetime.fromtimestamp(f.path.stat().st_mtime).year
    except OSError:
        return datetime.datetime.now().year
