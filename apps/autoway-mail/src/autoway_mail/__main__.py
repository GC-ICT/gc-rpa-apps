from __future__ import annotations

import logging
import sys

from autoway_mail import common, history, inbox, mail
from gc_rpa_autoway import erp, poppler, site
from gc_rpa_core import app, config
from gc_rpa_core import workspace as folders
from gc_rpa_core.browser import chrome, clean_up_browsers_on_exit
from gc_rpa_core.report import start_logging

FALLBACK_SYSTEM = "autoway-mail"

logger = logging.getLogger(FALLBACK_SYSTEM)


def warn_about_poppler() -> None:
    complaint = poppler.complaint()
    if complaint:
        logger.warning("      %s", complaint)


def erp_target(settings: config.RpaConfig) -> erp.Target:
    target = erp.target(config.usable_database(settings), key_column=common.ERP_KEY_COLUMN)
    logger.info("      ERP 등록 %s / %s", target.endpoint.database, target.file_table)
    return target


def report_leftovers(store: history.History) -> None:
    logger.info("[3/3] 남은 메일")
    mail.report_listed("보안메일", store.secured_mails(), "저장할 수 없어 사람이 처리해야 합니다")
    mail.report_listed(
        "격리된 메일",
        store.quarantined_mails(),
        f"연속 {history.QUARANTINE_THRESHOLD}회 이상 실패, "
        f"{int(history.QUARANTINE_RETRY.total_seconds() // 3600)}시간마다 재시도",
    )


def job(run: app.Run) -> app.Done:
    settings = common.load()
    run.begin(settings.name or FALLBACK_SYSTEM)
    logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", run.name, common.schedule_id())

    warn_about_poppler()
    target = erp_target(settings)
    workspace = folders.workspace(settings)
    downloads = folders.download_dir(settings)
    logger.info("[2/3] 받은편지함   %s", workspace)

    with (
        chrome(
            settings.url,
            download_dir=downloads,
            headless=common.headless(),
            keep_dialogs=True,
        ) as driver,
        history.opened(common.history_path(settings)) as store,
    ):
        site.login(driver, settings)
        inbox.open_module(driver)
        session = mail.Session(
            driver=driver,
            settings=settings,
            erp_target=target,
            workspace=workspace,
            downloads=downloads,
            store=store,
            report=run.step,
        )
        tally = mail.run(session)
        report_leftovers(store)

    return app.Done(tally.summary, broken=bool(tally.failed))


def main() -> int:
    start_logging()
    clean_up_browsers_on_exit()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
