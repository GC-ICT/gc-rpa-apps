from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gc_rpa_core import hub
from gc_rpa_core.report import describe_error, print_banner


@dataclass(frozen=True)
class Done:
    summary: str
    broken: bool = False
    note: str = ""


@dataclass
class Run:
    session: hub.Session
    relay: hub.HubHandler
    name: str

    def begin(self, name: str, *, banner: str = "") -> None:
        self.name = name
        self.relay.system_name = name
        print_banner(banner or name)
        self.session.started(name=name)

    def step(self, text: str) -> None:
        self.session.progress(message=text, name=self.name)

    def broke(self, text: str) -> None:
        self.session.failed(message=text, name=self.name)


def start(
    fallback: str,
    logger: logging.Logger,
    job: Callable[[Run], Done],
    *,
    forward: Sequence[logging.Logger] = (),
    level: int = logging.ERROR,
) -> int:
    began = time.monotonic()
    listeners = tuple(forward) or (logger,)

    with (
        hub.session() as opened,
        hub.forwarding(opened, *listeners, level=level) as relay,
    ):
        run = Run(session=opened, relay=relay, name=fallback)
        try:
            done = job(run)
        except Exception as exc:
            logger.error("실패했습니다: %s", describe_error(exc))
            logger.debug("상세 내역", exc_info=True)
            run.broke(describe_error(exc))
            print_banner(f"실패했습니다  ({time.monotonic() - began:.1f}초)")
            return 1

        if done.broken:
            run.broke(done.summary)
        else:
            opened.finished(message=done.summary, name=run.name)

    print_banner(f"완료했습니다  {done.summary}  ({time.monotonic() - began:.1f}초)")
    if done.note:
        print(f"  {done.note}", flush=True)
    return 1 if done.broken else 0
