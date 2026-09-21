from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gc_rpa_core.db import DbEndpoint, cursor

PROCEDURE = "ITM250_Schedule"
SELECT_TYPE = "GetActProgram"
DATABASE_SELECT_TYPE = "GetActDatabase"
PASSWORD_SELECT_TYPE = "SetRpaPassword"
CALL = f"EXEC {PROCEDURE} @_Select_type = %s, @_schedule_id = %s"
DATABASE_CALL = f"EXEC {PROCEDURE} @_Select_type = %s, @_actprg_id = %s"
PASSWORD_CALL = f"EXEC {PROCEDURE} @_Select_type = %s, @_schedule_id = %s, @_rpa_pw = %s"

TRUE_FLAGS = ("Y", "1", "T", "TRUE")
TABLE_SEPARATOR = ","
QUERY_SEPARATOR = ";"


def flag(value: str) -> bool:
    return value.strip().upper() in TRUE_FLAGS


def items(value: str, separator: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(separator) if part.strip())


def text(row: dict[str, Any], column: str) -> str:
    value = row.get(column)
    return "" if value is None else str(value).strip()


def number(row: dict[str, Any], column: str) -> int | None:
    value = row.get(column)
    return None if value in (None, "") else int(value)


def endpoint(row: dict[str, Any], prefix: str) -> DbEndpoint:
    return DbEndpoint(
        host=text(row, f"{prefix}_host"),
        port=number(row, f"{prefix}_port"),
        database=text(row, f"{prefix}_db_nm"),
        user=text(row, f"{prefix}_id"),
        password=text(row, f"{prefix}_pw"),
    )


@dataclass(frozen=True)
class RpaConfig:
    name: str
    url: str
    user_id: str
    password: str
    otp: str
    use_otp: bool
    move_path: str
    exe_name: str
    source: DbEndpoint
    target: DbEndpoint
    actprg_id: str = ""


@dataclass(frozen=True)
class RpaDatabase:
    name: str
    source: DbEndpoint
    target: DbEndpoint
    tables: tuple[str, ...] = ()
    queries: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.name or self.source.label

    @property
    def complaint(self) -> str:
        if not self.source.configured:
            return f"{self.label} 의 접속정보가 비어 있습니다"
        if not self.tables:
            return f"{self.label} 의 temp_table 이 비어 있습니다"
        if not self.queries:
            return f"{self.label} 의 act_query 가 비어 있습니다"
        return ""


def load(schedule_id: str) -> RpaConfig:
    with cursor() as opened:
        opened.execute(CALL, (SELECT_TYPE, schedule_id))
        row = opened.fetchone()

    if row is None:
        raise LookupError(f"{PROCEDURE} 에 schedule_id={schedule_id!r} 설정이 없습니다")

    return RpaConfig(
        name=text(row, "actprg_nm"),
        url=text(row, "rpa_site"),
        user_id=text(row, "rpa_id"),
        password=text(row, "rpa_pw"),
        otp=text(row, "rpa_opt"),
        use_otp=flag(text(row, "opt_yn")),
        move_path=text(row, "file_move_path"),
        exe_name=text(row, "file_nm"),
        source=endpoint(row, "source"),
        target=endpoint(row, "target"),
        actprg_id=text(row, "actprg_id"),
    )


def save_password(schedule_id: str, password: str) -> None:
    with cursor(autocommit=True) as opened:
        opened.execute(PASSWORD_CALL, (PASSWORD_SELECT_TYPE, schedule_id, password))


def usable_database(settings: RpaConfig) -> RpaDatabase:
    databases = load_databases(settings.actprg_id)
    filled = next((database for database in databases if not database.complaint), None)
    if filled is None:
        raise LookupError(
            f"{PROCEDURE} 의 actprg_id={settings.actprg_id} 에 쓸 수 있는 DB 가 없습니다 "
            f"({len(databases)}행): " + " / ".join(database.complaint for database in databases)
        )
    return filled


def load_databases(actprg_id: str) -> tuple[RpaDatabase, ...]:
    with cursor() as opened:
        opened.execute(DATABASE_CALL, (DATABASE_SELECT_TYPE, actprg_id))
        rows = opened.fetchall()

    if not rows:
        raise LookupError(f"{PROCEDURE} 에 actprg_id={actprg_id!r} 의 DB 설정이 없습니다")

    return tuple(
        RpaDatabase(
            name=text(row, "source_db") or text(row, "source_db_nm"),
            source=endpoint(row, "source"),
            target=endpoint(row, "target"),
            tables=items(text(row, "temp_table"), TABLE_SEPARATOR),
            queries=items(text(row, "act_query"), QUERY_SEPARATOR),
        )
        for row in rows
    )
