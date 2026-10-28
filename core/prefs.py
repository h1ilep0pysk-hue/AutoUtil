from pathlib import Path

import tomllib
import tomli_w
from platformdirs import user_data_dir
from pydantic import BaseModel

PREFS_PATH = Path(user_data_dir("AutoUtil", appauthor=False)) / "prefs.toml"


class UiPrefs(BaseModel):
    language: str = ""              # "" (not chosen yet) | en | ru
    theme: str = "graphite"          # graphite | light
    accent: str = "#4A8FD8"
    font_size: int = 10
    show_tooltips: bool = True
    compact_lists: bool = False
    journal_limit: int = 200
    default_section: str = "schema"  # schema | journal | rules | settings
    confirm_undo: bool = True

    def model_post_init(self, __context) -> None:
        if self.default_section not in ("schema", "journal", "rules", "settings"):
            self.default_section = "schema"


def load_prefs() -> UiPrefs:
    if not PREFS_PATH.exists():
        prefs = UiPrefs()
        save_prefs(prefs)
        return prefs
    with PREFS_PATH.open("rb") as f:
        return UiPrefs.model_validate(tomllib.load(f))


def save_prefs(prefs: UiPrefs) -> None:
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PREFS_PATH.open("wb") as f:
        tomli_w.dump(prefs.model_dump(), f)
