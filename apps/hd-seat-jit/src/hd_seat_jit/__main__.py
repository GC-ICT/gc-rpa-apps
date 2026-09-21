from __future__ import annotations

import logging
import sys
import time

from gc_rpa_core import hub
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit
from gc_rpa_core.report import describe_error, print_banner, start_logging
from hd_seat_jit import common, loader, orders, vpn

FALLBACK_SYSTEM = "hd-seat-jit"
STEPS = 5

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

            def report(text: str) -> None:
                hub_session.progress(message=text, name=name)

            target = loader.target(settings)
            downloads = folders.download_dir(settings)
            logger.info("      %s ← %s", target.temp_table, downloads)

            thrown = loader.clear(downloads)
            if thrown:
                logger.info("      지난 회차 파일 %d개를 지웠습니다", thrown)

            logger.info("[2/%d] VPN", STEPS)
            vpn.connect(
                portal_schedule_id=common.vpn_schedule_id(),
                otp_schedule_id=common.otp_schedule_id(),
                downloads=downloads,
            )

            logger.info("[3/%d] 작업지시서", STEPS)
            with chrome(settings.url, download_dir=downloads, headless=common.headless()) as driver:
                taken = orders.run(driver, settings, plants=common.PLANTS, folder=downloads)
            report(f"작업지시서 {len(taken)}건 받았습니다")

            logger.info("[4/%d] 적재", STEPS)
            pages = loader.parsed(downloads, customer_code=common.CUSTOMER_CODE)
            written = loader.write(target, loader.rows_of(pages))
            report(f"{target.temp_table} {written}행 적재")

            logger.info("[5/%d] 마무리", STEPS)
            queries = loader.finish(target)
            loader.discard([page.source for page in pages])

            summary = f"{len(taken)}건 받아 {written}행 적재, 마무리 쿼리 {queries}건"
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
