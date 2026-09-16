from __future__ import annotations

import logging
import sys

from gc_rpa_core import hub
from gc_rpa_core.env import optional_env
from mobis_as import pu010

JOB = "mobis-as/PU010"
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


def main() -> int:
    logging.basicConfig(
        level=optional_env(LOG_LEVEL_ENV, "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        path = pu010.run(headless=headless())
    except Exception as exc:
        logger.exception("실패")
        report(success=False, message=f"{type(exc).__name__}: {exc}")
        return 1

    logger.info("다운로드 완료: %s", path)
    report(success=True, message=path.name, detail={"path": str(path)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
