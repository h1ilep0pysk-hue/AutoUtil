from pathlib import Path
import tomllib

import tomli_w
from platformdirs import user_data_dir
from pydantic import BaseModel, Field

APP_DIR = Path(user_data_dir("AutoUtil", appauthor=False))
SETTINGS_PATH = APP_DIR / "settings.toml"


class OrganizerSettings(BaseModel):
    watch_dirs: list[str] = Field(default_factory=list)
    dry_run: bool = True
    excluded_dirs: list[str] = Field(default_factory=list)


class AppSettings(BaseModel):
    autostart: bool = False
    first_run: bool = True
    organizer: OrganizerSettings = Field(default_factory=OrganizerSettings)


def load_settings() -> AppSettings:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        settings = AppSettings()
        save_settings(settings)
        return settings
    with SETTINGS_PATH.open("rb") as f:
        data = tomllib.load(f)
    return AppSettings.model_validate(data)


def save_settings(settings: AppSettings) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("wb") as f:
        tomli_w.dump(settings.model_dump(), f)
