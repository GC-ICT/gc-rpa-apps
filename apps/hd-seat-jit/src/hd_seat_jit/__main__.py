from __future__ import annotations

import logging
import sys
import time

from gc_rpa_core import hub
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import clean_up_browsers_on_exit
from gc_rpa_core.report import describe_error, print_banner, start_logging
from hd_seat_jit import common

FALLBACK_SYSTEM = "hd-seat-jit"
STEPS = 6

logger = logging.getLogger(FALLBACK_SYSTEM)


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    began = time.monotonic()
    name = FALLBACK_SYSTEM

    with hub.session() as hub_session, hub.forwarding(hub_session, logger, level=logging.ERROR):
        try:
            settings = common.load()
            name = settings.name or FALLBACK_SYSTEM
            print_banner(name)
            logger.info("[1/%d] 설정 조회   %s (schedule_id=%s)", STEPS, name, common.schedule_id())
            hub_session.started(name=name)

            downloads = folders.download_dir(settings)
            logger.info("      받을 곳 %s", downloads)

            summary = "설정까지 확인했습니다 (VPN·다운로드·적재 단계 없음)"
            logger.info("[2/%d] 아직 만들지 않았습니다", STEPS)
        except Exception as exc:
            logger.error("실패했습니다: %s", describe_error(exc))
            logger.debug("상세 내역", exc_info=True)
            hub_session.failed(message=describe_error(exc), name=name)
            print_banner(f"실패했습니다  ({time.monotonic() - began:.1f}초)")
            return 1

        hub_session.finished(message=summary, name=name)

    print_banner(f"완료했습니다  {summary}  ({time.monotonic() - began:.1f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
