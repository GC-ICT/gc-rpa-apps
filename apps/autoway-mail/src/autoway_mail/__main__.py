from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from autoway_mail import mail
from gc_rpa_core import hub
from gc_rpa_core.env import optional_env

FALLBACK_SYSTEM = "autoway-mail"
QUIET_LOGGERS = ("pysignalr", "urllib3", "websockets", "asyncio")
LOG_LEVEL_ENV = "GC_RPA_LOG_LEVEL"

logger = logging.getLogger(FALLBACK_SYSTEM)


def notify(action: Callable[..., None], **kwargs: str) -> None:
    try:
        action(**kwargs)
    except Exception as exc:
        logger.warning("허브에 보고하지 못했습니다: %s: %s", type(exc).__name__, exc)


@contextmanager
def reporter() -> Iterator[hub.Session]:
    try:
        with hub.session() as opened:
            yield opened
    except Exception as exc:
        logger.warning("허브 연결에 실패했습니다: %s: %s", type(exc).__name__, exc)
        yield hub.Session(None, None)


EMPTY_DETAILS = ("", "Message:", "Message: None", "None")


def describe(exc: Exception) -> str:
    detail = str(exc).strip().splitlines()[0].strip() if str(exc).strip() else ""
    if detail in EMPTY_DETAILS:
        detail = "상세 메시지가 없습니다"
    return f"{type(exc).__name__}: {detail}"


def banner(text: str) -> None:
    line = "=" * 46
    print(line)
    print(f"  {text}")
    print(line, flush=True)


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

    with reporter() as hub_session, hub.forwarding(hub_session, mail.logger) as relay:
        try:
            settings = mail.load()
            name = settings.name or FALLBACK_SYSTEM
            relay.system_name = name
            banner(f"{name} — {mail.TASK_CODE}")
            notify(hub_session.started, name=name)
            path = mail.run(settings)
        except Exception as exc:
            logger.error("실패했습니다: %s", describe(exc))
            logger.debug("상세 내역", exc_info=True)
            notify(hub_session.failed, message=describe(exc), name=name)
            banner(f"실패했습니다  ({time.monotonic() - started:.1f}초)")
            return 1

        notify(hub_session.finished, message=f"{path.name} → {path.parent}", name=name)

    banner(f"완료했습니다  {path.name}  ({time.monotonic() - started:.1f}초)")
    print(f"  저장 위치: {path.parent}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
