import logging
from dataclasses import dataclass
from pathlib import Path

from modules.organizer.actions import UnsafeTargetError, resolve_target  # FIX
from modules.organizer.analyzer import Features
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


def learn_key(rule_name: str, ext: str) -> str:
    return f"{rule_name}|{ext}"


def plan(feats: Features, rules: list[Rule], base: Path, learned: Learned) -> PlannedMove | None:
    for rule in rules:
        try:  # FIX: одно сломанное правило не должно ломать обработку файла
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