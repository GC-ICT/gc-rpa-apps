from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from gc_rpa_core.db import DbEndpoint, connect
from hkmc_api_app.common import Api, outdata, succeeded

DATABASE = "IT_Info"
SCHEMA = "dbo"
KST = timezone(timedelta(hours=9))

SPMON_COLUMN = "I_SPMON"
SPMON_INDEXES = ("014", "015")

logger = logging.getLogger(__name__)


class ResponseError(RuntimeError):
    pass


class DatabaseError(RuntimeError):
    pass


@dataclass
class Writer:
    rows: Any
    procedures: Any

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


@contextmanager
def writer(endpoint: DbEndpoint | None = None) -> Iterator[Writer]:
    with (
        connect(endpoint, autocommit=False) as rows,
        connect(endpoint, autocommit=True) as procedures,
    ):
        yield Writer(rows=rows, procedures=procedures)


def qualified(name: str) -> str:
    return f"[{DATABASE}].[{SCHEMA}].[{name}]"


def ordinals(api: Api) -> tuple[str, ...]:
    if len(api.out_keys) == 1:
        return ("",)
    return tuple(str(position) for position, _ in enumerate(api.out_keys, start=1))


def temp_table(index: str, ordinal: str = "") -> str:
    return f"Z_API_{index}{ordinal}_TEMP"


def procedure(index: str, ordinal: str = "") -> str:
    return f"Z_API_{index}{ordinal}_PROC"


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
    return f"INSERT INTO {qualified(table)}\n  ({', '.join(columns)})\nVALUES ({placeholders})"


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


def load(
    api: Api,
    result: Any,
    *,
    company: str,
    writer: Writer,
    spmon: str = "",
) -> dict[str, int]:
    return load_rows(api, unwrap(api, result), company=company, writer=writer, spmon=spmon)


def load_rows(
    api: Api,
    lists: dict[str, list[dict[str, Any]]],
    *,
    company: str,
    writer: Writer,
    spmon: str = "",
) -> dict[str, int]:
    moment = collected_at()
    month = spmon if uses_spmon(api) else ""
    inserted: dict[str, int] = {}

    with writer.rows_cursor() as opened:
        for ordinal, key in zip(ordinals(api), api.out_keys, strict=True):
            table = temp_table(api.index, ordinal)
            rows = parameters(lists[key], moment=moment, company=company, spmon=month)
            if not rows:
                inserted[table] = 0
                continue
            try:
                opened.executemany(insert_statement(table, spmon=bool(month)), rows)
            except Exception as exc:
                raise DatabaseError(f"{table} 데이터 쓰기에 실패했습니다: {exc}") from exc
            inserted[table] = len(rows)
            logger.info("      %s %d행 데이터 쓰기", table, len(rows))

    for ordinal in ordinals(api):
        run_procedure(procedure(api.index, ordinal), moment.date(), writer=writer)

    return inserted


def run_procedure(name: str, run_dt: date, *, writer: Writer) -> bool:
    with writer.procedure_cursor() as opened:
        opened.execute("SELECT OBJECT_ID(%s, 'P')", (qualified(name),))
        row = opened.fetchone()
        if row is None or row[0] is None:
            logger.info("      %s 가 없어 건너뜁니다", name)
            return False
        try:
            opened.execute(f"EXEC {qualified(name)} @run_dt = %s", (run_dt,))
        except Exception as exc:
            raise DatabaseError(f"{name} 실행에 실패했습니다: {exc}") from exc

    logger.info("      %s 실행", name)
    return True
