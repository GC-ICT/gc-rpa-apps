from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from gc_rpa_core import config, hub
from gc_rpa_core.env import optional_env
from hkmc_api_app import loader, registry
from hkmc_api_app.common import Api, message, record_count, session, succeeded

FALLBACK_SYSTEM = "hkmc-api"
SCHEDULE_ID_ENV = "HKMC_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "4"
COMPANIES_ENV = "HKMC_COMPANIES"
LOG_LEVEL_ENV = "GC_RPA_LOG_LEVEL"

QUIET_LOGGERS = ("pysignalr", "urllib3", "websockets", "asyncio", "httpx", "httpcore")

logger = logging.getLogger(FALLBACK_SYSTEM)


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def companies() -> tuple[str, ...]:
    configured = optional_env(COMPANIES_ENV)
    if not configured:
        return ("HMC", "KIA")
    return tuple(part.strip().upper() for part in configured.split(",") if part.strip())


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


def describe(exc: Exception) -> str:
    detail = str(exc).strip().splitlines()[0].strip() if str(exc).strip() else ""
    return f"{type(exc).__name__}: {detail or '상세 메시지가 없습니다'}"


def banner(text: str) -> None:
    line = "=" * 46
    print(line)
    print(f"  {text}")
    print(line, flush=True)


def collect(api: Api, company: str, settings: config.RpaConfig) -> int:
    with session(company) as opened:
        result = api.fetch(opened)

    if not succeeded(result):
        logger.info("      %s %-28s 건너뜀 (%s)", api.index, api.name, message(result)[:32])
        return 0

    counts = loader.load(api, result, company=company, endpoint=settings.source)
    total = sum(counts.values())
    logger.info("      %s %-28s %d행 (응답 %d건)", api.index, api.name, total, record_count(result))
    return total


def run(settings: config.RpaConfig) -> dict[str, int]:
    totals: dict[str, int] = {}
    for position, company in enumerate(companies(), start=1):
        logger.info("[%d/%d] %s", position + 1, len(companies()) + 1, company)
        for api in registry.for_company(company):
            try:
                totals[f"{company}/{api.index}"] = collect(api, company, settings)
            except Exception as exc:
                logger.error("      %s %-28s 실패: %s", api.index, api.name, describe(exc))
                totals[f"{company}/{api.index}"] = -1
    return totals


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

    with reporter() as hub_session, hub.forwarding(hub_session, logger) as relay:
        try:
            settings = config.load(schedule_id())
            name = settings.name or FALLBACK_SYSTEM
            relay.system_name = name
            banner(name)
            logger.info(
                "[1/%d] 설정 조회   %s (schedule_id=%s)",
                len(companies()) + 1,
                name,
                schedule_id(),
            )
            notify(hub_session.started, name=name)
            totals = run(settings)
        except Exception as exc:
            logger.error("실패했습니다: %s", describe(exc))
            logger.debug("상세 내역", exc_info=True)
            notify(hub_session.failed, message=describe(exc), name=name)
            banner(f"실패했습니다  ({time.monotonic() - started:.1f}초)")
            return 1

        rows = sum(count for count in totals.values() if count > 0)
        broken = [key for key, count in totals.items() if count < 0]
        summary = f"{len(totals)}건 조회, {rows}행 데이터 쓰기"
        if broken:
            summary += f", 실패 {len(broken)}건: {', '.join(broken)}"
            notify(hub_session.failed, message=summary, name=name)
        else:
            notify(hub_session.finished, message=summary, name=name)

    banner(f"완료했습니다  {summary}  ({time.monotonic() - started:.1f}초)")
    print(f"  데이터 쓰기 대상: {settings.source.database}", flush=True)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
