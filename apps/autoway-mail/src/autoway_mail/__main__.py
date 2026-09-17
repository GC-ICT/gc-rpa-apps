from __future__ import annotations

import logging
import sys
import time

from autoway_mail import mail
from gc_rpa_core import hub
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

    with hub.session() as hub_session, hub.forwarding(hub_session, mail.logger) as relay:
        try:
            settings = mail.load()
            name = settings.name or FALLBACK_SYSTEM
            relay.system_name = name
            print_banner(f"{name} — {mail.TASK_CODE}")
            hub_session.started(name=name)
            path = mail.run(settings)
        except Exception as exc:
            logger.error("실패했습니다: %s", describe_error(exc))
            logger.debug("상세 내역", exc_info=True)
            hub_session.failed(message=describe_error(exc), name=name)
            print_banner(f"실패했습니다  ({time.monotonic() - started:.1f}초)")
            return 1

        hub_session.finished(message=f"{path.name} → {path.parent}", name=name)

    print_banner(f"완료했습니다  {path.name}  ({time.monotonic() - started:.1f}초)")
    print(f"  저장 위치: {path.parent}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
