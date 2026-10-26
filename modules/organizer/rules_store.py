import dataclasses
import json
import logging
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_data_dir

from modules.organizer.rules import Rule

log = logging.getLogger("autoutil.rules")  # FIX

RULES_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "rules.json"
_RULE_FIELDS = {f.name for f in dataclasses.fields(Rule)}  # FIX

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


def _rule_from_dict(item: dict) -> Rule | None:  # FIX: новая функция
    if not isinstance(item, dict) or "name" not in item:
        log.warning("Правило без имени пропущено: %r", item)
        return None
    unknown = set(item) - _RULE_FIELDS
    if unknown:
        log.warning("Неизвестные поля правила %s: %s", item.get("name"), sorted(unknown))
    try:
        return Rule(**{k: v for k, v in item.items() if k in _RULE_FIELDS})
    except TypeError as e:
        log.warning("Правило %s пропущено: %s", item.get("name"), e)
        return None


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    if not path.exists():
        save_rules(DEFAULT_RULES, path)
        return [Rule(**asdict(r)) for r in DEFAULT_RULES]
    try:  # FIX: повреждённый файл не роняет приложение
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("корень файла должен быть списком")
    except (ValueError, OSError) as e:
        broken = path.with_suffix(".broken.json")
        log.error("rules.json повреждён (%s), сохранён как %s, загружены правила по умолчанию", e, broken)
        try:
            path.replace(broken)
        except OSError:
            pass
        save_rules(DEFAULT_RULES, path)
        return [Rule(**asdict(r)) for r in DEFAULT_RULES]

    return [r for r in (_rule_from_dict(item) for item in data) if r is not None]  # FIX


def save_rules(rules: list[Rule], path: Path = RULES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")  # FIX: атомарная запись
    tmp.write_text(
        json.dumps([asdict(r) for r in rules], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)