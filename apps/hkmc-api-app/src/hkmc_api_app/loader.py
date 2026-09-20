from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from gc_rpa_core.config import RpaDatabase
from gc_rpa_core.db import DbEndpoint, connect
from gc_rpa_core.statement import bind
from hkmc_api_app.common import Api, outdata, succeeded

DATABASE = "IT_Info"
SCHEMA = "dbo"
KST = timezone(timedelta(hours=9))

SPMON_COLUMN = "I_SPMON"
SPMON_INDEXES = ("014", "015")

RUN_DT = "{run_dt}"
TABLE_PATTERN = re.compile(r"Z_API_(\d{3})(\d?)_TEMP", re.IGNORECASE)
NAME_PATTERN = re.compile(r"^[\w.\[\]]+$")

logger = logging.getLogger(__name__)


class ResponseError(RuntimeError):
    pass


class DatabaseError(RuntimeError):
    pass


@dataclass
class Writer:
    rows: Any
    procedures: Any
    name: str = ""
    tables: dict[str, str] = field(default_factory=dict)
    queries: tuple[str, ...] = ()

    @contextmanager
    def rows_cursor(self) -> Iterator[Any]:
        opened = self.rows.cursor(as_dict=True)
        try:
            yield opened
        except BaseException:
            self.rows.rollback()
            raise
        else:
            self.rows.commit()
        finally:
            opened.close()

    @contextmanager
    def procedure_cursor(self) -> Iterator[Any]:
        opened = self.procedures.cursor(as_dict=False)
        try:
            yield opened
        finally:
            opened.close()


def label(endpoint: DbEndpoint) -> str:
    return f"{endpoint.host}/{endpoint.database}" if endpoint.host else endpoint.database


def qualified(name: str, database: str = DATABASE) -> str:
    parts = [part.strip().strip("[]") for part in name.split(".") if part.strip()]
    if len(parts) >= 3:
        return "[{}].[{}].[{}]".format(*parts[-3:])
    if len(parts) == 2:
        return f"[{database or DATABASE}].[{parts[0]}].[{parts[1]}]"
    return f"[{database or DATABASE}].[{SCHEMA}].[{parts[0]}]"


def table_key(name: str) -> str:
    found = TABLE_PATTERN.search(name)
    return f"{found.group(1)}{found.group(2)}" if found else ""


def tables_of(database: RpaDatabase) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in database.tables:
        key = table_key(name)
        if not key:
            logger.warning("      %s 의 %s 은 API 번호를 읽을 수 없습니다", database.name, name)
            continue
        found[key] = qualified(name, database.source.database)
    return found


def statements_of(database: RpaDatabase) -> tuple[str, ...]:
    built = []
    for query in database.queries:
        if NAME_PATTERN.match(query):
            built.append(f"EXEC {qualified(query, database.source.database)} @run_dt = {RUN_DT}")
        else:
            built.append(query)
    return tuple(built)


@contextmanager
def writer(database: RpaDatabase) -> Iterator[Writer]:
    with (
        connect(database.source, autocommit=False) as rows,
        connect(database.source, autocommit=True) as procedures,
    ):
        yield Writer(
            rows=rows,
            procedures=procedures,
            name=database.name or label(database.source),
            tables=tables_of(database),
            queries=statements_of(database),
        )


@contextmanager
def writers(databases: Sequence[RpaDatabase]) -> Iterator[tuple[Writer, ...]]:
    with ExitStack() as stack:
        opened = []
        for database in databases:
            try:
                opened.append(stack.enter_context(writer(database)))
            except Exception as exc:
                shown = database.name or label(database.source)
                logger.warning("      %s 에 붙지 못해 건너뜁니다: %s", shown, exc)
        if not opened:
            raise DatabaseError("데이터를 쓸 수 있는 DB 가 없습니다")
        yield tuple(opened)


def ordinals(api: Api) -> tuple[str, ...]:
    if len(api.out_keys) == 1:
        return ("",)
    return tuple(str(position) for position, _ in enumerate(api.out_keys, start=1))


def keys(api: Api) -> tuple[str, ...]:
    return tuple(f"{api.index}{ordinal}" for ordinal in ordinals(api))


