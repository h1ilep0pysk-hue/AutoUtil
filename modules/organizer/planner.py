import logging
from dataclasses import dataclass
from pathlib import Path

from modules.organizer.actions import UnsafeTargetError, resolve_target  # FIX
from modules.organizer.analyzer import Features
from modules.organizer.dedupe_groups import DupGroup, group_duplicates
from modules.organizer.learning import Learned
from modules.organizer.naming import render_name
from modules.organizer.rules import Rule

log = logging.getLogger("autoutil.planner")  # FIX


@dataclass
class PlannedMove:
    src: Path
    dst: Path
    rule: str
    ask: bool = False
    to_bin: bool = False    # действие — убрать в корзину (dst не используется)
    delay_days: int = 0     # файл должен пролежать ещё N дней до действия
    dedupe: bool = False    # правило узла «Дубликаты»: действие идёт над группой
    # Готовая группа дубликатов: keep остаётся, remove уходит в карантин.
    # Считается здесь один раз, чтобы исполнение не пересчитывало её и не
    # могло разойтись с планом. None — группа не определена (старые вызовы).
    dedupe_group: DupGroup | None = None


def learn_key(rule_name: str, ext: str) -> str:
    return f"{rule_name}|{ext}"


def _dedupe_group(path: Path, rule: Rule) -> DupGroup | None:
    """Группа дубликатов, в которую входит path — как keep или как копия.

    Тот же ``group_duplicates``, что используют предпросмотр и исполнение,
    поэтому план больше не может разойтись с тем, что реально произойдёт.
    """
    try:
        groups = group_duplicates(path.parent, rule)
    except OSError:
        log.warning("Не удалось прочитать папку для поиска дубликатов: %s", path.parent)
        return None
    for group in groups:
        if path == group.keep or path in group.remove:
            return group
    return None


def plan(feats: Features, rules: list[Rule], base: Path, learned: Learned) -> PlannedMove | None:
    for rule in rules:
        try:  # FIX: одно сломанное правило не должно ломать обработку файла
            if rule.dedupe:
                # Узел «Дубликаты»: файл попадает в план, только если рядом
                # лежит его точная копия — та же маска (или «плюс-минус то же
                # имя» в авто-режиме) и то же содержимое. Из набора копий
                # остаётся ровно одна, остальные уходят в карантин.
                if not rule.masks_match(feats):
                    continue
                group = _dedupe_group(feats.path, rule)
                if group is None:
                    continue
                return PlannedMove(
                    src=feats.path,
                    dst=feats.path,
                    rule=rule.name,
                    to_bin=True,
                    delay_days=rule.delay_days,
                    dedupe=True,
                    dedupe_group=group,
                )
            folder = rule.match(feats)
        except Exception:
            log.exception("Правило «%s» упало на файле %s", rule.name, feats.path.name)
            continue
        if folder is None:
            continue
        override = learned.preferred(learn_key(rule.name, feats.ext))
        folder = override or folder
        if rule.to_bin:
            # Корзина: переноса нет, цель — сам файл (target у такого правила пуст).
            return PlannedMove(
                src=feats.path,
                dst=feats.path,
                rule=rule.name,
                ask=rule.ask,
                to_bin=True,
                delay_days=rule.delay_days,
            )
        try:  # FIX: папка должна оставаться внутри base
            dst_dir = resolve_target(base, folder)
        except UnsafeTargetError as e:
            log.warning("Правило «%s» пропущено: %s", rule.name, e)
            continue
        name = render_name(rule.rename, feats) if rule.rename else feats.path.name
        return PlannedMove(
            src=feats.path,
            dst=dst_dir / name,  # FIX: было base / folder / name
            rule=rule.name,
            ask=rule.ask,
            delay_days=rule.delay_days,
        )
    return None