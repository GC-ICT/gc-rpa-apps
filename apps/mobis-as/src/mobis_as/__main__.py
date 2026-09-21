from __future__ import annotations

import logging
import sys

from gc_rpa_core import app, config
from gc_rpa_core.env import optional_env
from gc_rpa_core.report import start_logging
from mobis_as import pu010

FALLBACK_SYSTEM = "mobis-as"
VERBOSE_LOGGERS = ("gc_rpa_core.browser",)
HEADLESS_ENV = "MOBIS_AS_HEADLESS"

logger = logging.getLogger(FALLBACK_SYSTEM)


def headless() -> bool:
    return config.flag(optional_env(HEADLESS_ENV, "1"))


def job(run: app.Run) -> app.Done:
    settings = pu010.load()
    name = settings.name or FALLBACK_SYSTEM
    run.begin(name, banner=f"{name} — {pu010.SCREEN_CODE}")
    path = pu010.run(settings, headless=headless())
    return app.Done(path.name, note=f"저장 위치: {path.parent}")


def main() -> int:
    start_logging(verbose=VERBOSE_LOGGERS)
    return app.start(FALLBACK_SYSTEM, logger, job, forward=(pu010.logger,), level=logging.NOTSET)


if __name__ == "__main__":
    sys.exit(main())
