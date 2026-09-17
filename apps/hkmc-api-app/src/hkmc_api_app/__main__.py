from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from gc_rpa_core import config, hub
from gc_rpa_core.env import optional_env
from gc_rpa_core.report import describe_error, print_banner
from hkmc_api_app import build_settings, common, loader, registry
from hkmc_api_app.build_settings import Build
from hkmc_api_app.common import Api, Session, message, record_count, succeeded

FALLBACK_SYSTEM = "hkmc-api"
FAILED = -1
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


def system_name(build: Build, settings: config.RpaConfig) -> str:
    return build.signalr_system or settings.name or build.name or FALLBACK_SYSTEM


@dataclass(frozen=True)
class Outcome:
    rows: int
    detail: str

    @property
    def broken(self) -> bool:
        return self.rows == FAILED


def collect_rows(api: Api, opened: Session, writer: loader.Writer) -> Outcome:
    company = opened.company
    if registry.sweeps(api):
        results = api.sweep(opened, plants=registry.plants_for(api, company))
    else:
        results = {"": api.fetch(opened)}

    answered = [result for result in results.values() if succeeded(result)]
    if not answered:
        first = next(iter(results.values()))
        note = " (예상된 오류)" if registry.expected_empty(api, company) else ""
        return Outcome(0, f"건너뜀 ({message(first)[:32]}){note}")

    counts = loader.load_rows(api, api.collect_all(results), company=company, writer=writer)
    total = sum(counts.values())
    received = sum(record_count(result) for result in answered)
    return Outcome(total, f"{total}행 (응답 {received}건)")


def run_routine(api: Api, opened: Session, writer: loader.Writer) -> Outcome:
    company = opened.company
    try:
        outcome = collect_rows(api, opened, writer)
    except Exception as exc:
        if registry.expected_empty(api, company):
            outcome = Outcome(0, f"실패: {describe_error(exc)} (예상된 오류)")
        else:
            outcome = Outcome(FAILED, f"실패: {describe_error(exc)}")

    write_log = logger.warning if outcome.broken else logger.info
    write_log("      %-4s %s", company, outcome.detail)
    return outcome


def summarize_totals(totals: dict[str, int]) -> tuple[str, list[str]]:
    broken = [key for key, count in totals.items() if count == FAILED]
    rows = sum(count for count in totals.values() if count != FAILED)
    summary = f"{len(totals)}건 조회, {rows}행 데이터 쓰기"
    if broken:
        summary += f", 실패 {len(broken)}건: {', '.join(broken)}"
    return summary, broken


def run(
    settings: config.RpaConfig,
    build: Build,
    *,
    report: Callable[[str, bool], None] = lambda *_: None,
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
                outcome = run_routine(api, opened, writer)
                totals[f"{company}/{api.index}"] = outcome.rows
                report(
                    f"{api.index} {api.name} {company} {outcome.detail} ({done}/{len(chosen)})",
                    outcome.broken,
                )

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

    with (
        hub.session() as hub_session,
        hub.forwarding(hub_session, logger, level=logging.ERROR) as relay,
    ):
        try:
            build = build_settings.current()
            settings = config.load(schedule_id(build))
            name = system_name(build, settings)
            relay.system_name = name
            planned = registry.ordered(build.indexes)
            print_banner(name)
            logger.info(
                "[1/%d] 설정 조회   %s (build=%s, schedule_id=%s, API %s)",
                len(planned) + 1,
                name,
                build.name,
                schedule_id(build),
                ", ".join(api.index for api in planned),
            )
            hub_session.started(name=name)

            def report_step(text: str, broken: bool) -> None:
                if broken:
                    hub_session.failed(message=text, name=name)
                else:
                    hub_session.progress(message=text, name=name)

            totals = run(settings, build, report=report_step)
        except Exception as exc:
            logger.error("실패했습니다: %s", describe_error(exc))
            logger.debug("상세 내역", exc_info=True)
            hub_session.failed(message=describe_error(exc), name=name)
            print_banner(f"실패했습니다  ({time.monotonic() - started:.1f}초)")
            return 1

        summary, broken = summarize_totals(totals)
        if broken:
            hub_session.failed(message=summary, name=name)
        else:
            hub_session.finished(message=summary, name=name)

    print_banner(f"완료했습니다  {summary}  ({time.monotonic() - started:.1f}초)")
    print(f"  데이터 쓰기 대상: {settings.source.database}", flush=True)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