def collected_at() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def unwrap(api: Api, result: Any) -> dict[str, list[dict[str, Any]]]:
    try:
        if not succeeded(result):
            raise ResponseError(f"응답이 실패했습니다: {result['outData']['E_IFMSG']}")
        parsed = outdata(result)
    except ResponseError:
        raise
    except Exception as exc:
        raise ResponseError(f"응답 본문을 해석하지 못했습니다: {exc}") from exc

    return {key: parsed.get(key) or [] for key in api.out_keys}


def insert_statement(table: str, *, spmon: bool) -> str:
    columns = ["api_dt", "api_idx", "api_value", "api_company"]
    if spmon:
        columns.append(SPMON_COLUMN)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table}\n  ({', '.join(columns)})\nVALUES ({placeholders})"


def parameters(
    rows: list[dict[str, Any]], *, moment: datetime, company: str, spmon: str
) -> list[tuple[Any, ...]]:
    built = []
    for index, row in enumerate(rows):
        values: list[Any] = [
            moment,
            index,
            json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            company,
        ]
        if spmon:
            values.append(spmon)
        built.append(tuple(values))
    return built


def uses_spmon(api: Api) -> bool:
    return api.index in SPMON_INDEXES


def tag(writer: Writer, message: str) -> str:
    return f"{writer.name} {message}" if writer.name else message


def load(
    api: Api,
    result: Any,
    *,
    company: str,
    targets: Sequence[Writer],
    spmon: str = "",
) -> dict[str, int]:
    return load_rows(api, unwrap(api, result), company=company, targets=targets, spmon=spmon)


def write_rows(
    api: Api,
    lists: dict[str, list[dict[str, Any]]],
    *,
    company: str,
    moment: datetime,
    spmon: str,
    writer: Writer,
) -> dict[str, int]:
    inserted: dict[str, int] = {}

    with writer.rows_cursor() as opened:
        for key, out_key in zip(keys(api), api.out_keys, strict=True):
            table = writer.tables.get(key)
            if table is None:
                logger.info("      %s", tag(writer, f"에 {key} 테이블이 없어 건너뜁니다"))
                continue
            rows = parameters(lists[out_key], moment=moment, company=company, spmon=spmon)
            if not rows:
                inserted[key] = 0
                continue
            try:
                opened.executemany(insert_statement(table, spmon=bool(spmon)), rows)
            except Exception as exc:
                raise DatabaseError(f"{table} 데이터 쓰기에 실패했습니다: {exc}") from exc
            inserted[key] = len(rows)
            logger.info("      %s %d행 데이터 쓰기", tag(writer, table), len(rows))

    return inserted


def load_rows(
    api: Api,
    lists: dict[str, list[dict[str, Any]]],
    *,
    company: str,
    targets: Sequence[Writer],
    spmon: str = "",
) -> dict[str, int]:
    moment = collected_at()
    month = spmon if uses_spmon(api) else ""
    inserted: dict[str, int] = {}
    failures: list[str] = []

    for writer in targets:
        try:
            written = write_rows(
                api, lists, company=company, moment=moment, spmon=month, writer=writer
            )
        except Exception as exc:
            logger.warning("      %s", tag(writer, str(exc)))
            failures.append(tag(writer, str(exc)))
            continue
        inserted = {**inserted, **written}

    if failures:
        raise DatabaseError(", ".join(failures))

    return inserted


def bound(query: str, run_dt: date) -> tuple[str, tuple[Any, ...]]:
    return bind(query, {"run_dt": run_dt})


def run_queries(writer: Writer, run_dt: date) -> int:
    for order, query in enumerate(writer.queries, start=1):
        statement, params = bound(query, run_dt)
        with writer.procedure_cursor() as opened:
            try:
                if params:
                    opened.execute(statement, params)
                else:
                    opened.execute(statement)
            except Exception as exc:
                raise DatabaseError(
                    tag(writer, f"{order}번째 쿼리 실행에 실패했습니다: {exc}")
                ) from exc
        logger.info("      %s", tag(writer, f"쿼리 {order}/{len(writer.queries)} 실행"))

    return len(writer.queries)
