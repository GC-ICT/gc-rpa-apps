from __future__ import annotations

import logging
import sys

from autoway_document import common, document
from gc_rpa_autoway import erp, poppler, site
from gc_rpa_core import app, config
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit, close_other_windows
from gc_rpa_core.report import start_logging

FALLBACK_SYSTEM = "autoway-document"

logger = logging.getLogger(FALLBACK_SYSTEM)


def warn_about_poppler() -> None:
    complaint = poppler.complaint()
    if complaint:
        logger.warning("      %s", complaint)


def erp_target(settings: config.RpaConfig) -> erp.Target | None:
    try:
        target = erp.target(config.usable_database(settings), key_column=common.ERP_KEY_COLUMN)
    except (LookupError, erp.ErpError) as exc:
        logger.warning("      ERP 등록 설정이 없어 결재 없이 내려받기만 합니다: %s", exc)
        return None

    logger.info("      ERP 등록 %s / %s", target.endpoint.database, target.file_table)
    return target


def finish(taken: document.Captured, target: erp.Target | None) -> app.Done:
    if target is None:
        return app.Done(
            f"{taken.document.number} 내려받음 (첨부 {taken.attachments}건)",
            note=f"받은 곳: {taken.folder}  ※ 결재·ERP 등록은 하지 않았습니다",
        )

    document_no = erp.register(
        taken.folder,
        sender=taken.document.sender,
        subject=taken.document.title,
        target=target,
    )
    return app.Done(
        f"{taken.document.number} 결재·ERP 등록 완료 (docu_no={document_no}, "
        f"첨부 {taken.attachments}건)"
    )


def job(run: app.Run) -> app.Done:
    settings = common.load()
    run.begin(settings.name or FALLBACK_SYSTEM)
    logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", run.name, common.schedule_id())

    warn_about_poppler()
    target = erp_target(settings)
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

        if target is not None:
            document.approve(driver)
        done = finish(taken, target)
        close_other_windows(driver, taken.approvals)

    return done


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
