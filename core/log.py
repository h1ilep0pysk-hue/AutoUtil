import logging
from logging.handlers import RotatingFileHandler

from platformdirs import user_data_dir
from pathlib import Path

APP_NAME = "AutoUtil"
APP_DIR = Path(user_data_dir(APP_NAME, appauthor=False))
LOG_DIR = APP_DIR / "logs"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("autoutil")
    logger.setLevel(level)

    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_DIR / "autoutil.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)

    return logger