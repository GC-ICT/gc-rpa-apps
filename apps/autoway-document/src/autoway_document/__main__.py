from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autoway_document import common, document
from gc_rpa_autoway import erp, poppler, site
from gc_rpa_core import app, config
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit, close_other_windows
from gc_rpa_core.report import describe_error, start_logging

FALLBACK_SYSTEM = "autoway-document"
MAX_DOCUMENTS = 10

logger = logging.getLogger(FALLBACK_SYSTEM)


def warn_about_poppler() -> None:
    complaint = poppler.complaint()
    if complaint:
        logger.warning("      %s", complaint)


def erp_target(settings: config.RpaConfig) -> erp.Target:
    target = erp.target(config.usable_database(settings), key_column=common.ERP_KEY_COLUMN)
    logger.info("      ERP 등록 %s / %s", target.endpoint.database, target.file_table)
    return target


def register_one(taken: document.Captured, target: erp.Target) -> str:
    document_no = erp.register(
        taken.folder,
        sender=taken.document.sender,
        subject=taken.document.title,
        target=target,
        body=taken.pdf,
    )
    logger.info(
        "      %s 결재·ERP 등록 완료 (docu_no=%s, 첨부 %d건)",
        taken.document.number,
        document_no,
        taken.attachments,
    )
    return document_no


@dataclass
class Round:
    numbers: list[str] = field(default_factory=list)
    attachments: int = 0
    complaint: str = ""

    @property
    def summary(self) -> str:
        if not self.numbers:
            return "결재할 문서가 없습니다"
        return (
            f"{len(self.numbers)}건 결재·ERP 등록, 첨부 {self.attachments}건 "
            f"(docu_no={', '.join(self.numbers)})"
        )


def sweep(
    driver: Any,
    run: app.Run,
    *,
    target: erp.Target,
    workspace: Path,
    downloads: Path,
) -> Round:
    done = Round()
    base = driver.current_window_handle

    for turn in range(1, MAX_DOCUMENTS + 1):
        logger.info("      %d/%d 번째", turn, MAX_DOCUMENTS)
        try:
            taken = document.capture_one(driver, workspace=workspace, downloads=downloads)
            if taken is None:
                break
            document.approve(driver)
            document_no = register_one(taken, target)
        except Exception as exc:
            done.complaint = describe_error(exc)
            logger.error("      %s", done.complaint)
            break

        done.numbers.append(document_no)
        done.attachments += taken.attachments
        run.step(f"{taken.document.number} → {document_no} ({len(done.numbers)}/{MAX_DOCUMENTS})")
        close_other_windows(driver, base)
        driver.switch_to.default_content()

    return done


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
        logger.info("[3/3] 문서 최대 %d건", MAX_DOCUMENTS)
        done = sweep(driver, run, target=target, workspace=workspace, downloads=downloads)

    if done.complaint:
        return app.Done(f"{done.summary} / 중단: {done.complaint}", broken=True)
    return app.Done(done.summary)


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
