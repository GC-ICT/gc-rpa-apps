from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from gc_rpa_core.env import optional_env

BANNER_WIDTH = 46
EMPTY_DETAILS = ("", "Message:", "Message: None", "None")
NO_DETAIL = "상세 메시지가 없습니다"

LOG_LEVEL_ENV = "GC_RPA_LOG_LEVEL"
QUIET_LOGGERS = ("pysignalr", "urllib3", "websockets", "asyncio", "httpx", "httpcore")


def start_logging(*, verbose: Sequence[str] = ()) -> None:
    logging.basicConfig(
        level=optional_env(LOG_LEVEL_ENV, "INFO"),
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in verbose:
        logging.getLogger(name).setLevel(logging.INFO)


def describe_error(exc: Exception) -> str:
    text = str(exc).strip()
    detail = text.splitlines()[0].strip() if text else ""
    if detail in EMPTY_DETAILS:
        detail = NO_DETAIL
    return f"{type(exc).__name__}: {detail}"


def size_text(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1024:,.0f} KB" if size >= 1024 else f"{size} B"


def print_banner(text: str) -> None:
    line = "=" * BANNER_WIDTH
    print(line)
    print(f"  {text}")
    print(line, flush=True)
