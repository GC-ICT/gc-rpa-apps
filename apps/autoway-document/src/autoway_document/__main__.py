from __future__ import annotations

import logging
import sys

from autoway_document import common, document
from gc_rpa_autoway import poppler, site
from gc_rpa_core import app
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit
from gc_rpa_core.report import start_logging

FALLBACK_SYSTEM = "autoway-document"

logger = logging.getLogger(FALLBACK_SYSTEM)


def warn_about_poppler() -> None:
    complaint = poppler.complaint()
    if complaint:
        logger.warning("      %s", complaint)


def job(run: app.Run) -> app.Done:
    settings = common.load()
    run.begin(settings.name or FALLBACK_SYSTEM)
    logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", run.name, common.schedule_id())

    warn_about_poppler()
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
        logger.info("[3/3] 문서 한 건")
        taken = document.capture_one(driver, workspace=workspace, downloads=downloads)

    if taken is None:
        return app.Done("결재할 문서가 없습니다")

    summary = f"{taken.document.number} 내려받음 (첨부 {taken.attachments}건)"
    return app.Done(summary, note=f"받은 곳: {taken.folder}  ※ 결재·ERP 등록은 하지 않았습니다")


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
