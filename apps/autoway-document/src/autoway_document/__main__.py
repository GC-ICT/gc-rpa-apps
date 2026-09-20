from __future__ import annotations

import logging
import sys
import time

from autoway_document import common
from gc_rpa_autoway import erp, files, site
from gc_rpa_core import config, hub
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit
from gc_rpa_core.report import describe_error, print_banner, start_logging

FALLBACK_SYSTEM = "autoway-document"

logger = logging.getLogger(FALLBACK_SYSTEM)


def warn_about_poppler() -> None:
    complaint = files.poppler_complaint()
    if complaint:
        logger.warning("      %s", complaint)


def erp_target(settings: config.RpaConfig) -> erp.Target:
    target = erp.target(erp.usable_database(settings), key_column=common.ERP_KEY_COLUMN)
    logger.info("      ERP 등록 %s / %s", target.endpoint.database, target.file_table)
    return target


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
            logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", name, common.schedule_id())
            hub_session.started(name=name)

            warn_about_poppler()
            erp_target(settings)
            workspace = files.workspace(settings)
            downloads = files.download_dir(settings)
            logger.info("[2/3] 결재함      %s", workspace)

            with chrome(
                settings.url,
                download_dir=downloads,
                headless=common.headless(),
                keep_dialogs=True,
            ) as driver:
                site.login(driver, settings)
                logger.info("[3/3] 문서 처리   아직 만들지 않았습니다")
                summary = "로그인까지 확인했습니다 (문서 처리 단계 없음)"
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
