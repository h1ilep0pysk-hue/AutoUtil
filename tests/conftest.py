import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

# (module, attribute, relative name) triples holding user-data paths.
# Module-level constants are computed at import time, so each of them must
# be patched explicitly. ``None`` means the attribute *is* the directory
# itself; otherwise it is a file/subdir under the app dir.
_PATH_ATTRS = [
    ("core.config", "APP_DIR", None),
    ("core.config", "SETTINGS_PATH", "settings.toml"),
    ("core.log", "APP_DIR", None),
    ("core.log", "LOG_DIR", "logs"),
    ("core.journal_db", "JOURNAL_DB_PATH", "journal.sqlite"),
    ("core.journal", "JOURNAL_PATH", "journal.jsonl"),
    ("core.pending", "PENDING_PATH", "pending.json"),
    ("core.schema", "SCHEMA_PATH", "schema.json"),
    ("core.prefs", "PREFS_PATH", "prefs.toml"),
    ("core.deferred", "APP_DIR", None),
    ("modules.organizer.rules_store", "RULES_PATH", "rules.json"),
    ("modules.organizer.learning", "LEARNED_PATH", "learned.json"),
    ("modules.organizer.cacheclean", "STATE_PATH", "cache_clean.json"),
]


@pytest.fixture(autouse=True)
def isolated_app_dir(tmp_path, monkeypatch):
    """Redirect every user-data path to tmp_path/AutoUtil.

    No test may read or write the real %LOCALAPPDATA%/AutoUtil.
    """
    fake = tmp_path / "AutoUtil"
    fake.mkdir()
    for module_name, attr, rel in _PATH_ATTRS:
        module = __import__(module_name, fromlist=["__name__"])
        monkeypatch.setattr(module, attr, fake if rel is None else fake / rel, raising=False)
    # Runtime calls (e.g. ui/explorer/report_page.py) go through
    # platformdirs.user_data_dir; patch it as well.
    import platformdirs

    monkeypatch.setattr(platformdirs, "user_data_dir", lambda *a, **kw: str(fake))
    yield
