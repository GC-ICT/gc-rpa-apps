from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

TOKEN = re.compile(r"\{(\w+)\}")


class UnknownTokenError(LookupError):
    pass


def bind(statement: str, values: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
    found: list[Any] = []

    def take(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise UnknownTokenError(f"{{{name}}} 에 넣을 값이 없습니다")
        found.append(values[name])
        return "%s"

    return TOKEN.sub(take, statement), tuple(found)
