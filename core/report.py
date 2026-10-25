from collections import Counter
from datetime import date, datetime
from pathlib import Path

from core.journal import JournalEntry

MB = 1024 * 1024


def _local_date(e: JournalEntry) -> date:
    return datetime.fromisoformat(e.timestamp).astimezone().date()


def _folder(dst: str) -> str:
    parts = Path(dst).parent.parts
    return "/".join(parts[-2:]) if parts else "(корень)"


def build(entries: list[JournalEntry], start: date, end: date) -> dict:
    chosen = [e for e in entries if start <= _local_date(e) <= end]
    active = [e for e in chosen if not e.undone]
    undone = [e for e in chosen if e.undone]

    size = 0
    for e in active:
        try:
            size += Path(e.dst).stat().st_size
        except OSError:
            pass

    return {
        "start": start,
        "end": end,
        "moved": len(active),
        "undone": len(undone),
        "trashed": sum(1 for e in undone if e.trashed),
        "size_mb": size / MB,
        "by_rule": Counter(e.rule for e in active),
        "by_ext": Counter(Path(e.dst).suffix.lower() or "без расширения" for e in active),
        "by_folder": Counter(_folder(e.dst) for e in active),
    }


def to_markdown(r: dict, start: date, end: date) -> str:
    lines = [
        f"# Отчёт AutoUtil: {start:%d.%m.%Y} — {end:%d.%m.%Y}",
        "",
        f"- Перенесено файлов: **{r['moved']}**",
        f"- Общий размер перенесённых: **{r['size_mb']:.1f} МБ**",
        f"- Возвращено откатом: **{r['undone']}**",
        f"- Из них убрано в корзину при откате: **{r['trashed']}**",
        "",
    ]
    if r["moved"] == 0:
        lines.append("За период ничего не перенесено.")
        return "\n".join(lines)

    def table(title: str, counter: Counter, head: str) -> list[str]:
        out = [f"## {title}", "", f"| {head} | Файлов |", "|---|---:|"]
        out += [f"| {k} | {v} |" for k, v in counter.most_common()]
        out.append("")
        return out

    lines += table("По правилам", r["by_rule"], "Правило")
    lines += table("По папкам назначения", r["by_folder"], "Папка")
    lines += table("По типам файлов", r["by_ext"], "Расширение")
    return "\n".join(lines)
