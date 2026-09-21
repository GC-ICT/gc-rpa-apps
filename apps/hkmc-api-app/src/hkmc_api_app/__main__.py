from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from gc_rpa_core import app, config
from gc_rpa_core.env import optional_env
from gc_rpa_core.report import describe_error, start_logging
from hkmc_api_app import build_settings, common, loader, registry
from hkmc_api_app.build_settings import Build
from hkmc_api_app.common import Api, Session, message, record_count, succeeded

FALLBACK_SYSTEM = "hkmc-api"
FAILED = -1
SCHEDULE_ID_ENV = "HKMC_SCHEDULE_ID"
COMPANIES_ENV = "HKMC_COMPANIES"

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


def checked_databases(databases: Sequence[config.RpaDatabase]) -> tuple[config.RpaDatabase, ...]:
    for database in databases:
        if database.complaint:
            raise LookupError(database.complaint)

    return tuple(databases)


@dataclass(frozen=True)
class Plan:
    build: Build
    databases: tuple[config.RpaDatabase, ...]
    name: str

    @property
    def written_to(self) -> str:
        return ", ".join(database.label for database in self.databases)


def plan() -> Plan:
    build = build_settings.current()
    settings = config.load(schedule_id(build))
    return Plan(
        build=build,
        databases=checked_databases(config.load_databases(settings.actprg_id)),
        name=system_name(build, settings),
    )


def announce(chosen: Plan) -> None:
    planned = registry.ordered(chosen.build.indexes)
    logger.info(
        "[1/%d] 설정 조회   %s (build=%s, schedule_id=%s, API %s)",
        len(planned) + 2,
        chosen.name,
        chosen.build.name,
        schedule_id(chosen.build),
        ", ".join(api.index for api in planned),
    )
    logger.info("      데이터 쓰기 대상 %s", chosen.written_to)


@dataclass(frozen=True)
class Outcome:
    rows: int
    detail: str

    @property
    def broken(self) -> bool:
        return self.rows == FAILED


def collect_rows(api: Api, opened: Session, targets: Sequence[loader.Writer]) -> Outcome:
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

    counts = loader.load_rows(api, api.collect_all(results), company=company, targets=targets)
    total = sum(counts.values())
    received = sum(record_count(result) for result in answered)
    return Outcome(total, f"{total}행 (응답 {received}건)")


def run_routine(api: Api, opened: Session, targets: Sequence[loader.Writer]) -> Outcome:
    company = opened.company
    try:
        outcome = collect_rows(api, opened, targets)
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


def finish(target: loader.Writer, report: Callable[[str, bool], None]) -> int:
    try:
        ran = loader.run_queries(target, loader.collected_at().date())
    except Exception as exc:
        logger.error("      %s", describe_error(exc))
        report(f"{target.name} 쿼리 실패: {describe_error(exc)}", True)
        return FAILED

    report(f"{target.name} 쿼리 {ran}건 실행", False)
    return 0


def sweep(
    build: Build,
    databases: Sequence[config.RpaDatabase],
    *,
    report: Callable[[str, bool], None] = lambda *_: None,
) -> dict[str, int]:
    totals: dict[str, int] = {}
    chosen = registry.ordered(build.indexes)
    if not chosen:
        logger.info("수행할 API 가 없습니다")
        return totals

    steps = len(chosen) + 2
    involved = tuple(
        company for company in companies() if any(api.supports(company) for api in chosen)
    )

    with common.build_client() as client, loader.writers(databases) as targets:
        sessions = {company: common.open_session(client, company) for company in involved}

        for done, api in enumerate(chosen, start=1):
            logger.info("[%d/%d] %s %s", done + 1, steps, api.index, api.name)
            for company, opened in sessions.items():
                if not api.supports(company):
                    continue
                outcome = run_routine(api, opened, targets)
                totals[f"{company}/{api.index}"] = outcome.rows
                report(
                    f"{api.index} {api.name} {company} {outcome.detail} ({done}/{len(chosen)})",
                    outcome.broken,
                )

        logger.info("[%d/%d] 마무리 쿼리", steps, steps)
        for target in targets:
            totals[f"{target.name}/쿼리"] = finish(target, report)

    return totals


def job(run: app.Run) -> app.Done:
    chosen = plan()
    run.begin(chosen.name)
    announce(chosen)

    def report_step(text: str, broken: bool) -> None:
        if broken:
            run.broke(text)
        else:
            run.step(text)

    totals = sweep(chosen.build, chosen.databases, report=report_step)
    summary, broken = summarize_totals(totals)
    return app.Done(summary, broken=bool(broken), note=f"데이터 쓰기 대상: {chosen.written_to}")


def main() -> int:
    start_logging()
    return app.start(FALLBACK_SYSTEM, logger, job)


if __name__ == "__main__":
    sys.exit(main())
