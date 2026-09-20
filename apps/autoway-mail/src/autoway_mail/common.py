from __future__ import annotations

from pathlib import Path

from gc_rpa_autoway.files import workspace
from gc_rpa_core import config
from gc_rpa_core.env import optional_env

SCHEDULE_ID_ENV = "AUTOWAY_MAIL_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "5"

HISTORY_FILE = "history.db"
HEADLESS_ENV = "AUTOWAY_MAIL_HEADLESS"

ERP_KEY_COLUMN = "mail_no"


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def load() -> config.RpaConfig:
    return config.load(schedule_id())


def history_path(settings: config.RpaConfig) -> Path:
    return workspace(settings) / HISTORY_FILE


def headless() -> bool:
    return config.flag(optional_env(HEADLESS_ENV, "1"))
