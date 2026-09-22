from __future__ import annotations

from gc_rpa_core import config
from gc_rpa_core.env import optional_env

SCHEDULE_ID_ENV = "AUTOWAY_DOCUMENT_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "7"

HEADLESS_ENV = "AUTOWAY_DOCUMENT_HEADLESS"
APPROVE_ENV = "AUTOWAY_DOCUMENT_APPROVE"

ERP_KEY_COLUMN = "docu_no"


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def load() -> config.RpaConfig:
    return config.load(schedule_id())


def headless() -> bool:
    return config.flag(optional_env(HEADLESS_ENV, "1"))


def approving() -> bool:
    return config.flag(optional_env(APPROVE_ENV, "Y"))
