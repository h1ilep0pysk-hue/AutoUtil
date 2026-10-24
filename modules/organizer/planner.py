from dataclasses import dataclass
from pathlib import Path

from modules.organizer.analyzer import Features
from modules.organizer.learning import Learned
from modules.organizer.rules import Rule


@dataclass
class PlannedMove:
    src: Path
    dst: Path
    rule: str


def plan(feats: Features, rules: list[Rule], base: Path, learned: Learned) -> PlannedMove | None:
    for rule in rules:
        folder = rule.match(feats)
        if folder is None:
            continue
        override = learned.preferred(feats.ext)
        folder = override or folder
        return PlannedMove(src=feats.path, dst=base / folder / feats.path.name, rule=rule.name)
    return None
