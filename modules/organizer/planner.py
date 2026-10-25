from dataclasses import dataclass
from pathlib import Path

from modules.organizer.analyzer import Features
from modules.organizer.learning import Learned
from modules.organizer.naming import render_name
from modules.organizer.rules import Rule


@dataclass
class PlannedMove:
    src: Path
    dst: Path
    rule: str
    ask: bool = False


def learn_key(rule_name: str, ext: str) -> str:
    return f"{rule_name}|{ext}"


def plan(feats: Features, rules: list[Rule], base: Path, learned: Learned) -> PlannedMove | None:
    for rule in rules:
        folder = rule.match(feats)
        if folder is None:
            continue
        override = learned.preferred(learn_key(rule.name, feats.ext))
        folder = override or folder
        name = render_name(rule.rename, feats) if rule.rename else feats.path.name
        return PlannedMove(
            src=feats.path,
            dst=base / folder / name,
            rule=rule.name,
            ask=rule.ask,
        )
    return None
