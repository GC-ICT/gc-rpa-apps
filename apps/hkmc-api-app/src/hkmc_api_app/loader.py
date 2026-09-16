from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from gc_rpa_core.db import DbEndpoint, cursor
from hkmc_api_app.common import Api, outdata, succeeded

DATABASE = "IT_Info"
SCHEMA = "dbo"
KST = timezone(timedelta(hours=9))

SPMON_COLUMN = "I_SPMON"
SPMON_INDEXES = ("014", "015")

logger = logging.getLogger(__name__)


class GerpError(RuntimeError):
    pass


class DatabaseError(RuntimeError):
    pass


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
            raise GerpError(f"응답이 실패했습니다: {result['outData']['E_IFMSG']}")
        parsed = outdata(result)
    except GerpError:
        raise
    except Exception as exc:
        raise GerpError(f"응답 봉투를 해석하지 못했습니다: {exc}") from exc

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
    spmon: str = "",
    endpoint: DbEndpoint | None = None,
) -> dict[str, int]:
    lists = unwrap(api, result)
    moment = collected_at()
    month = spmon if uses_spmon(api) else ""
    inserted: dict[str, int] = {}

    with cursor(endpoint, autocommit=False) as opened:
        for ordinal, key in zip(ordinals(api), api.out_keys, strict=True):
            table = temp_table(api.index, ordinal)
            rows = parameters(lists[key], moment=moment, company=company, spmon=month)
            if not rows:
                inserted[table] = 0
                continue
            try:
                opened.executemany(insert_statement(table, spmon=bool(month)), rows)
            except Exception as exc:
                raise DatabaseError(f"{table} 적재에 실패했습니다: {exc}") from exc
            inserted[table] = len(rows)
            logger.info("%s %d행 적재", table, len(rows))

    for ordinal in ordinals(api):
        run_procedure(procedure(api.index, ordinal), endpoint=endpoint)

    return inserted


def run_procedure(name: str, *, endpoint: DbEndpoint | None = None) -> bool:
    with cursor(endpoint, autocommit=True) as opened:
        opened.execute("SELECT OBJECT_ID(%s, 'P') AS id", (qualified(name),))
        row = opened.fetchone()
        if row is None or row["id"] is None:
            logger.info("%s 가 없어 건너뜁니다", name)
            return False
        try:
            opened.execute(f"EXEC {qualified(name)}")
        except Exception as exc:
            raise DatabaseError(f"{name} 실행에 실패했습니다: {exc}") from exc

    logger.info("%s 실행", name)
    return True
