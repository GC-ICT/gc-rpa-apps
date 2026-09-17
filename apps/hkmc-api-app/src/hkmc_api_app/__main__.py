from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from gc_rpa_core import config, hub
from gc_rpa_core.env import optional_env
from hkmc_api_app import build_settings, common, loader, registry
from hkmc_api_app.build_settings import Build
from hkmc_api_app.common import Api, Session, message, record_count, succeeded

FALLBACK_SYSTEM = "hkmc-api"
SCHEDULE_ID_ENV = "HKMC_SCHEDULE_ID"
COMPANIES_ENV = "HKMC_COMPANIES"
LOG_LEVEL_ENV = "GC_RPA_LOG_LEVEL"

QUIET_LOGGERS = ("pysignalr", "urllib3", "websockets", "asyncio", "httpx", "httpcore")

logger = logging.getLogger(FALLBACK_SYSTEM)


def schedule_id(build: Build) -> str:
    return optional_env(SCHEDULE_ID_ENV) or build.schedule_id


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


def system_name(build: Build, settings: config.RpaConfig) -> str:
    return build.signalr_system or settings.name or build.name or FALLBACK_SYSTEM


def collect(api: Api, opened: Session, writer: loader.Writer) -> int:
    company = opened.company
    if registry.sweeps(api):
        results = api.sweep(opened, plants=registry.plants_for(api, company))
    else:
        results = {"": api.fetch(opened)}

    expected = registry.expected_empty(api, company)

    answered = [result for result in results.values() if succeeded(result)]
    if not answered:
        first = next(iter(results.values()))
        note = " (예상된 오류)" if expected else ""
        logger.info("      %-4s 건너뜀 (%s)%s", company, message(first)[:32], note)
        return 0

    counts = loader.load_rows(api, api.collect_all(results), company=company, writer=writer)
    total = sum(counts.values())
    received = sum(record_count(result) for result in answered)
    logger.info("      %-4s %d행 (응답 %d건)", company, total, received)
    return total


def routines(build: Build, company: str) -> tuple[Api, ...]:
    return registry.for_indexes(build.indexes, company)


def run(
    settings: config.RpaConfig,
    build: Build,
    *,
    report: Callable[[str], None] = lambda _: None,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    chosen = registry.ordered(build.indexes)
    if not chosen:
        logger.info("수행할 API 가 없습니다")
        return totals

    steps = len(chosen) + 1
    targets = tuple(
        company for company in companies() if any(api.supports(company) for api in chosen)
    )

    with common.build_client() as client, loader.writer(settings.source) as writer:
        sessions = {company: common.open_session(client, company) for company in targets}

        for done, api in enumerate(chosen, start=1):
            logger.info("[%d/%d] %s %s", done + 1, steps, api.index, api.name)
            for company, opened in sessions.items():
                if not api.supports(company):
                    continue
                expected = registry.expected_empty(api, company)
                try:
                    rows = collect(api, opened, writer)
                except Exception as exc:
                    if expected:
                        logger.info("      %-4s 실패: %s (예상된 오류)", company, describe(exc))
                        totals[f"{company}/{api.index}"] = 0
                        continue
                    logger.error("      %-4s 실패: %s", company, describe(exc))
                    totals[f"{company}/{api.index}"] = -1
                    continue
                totals[f"{company}/{api.index}"] = rows
                report(f"{api.index} {api.name} {company} {rows}행 ({done}/{len(chosen)})")

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
            build = build_settings.current()
            settings = config.load(schedule_id(build))
            name = system_name(build, settings)
            relay.system_name = name
            banner(name)
            logger.info(
                "[1/%d] 설정 조회   %s (build=%s, schedule_id=%s, API %s)",
                len(build.indexes) + 1,
                name,
                build.name,
                schedule_id(build),
                ", ".join(build.indexes),
            )
            notify(hub_session.started, name=name)
            totals = run(
                settings,
                build,
                report=lambda text: notify(hub_session.progress, message=text, name=name),
            )
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
