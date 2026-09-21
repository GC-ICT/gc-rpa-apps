from __future__ import annotations

import logging
import sys

from autoway_document import common
from gc_rpa_autoway import erp, poppler, site
from gc_rpa_core import app, config
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit
from gc_rpa_core.report import start_logging

FALLBACK_SYSTEM = "autoway-document"

logger = logging.getLogger(FALLBACK_SYSTEM)


def warn_about_poppler() -> None:
    complaint = poppler.complaint()
    if complaint:
        logger.warning("      %s", complaint)


def erp_target(settings: config.RpaConfig) -> erp.Target:
    target = erp.target(config.usable_database(settings), key_column=common.ERP_KEY_COLUMN)
    logger.info("      ERP 등록 %s / %s", target.endpoint.database, target.file_table)
    return target


def job(run: app.Run) -> app.Done:
    settings = common.load()
    run.begin(settings.name or FALLBACK_SYSTEM)
    logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", run.name, common.schedule_id())

    warn_about_poppler()
    erp_target(settings)
    workspace = folders.workspace(settings)
    downloads = folders.download_dir(settings)
    logger.info("[2/3] 결재함      %s", workspace)

    with chrome(
        settings.url,
        download_dir=downloads,
        headless=common.headless(),
        keep_dialogs=True,
    ) as driver:
        site.login(driver, settings)
        logger.info("[3/3] 문서 처리   아직 만들지 않았습니다")

    return app.Done("로그인까지 확인했습니다 (문서 처리 단계 없음)")


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
