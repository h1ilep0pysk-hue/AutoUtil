import re
from datetime import datetime
from pathlib import Path

from modules.organizer.analyzer import Features

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _date(f: Features) -> datetime:
    if f.exif_date:
        return f.exif_date
    try:
        return datetime.fromtimestamp(f.path.stat().st_mtime)
    except OSError:
        return datetime.now()


def _vendor(text: str) -> str:
    """Грубая эвристика: первая строка текста с буквами. Ненадёжно на сложных чеках."""
    for line in text.splitlines():
        s = re.sub(r"[^\w .&-]", " ", line)
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) >= 3:
            return s[:30].strip()
    return "неизвестно"


def render_name(template: str, f: Features) -> str:
    d = _date(f)
    values = {
        "date": d.strftime("%Y-%m-%d"),
        "year": str(d.year),
        "month": f"{d.month:02d}",
        "name": f.path.stem,
        "ext": f.ext.lstrip('.'),
        "vendor": _vendor(f.text),
    }
    out = template
    for key, value in values.items():
        out = out.replace('{' + key + '}', value)
    out = _BAD.sub('_', out).strip().strip('.')
    if not out:
        out = f.path.stem
    if f.ext and not out.lower().endswith(f.ext.lower()):
        out += f.ext
    return out
