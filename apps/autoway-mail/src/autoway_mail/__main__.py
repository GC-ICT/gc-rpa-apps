from __future__ import annotations

import logging
import sys
import time

from autoway_mail import common, history, inbox, mail
from gc_rpa_core import hub
from gc_rpa_core.browser import chrome
from gc_rpa_core.env import optional_env
from gc_rpa_core.report import describe_error, print_banner

FALLBACK_SYSTEM = "autoway-mail"
QUIET_LOGGERS = ("pysignalr", "urllib3", "websockets", "asyncio")
LOG_LEVEL_ENV = "GC_RPA_LOG_LEVEL"

logger = logging.getLogger(FALLBACK_SYSTEM)


def main() -> int:
    logging.basicConfig(
        level=optional_env(LOG_LEVEL_ENV, "INFO"),
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    started = time.monotonic()
    name = FALLBACK_SYSTEM

    with hub.session() as hub_session, hub.forwarding(hub_session, logger, level=logging.ERROR):
        try:
            settings = common.load()
            name = settings.name or FALLBACK_SYSTEM
            print_banner(name)
            logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", name, common.schedule_id())
            hub_session.started(name=name)

            workspace = common.workspace(settings)
            downloads = common.download_dir(settings)
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
                common.login(driver, settings)
                inbox.open_module(driver)
                session = mail.Session(
                    driver=driver,
                    settings=settings,
                    workspace=workspace,
                    downloads=downloads,
                    store=store,
                    report=lambda text: hub_session.progress(message=text, name=name),
                )
                tally = mail.run(session)
                logger.info("[3/3] 남은 메일")
                mail.report_listed(
                    "보안메일", store.secured_mails(), "저장할 수 없어 사람이 처리해야 합니다"
                )
                mail.report_listed(
                    "격리된 메일",
                    store.quarantined_mails(),
                    f"연속 {history.QUARANTINE_THRESHOLD}회 이상 실패, "
                    f"{int(history.QUARANTINE_RETRY.total_seconds() // 3600)}시간마다 재시도",
                )
        except Exception as exc:
            logger.error("실패했습니다: %s", describe_error(exc))
            logger.debug("상세 내역", exc_info=True)
            hub_session.failed(message=describe_error(exc), name=name)
            print_banner(f"실패했습니다  ({time.monotonic() - started:.1f}초)")
            return 1

        if tally.failed:
            hub_session.failed(message=tally.summary, name=name)
        else:
            hub_session.finished(message=tally.summary, name=name)

    print_banner(f"완료했습니다  {tally.summary}  ({time.monotonic() - started:.1f}초)")
    return 1 if tally.failed else 0


if __name__ == "__main__":
    sys.exit(main())
