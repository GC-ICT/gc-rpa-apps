from __future__ import annotations

import logging
import sys

from gc_rpa_core import app
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit
from gc_rpa_core.report import start_logging
from gc_rpa_core.workspace import download_dir
from hd_seat_jit import common, loader, orders, vpn

FALLBACK_SYSTEM = "hd-seat-jit"

logger = logging.getLogger(FALLBACK_SYSTEM)


def job(run: app.Run) -> app.Done:
    settings = common.load()
    run.begin(settings.name or FALLBACK_SYSTEM)
    logger.info("[1/5] 설정 조회   %s (schedule_id=%s)", run.name, common.schedule_id())

    target = loader.target(settings)
    downloads = download_dir(settings)
    logger.info("      %s ← %s", target.temp_table, downloads)

    wiped = loader.clear(downloads)
    if wiped:
        logger.info("      지난 회차 파일 %d개를 지웠습니다", wiped)

    logger.info("[2/5] VPN")
    vpn.connect(
        portal_schedule_id=common.vpn_schedule_id(),
        otp_schedule_id=common.otp_schedule_id(),
        downloads=downloads,
    )

    logger.info("[3/5] 작업지시서")
    with chrome(settings.url, download_dir=downloads, headless=common.headless()) as driver:
        taken = orders.run(driver, settings, plants=common.PLANTS, folder=downloads)
    run.step(f"작업지시서 {len(taken)}건 받았습니다")

    logger.info("[4/5] 적재")
    pages = loader.parsed(downloads, customer_code=common.CUSTOMER_CODE)
    written = loader.write(target, loader.rows_of(pages))
    run.step(f"{target.temp_table} {written}행 적재")

    logger.info("[5/5] 마무리")
    queries = loader.finish(target)
    loader.discard([page.source for page in pages])

    return app.Done(f"{len(taken)}건 받아 {written}행 적재, 마무리 쿼리 {queries}건")


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
