from __future__ import annotations

import logging
import sys
import time

from gc_rpa_core import hub
from gc_rpa_core.env import optional_env
from mobis_as import pu010

TITLE = "Mobis A/S — PU010"
JOB = "mobis-as/PU010"
QUIET_LOGGERS = ("pysignalr", "urllib3", "websockets", "asyncio")
VERBOSE_LOGGERS = ("gc_rpa_core.browser",)
HEADLESS_ENV = "MOBIS_AS_HEADLESS"
LOG_LEVEL_ENV = "GC_RPA_LOG_LEVEL"

logger = logging.getLogger(JOB)


def headless() -> bool:
    return optional_env(HEADLESS_ENV, "1").strip().upper() in ("Y", "1", "T", "TRUE")


def report(*, success: bool, message: str, detail: dict[str, str] | None = None) -> None:
    try:
        hub.report(job=JOB, success=success, message=message, detail=detail)
    except Exception:
        logger.exception("허브 보고 실패")


def banner(text: str) -> None:
    line = "=" * 46
    print(line)
    print(f"  {text}")
    print(line, flush=True)


def main() -> int:
    logging.basicConfig(
        level=optional_env(LOG_LEVEL_ENV, "INFO"),
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in VERBOSE_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)

    banner(TITLE)
    started = time.monotonic()

    try:
        path = pu010.run(headless=headless())
    except Exception as exc:
        logger.error("실패: %s: %s", type(exc).__name__, exc)
        logger.debug("상세", exc_info=True)
        report(success=False, message=f"{type(exc).__name__}: {exc}")
        banner(f"실패  ({time.monotonic() - started:.1f}초)")
        return 1

    report(success=True, message=path.name, detail={"path": str(path)})
    banner(f"완료  {path.name}  ({time.monotonic() - started:.1f}초)")
    print(f"  저장 위치: {path.parent}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
