from collections import Counter
from datetime import date, datetime
from pathlib import Path

from core.i18n import t
from core.journal import JournalEntry

MB = 1024 * 1024


def _local_date(e: JournalEntry) -> date:
    return datetime.fromisoformat(e.timestamp).astimezone().date()


def _folder(e: JournalEntry) -> str:
    if e.kind == "bin":
        return t("Корзина")
    parts = Path(e.dst).parent.parts
    return "/".join(parts[-2:]) if parts else t("(корень)")


def _ext(e: JournalEntry) -> str:
    p = Path(e.src) if e.kind == "bin" else Path(e.dst)
    return p.suffix.lower() or t("без расширения")


def build(entries: list[JournalEntry], start: date, end: date) -> dict:
    chosen = [e for e in entries if start <= _local_date(e) <= end]
    active = [e for e in chosen if not e.undone]
    undone = [e for e in chosen if e.undone]
    moved = [e for e in active if e.kind != "bin"]
    binned = [e for e in active if e.kind == "bin"]

    size = 0
    for e in moved:
        try:
            size += Path(e.dst).stat().st_size
        except OSError:
            pass

    return {
        "start": start,
        "end": end,
        "moved": len(moved),
        "binned": len(binned),
        "undone": len(undone),
        "trashed": sum(1 for e in undone if e.trashed),
        "size_mb": size / MB,
        "by_rule": Counter(e.rule for e in active),
        "by_ext": Counter(_ext(e) for e in active),
        "by_folder": Counter(_folder(e) for e in active),
    }


def to_markdown(r: dict, start: date, end: date) -> str:
    lines = [
        t("# Отчёт AutoUtil: {start:%d.%m.%Y} — {end:%d.%m.%Y}", start=start, end=end),
        "",
        t("- Перенесено файлов: **{moved}**", moved=r["moved"]),
        t("- Общий размер перенесённых: **{size:.1f} МБ**", size=r["size_mb"]),
        t("- Возвращено откатом: **{undone}**", undone=r["undone"]),
        t("- Из них убрано в корзину при откате: **{trashed}**", trashed=r["trashed"]),
    ]
    if r["binned"]:
        lines.append(t("- Убрано правилом в корзину: **{binned}**", binned=r["binned"]))
    lines.append("")
    if r["moved"] == 0 and r["binned"] == 0:
        lines.append(t("За период ничего не перенесено."))
        return "\n".join(lines)

    def table(title: str, counter: Counter, head: str) -> list[str]:
        out = [f"## {title}", "", f"| {head} | {t('Файлов')} |", "|---|---:|"]
        out += [f"| {k} | {v} |" for k, v in counter.most_common()]
        out.append("")
        return out

    lines += table(t("По правилам"), r["by_rule"], t("Правило"))
    lines += table(t("По папкам назначения"), r["by_folder"], t("Папка"))
    lines += table(t("По типам файлов"), r["by_ext"], t("Расширение"))
    return "\n".join(lines)
