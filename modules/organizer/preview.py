"""Предпросмотр правила: какие файлы папки под него попадут.

Логика повторяет plan() для одного правила (первое совпадение, override из
learned.json, корзина без папки-цели), так что предпросмотр показывает то же,
что реально сделает сервис.

Текст (PDF/OCR) читается только у кандидатов: у правил с ключевыми словами
— у тех, кто прошёл все остальные условия; у правил с «запрещёнными» словами
— у уже совпавших, чтобы отсеять ложные срабатывания. Так предпросмотр на
папке с сотнями картинок не превращается в минуты распознавания.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.i18n import t
from modules.organizer.actions import UnsafeTargetError, resolve_target
from modules.organizer.analyzer import Features, analyze
from modules.organizer.learning import Learned
from modules.organizer.planner import learn_key
from modules.organizer.rules import Rule

DEFAULT_OCR_LIMIT = 100  # сколько файлов максимум прогонять через OCR/PDF-текст


@dataclass
class RulePreview:
    matches: list[tuple[Path, str]] = field(default_factory=list)  # (файл, куда)
    total_files: int = 0          # сколько файлов вообще просмотрено
    ocr_capped: bool = False      # текстовых проверок было больше лимита


def _match_one(rule: Rule, feats: Features, base: Path, learned: Learned) -> str | None:
    """Куда уйдёт файл по этому правилу: строка-папка, «Корзина» или None."""
    folder = rule.match(feats)
    if folder is None:
        return None
    override = learned.preferred(learn_key(rule.name, feats.ext))
    folder = override or folder
    if rule.to_bin:
        return t("preview.bin")
    try:
        return str(resolve_target(base, folder))
    except (UnsafeTargetError, OSError, ValueError):
        return None  # правило не исполнится — честно не показываем файл


def preview_rule(rule: Rule, folder: Path, base: Path,
                 learned: Learned | None = None,
                 ocr_limit: int = DEFAULT_OCR_LIMIT) -> RulePreview:
    """Файлы верхнего уровня folder, подходящие под rule, с местом назначения."""
    result = RulePreview()
    if learned is None:
        learned = Learned()
    text_required = bool(rule.keywords or rule.keyword_groups)
    text_exclude = bool(rule.exclude_keywords)

    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return result

    labels: dict[Path, str] = {}
    candidates: list[Path] = []
    recheck: list[Path] = []
    for p in entries:
        if not p.is_file():
            continue
        result.total_files += 1
        try:
            feats = analyze(p, need_text=False)
        except OSError:
            continue
        hit = _match_one(rule, feats, base, learned)
        if text_required:
            if hit is None:
                candidates.append(p)  # совпадёт, только если в тексте есть слова
        else:
            if hit is not None:
                labels[p] = hit
            if text_exclude:
                recheck.append(p)  # может быть отвергнут запрещённым словом

    checks = 0
    if text_required:
        for p in candidates:
            if checks >= ocr_limit:
                result.ocr_capped = True
                break
            checks += 1
            try:
                feats = analyze(p, need_text=True)
            except OSError:
                continue
            hit = _match_one(rule, feats, base, learned)
            if hit is not None:
                labels[p] = hit
    for p in recheck:
        if checks >= ocr_limit:
            result.ocr_capped = True
            break
        checks += 1
        try:
            feats = analyze(p, need_text=True)
        except OSError:
            continue
        hit = _match_one(rule, feats, base, learned)
        if hit is None:
            labels.pop(p, None)
        else:
            labels[p] = hit

    result.matches = sorted(labels.items(), key=lambda kv: kv[0].name.lower())
    return result
