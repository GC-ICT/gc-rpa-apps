from __future__ import annotations

from pathlib import Path

from gc_rpa_core import config
from gc_rpa_core.browser import resolve_dir
from gc_rpa_core.env import bundle_dir, optional_env

SCHEDULE_ID_ENV = "AUTOWAY_MAIL_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "5"

DOWNLOAD_DIR_ENV = "AUTOWAY_MAIL_DOWNLOAD_DIR"
DEFAULT_DOWNLOAD_DIR = "downloads"


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def load() -> config.RpaConfig:
    return config.load(schedule_id())


def download_dir() -> Path:
    configured = optional_env(DOWNLOAD_DIR_ENV)
    if configured:
        return resolve_dir(configured)
    return resolve_dir(str(bundle_dir() / DEFAULT_DOWNLOAD_DIR))


def size_text(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1024:,.0f} KB" if size >= 1024 else f"{size} B"
