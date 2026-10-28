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
from modules.organizer.planner import PlannedMove, learn_key, plan
from modules.organizer.rules import Rule

DEFAULT_OCR_LIMIT = 100  # сколько файлов максимум прогонять через OCR/PDF-текст


@dataclass
class RulePreview:
    matches: list[tuple[Path, str]] = field(default_factory=list)  # (файл, куда)
    total_files: int = 0          # сколько файлов вообще просмотрено
    ocr_capped: bool = False      # текстовых проверок было больше лимита


def _match_one(rule: Rule, feats: Features, base: Path, learned: Learned,
               dup_remove: set[Path] | None = None) -> str | None:
    """Куда уйдёт файл по этому правилу: строка-папка, «Корзина» или None."""
    if rule.dedupe:
        # Честно повторяем исполнение: показываем корзину только файлам,
        # которые group_duplicates() отнесла к копиям (keep остаётся на месте).
        if dup_remove and feats.path in dup_remove:
            return t("preview.dedupe_bin")
        return None
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

    # Дубликаты считаем один раз на папку: и предпросмотр, и исполнение
    # должны опираться на одну и ту же группировку.
    dup_remove: set[Path] = set()
    if rule.dedupe:
        from modules.organizer.dedupe_groups import group_duplicates

        for group in group_duplicates(folder, rule):
            dup_remove.update(group.remove)

    for p in entries:
        if not p.is_file():
            continue
        result.total_files += 1
        try:
            feats = analyze(p, need_text=False)
        except OSError:
            continue
        hit = _match_one(rule, feats, base, learned, dup_remove)
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
            hit = _match_one(rule, feats, base, learned, dup_remove)
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
        hit = _match_one(rule, feats, base, learned, dup_remove)
        if hit is None:
            labels.pop(p, None)
        else:
            labels[p] = hit

    result.matches = sorted(labels.items(), key=lambda kv: kv[0].name.lower())
    return result


@dataclass
class PreviewMove:
    """Куда уйдёт один файл: папка-назначение и правило, которое его поймало."""
    src: Path
    dst: str              # абсолютный путь папки или t("preview.bin") для корзины
    rule: str
    to_bin: bool = False
    ask: bool = False     # файл попадёт в «Спросить», а не перенесётся сам
    delay_days: int = 0   # действие отложено на N дней


@dataclass
class FolderPreview:
    moves: list[PreviewMove] = field(default_factory=list)
    total_files: int = 0
    ocr_capped: bool = False


def _text_can_change(rule_name: str, rules: list[Rule]) -> bool:
    """Может ли настоящий текст файла сместить совпадение на это правило?

    Совпадение «первое выигрывает» стабильно, только если до правила rule_name
    нет правил с ключевыми словами, а само правило не запрещает слова и не
    использует {vendor} в шаблоне имени (имя зависит от текста).
    """
    idx = next((i for i, r in enumerate(rules) if r.name == rule_name), None)
    if idx is None:
        return True
    if rules[idx].exclude_keywords or "{vendor}" in rules[idx].rename:
        return True
    return any(r.needs_text for r in rules[:idx])


def preview_folder(folder: Path, base: Path, rules: list[Rule] | None = None,
                   learned: Learned | None = None,
                   ocr_limit: int = DEFAULT_OCR_LIMIT) -> FolderPreview:
    """Куда сервис разложит файлы папки прямо сейчас: по всем правилам сразу.

    Повторяет ночную логику сервиса: первое совпавшее правило, override из
    learned.json, переименование по шаблону, корзина. Текст (PDF/OCR) читается
    с лимитом — только у кандидатов, где совпадение зависит от текста.
    """
    result = FolderPreview()
    if learned is None:
        learned = Learned()
    if rules is None:
        # Локальный импорт: rules_store знает о правилах, но не о предпросмотре.
        from modules.organizer.rules_store import load_rules

        rules = [r for r in load_rules() if r.enabled]

    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return result

    text_rules = any(r.needs_text for r in rules)
    matched: dict[Path, PlannedMove] = {}
    candidates: list[Path] = []

    for p in entries:
        if not p.is_file():
            continue
        result.total_files += 1
        try:
            feats = analyze(p, need_text=False)
        except OSError:
            continue
        move = plan(feats, rules, base, learned)
        if move is None:
            if text_rules:
                candidates.append(p)  # совпадение может появиться, когда прочитаем текст
        elif _text_can_change(move.rule, rules):
            candidates.append(p)  # текст может сместить совпадение — проверяем честно
        else:
            matched[p] = move

    checks = 0
    for p in candidates:
        if checks >= ocr_limit:
            result.ocr_capped = True
            break
        checks += 1
        try:
            feats = analyze(p, need_text=True)
        except OSError:
            continue
        move = plan(feats, rules, base, learned)
        if move is not None:
            matched[p] = move

    for p, move in matched.items():
        result.moves.append(PreviewMove(
            src=p,
            dst=t("preview.bin") if move.to_bin else str(move.dst.parent),
            rule=move.rule,
            to_bin=move.to_bin,
            ask=move.ask,
            delay_days=move.delay_days,
        ))
    result.moves.sort(key=lambda m: m.src.name.lower())
    return result
