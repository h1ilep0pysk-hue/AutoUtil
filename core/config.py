from pathlib import Path
import logging
import tomllib

import tomli_w
from platformdirs import user_data_dir
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("autoutil.config")

APP_DIR = Path(user_data_dir("AutoUtil", appauthor=False))
SETTINGS_PATH = APP_DIR / "settings.toml"

# Срок хранения журнала: по умолчанию год, допустимо от 1 дня до 10 лет.
JOURNAL_RETENTION_DEFAULT = 365
JOURNAL_RETENTION_MIN = 1
JOURNAL_RETENTION_MAX = 3650


class OrganizerSettings(BaseModel):
    watch_dirs: list[str] = Field(default_factory=list)
    dry_run: bool = True
    excluded_dirs: list[str] = Field(default_factory=list)
    # Периодическая очистка безопасных кэшей (см. modules/organizer/cacheclean.py).
    cache_clean: bool = True
    cache_clean_days: int = 30
    # Сколько дней хранить записи журнала (done/undone); см. JournalDB.purge_older_than.
    journal_retention_days: int = JOURNAL_RETENTION_DEFAULT

    @field_validator("journal_retention_days", mode="before")
    @classmethod
    def _clamp_retention(cls, value):
        try:
            days = int(value)
        except (TypeError, ValueError):
            days = None
        if days is None or not (JOURNAL_RETENTION_MIN <= days <= JOURNAL_RETENTION_MAX):
            log.warning(
                "journal_retention_days=%r вне диапазона %d..%d, использую %d",
                value, JOURNAL_RETENTION_MIN, JOURNAL_RETENTION_MAX,
                JOURNAL_RETENTION_DEFAULT,
            )
            return JOURNAL_RETENTION_DEFAULT
        return days


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
