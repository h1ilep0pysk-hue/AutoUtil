import json
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_data_dir

from modules.organizer.rules import Rule

RULES_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "rules.json"

DEFAULT_RULES = [
    Rule(
        name="Чеки",
        exts=[".pdf", ".jpg", ".jpeg", ".png"],
        keywords=["итого", "total", "чек", "касса", "vat"],
        target="Документы/Чеки/{year}",
    ),
    Rule(
        name="Фото из поездок",
        exts=[".jpg", ".jpeg", ".heic"],
        requires_gps=True,
        target="Изображения/Поездки/{year}",
    ),
    Rule(
        name="Документы",
        exts=[".pdf", ".docx", ".xlsx", ".pptx", ".txt"],
        target="Документы/Документы/{year}",
    ),
    Rule(
        name="Установщики",
        exts=[".exe", ".msi"],
        target="Документы/Установщики",
    ),
]


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    if not path.exists():
        save_rules(DEFAULT_RULES, path)
        return [Rule(**asdict(r)) for r in DEFAULT_RULES]
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Rule(**item) for item in data]


def save_rules(rules: list[Rule], path: Path = RULES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in rules], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
