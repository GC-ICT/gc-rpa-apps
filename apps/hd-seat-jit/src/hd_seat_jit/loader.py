from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gc_rpa_core import config
from gc_rpa_core.db import DbEndpoint, cursor
from hd_seat_jit import sheet

EXCEL_SUFFIX = ".xlsx"
UNREADABLE_SUFFIX = ".xls"
LEFTOVER_SUFFIXES = (EXCEL_SUFFIX, UNREADABLE_SUFFIX, ".crdownload")

DELETE_ATTEMPTS = 3
DELETE_PAUSE = 0.5

logger = logging.getLogger(__name__)


class LoaderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    endpoint: DbEndpoint
    temp_table: str
    queries: tuple[str, ...]


def target(settings: config.RpaConfig) -> Target:
    database = config.usable_database(settings)
    return Target(
        endpoint=database.source,
        temp_table=database.tables[0],
        queries=database.queries,
    )


def workbooks(folder: Path) -> list[Path]:
    unreadable = sorted(path.name for path in folder.rglob(f"*{UNREADABLE_SUFFIX}"))
    if unreadable:
        raise LoaderError(f"{EXCEL_SUFFIX} 가 아니라 읽을 수 없습니다: {', '.join(unreadable)}")

    found = [path for path in folder.rglob(f"*{EXCEL_SUFFIX}") if path.is_file()]
    if not found:
        raise LoaderError(f"받은 엑셀이 없습니다: {folder}")
    return sorted(found, key=lambda path: path.stat().st_mtime)


def clear(folder: Path) -> int:
    leftovers = [
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in LEFTOVER_SUFFIXES
    ]
    return discard(leftovers)


def parsed(folder: Path, *, customer_code: str) -> list[sheet.Sheet]:
    pages = []
    for path in workbooks(folder):
        try:
            page = sheet.read(path, customer_code=customer_code)
        except Exception as exc:
            raise LoaderError(f"{path.name} 을 읽지 못했습니다: {exc}") from exc
        logger.info("      %s %d행 %s", path.name, len(page.rows), page.common)
        pages.append(page)
    return pages


def rows_of(pages: Sequence[sheet.Sheet]) -> list[tuple[Any, ...]]:
    return [row for page in pages for row in page.rows]


def insert_statement(table: str) -> str:
    placeholders = ", ".join(["%s"] * len(sheet.FIELDS))
    return f"INSERT INTO {table}\n  ({', '.join(sheet.FIELDS)})\nVALUES ({placeholders})"


def write(target: Target, rows: Sequence[tuple[Any, ...]]) -> int:
    if not rows:
        raise LoaderError("적재할 행이 없습니다")

    with cursor(target.endpoint, autocommit=False, as_dict=False) as opened:
        try:
            opened.execute(f"TRUNCATE TABLE {target.temp_table}")
            opened.executemany(insert_statement(target.temp_table), rows)
        except Exception as exc:
            raise LoaderError(f"{target.temp_table} 적재에 실패했습니다: {exc}") from exc

    logger.info("      %s %d행 적재", target.temp_table, len(rows))
    return len(rows)


def finish(target: Target) -> int:
    with cursor(target.endpoint, autocommit=True, as_dict=False) as opened:
        for order, query in enumerate(target.queries, start=1):
            try:
                opened.execute(query)
            except Exception as exc:
                raise LoaderError(f"{order}번째 마무리 쿼리에 실패했습니다: {exc}") from exc
            logger.info("      마무리 쿼리 %d/%d 실행", order, len(target.queries))

    return len(target.queries)


def thrown_away(path: Path) -> bool:
    for attempt in range(DELETE_ATTEMPTS):
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError as exc:
            if attempt + 1 == DELETE_ATTEMPTS:
                logger.warning("      %s 를 지우지 못했습니다: %s", path.name, exc)
            else:
                time.sleep(DELETE_PAUSE)
    return False


def discard(paths: Sequence[Path]) -> int:
    return sum(thrown_away(path) for path in paths)
