from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gc_rpa_core.db import cursor

PROCEDURE = "ITM250_Schedule"
SELECT_TYPE = "GetActProgram"
CALL = f"EXEC {PROCEDURE} @_Select_type = %s, @_schedule_id = %s"

TRUE_FLAGS = ("Y", "1", "T", "TRUE")


def flag(value: str) -> bool:
    return value.strip().upper() in TRUE_FLAGS


def text(row: dict[str, Any], column: str) -> str:
    value = row.get(column)
    return "" if value is None else str(value).strip()


@dataclass(frozen=True)
class RpaConfig:
    url: str
    user_id: str
    password: str
    otp: str
    use_otp: bool
    move_path: str


def load(schedule_id: str) -> RpaConfig:
    with cursor() as opened:
        opened.execute(CALL, (SELECT_TYPE, schedule_id))
        row = opened.fetchone()

    if row is None:
        raise LookupError(f"{PROCEDURE} 에 schedule_id={schedule_id!r} 설정이 없다")

    return RpaConfig(
        url=text(row, "rpa_site"),
        user_id=text(row, "rpa_id"),
        password=text(row, "rpa_pw"),
        otp=text(row, "rpa_opt"),
        use_otp=flag(text(row, "opt_yn")),
        move_path=text(row, "file_move_path"),
    )
