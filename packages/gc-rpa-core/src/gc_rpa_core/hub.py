from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pysignalr.client import SignalRClient

from gc_rpa_core.env import optional_env, require_env

HUB_URL_ENV = "SIGNALR_HUB_URL"
GROUP_ENV = "SIGNALR_GROUP"
JOIN_METHOD_ENV = "SIGNALR_JOIN_METHOD"
RESULT_METHOD_ENV = "SIGNALR_RESULT_METHOD"
TIMEOUT_ENV = "SIGNALR_TIMEOUT"

DEFAULT_JOIN_METHOD = "JoinGroup"
DEFAULT_RESULT_METHOD = "SendResult"
DEFAULT_TIMEOUT = 30.0


class HubError(RuntimeError):
    pass


def hub_url() -> str:
    return require_env(HUB_URL_ENV)


def group() -> str:
    return optional_env(GROUP_ENV)


def join_method() -> str:
    return optional_env(JOIN_METHOD_ENV, DEFAULT_JOIN_METHOD)


def result_method() -> str:
    return optional_env(RESULT_METHOD_ENV, DEFAULT_RESULT_METHOD)


def timeout() -> float:
    return float(optional_env(TIMEOUT_ENV, str(DEFAULT_TIMEOUT)))


async def invoke(calls: Sequence[tuple[str, list[Any]]], *, seconds: float) -> None:
    client = SignalRClient(hub_url())
    opened = asyncio.Event()

    async def mark_open() -> None:
        opened.set()

    client.on_open(mark_open)

    runner = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(opened.wait(), seconds)
        for method, arguments in calls:
            await client.send(method, arguments)
    except TimeoutError as exc:
        raise HubError(f"{seconds}초 안에 허브에 연결하지 못했다: {hub_url()}") from exc
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


def send(method: str, arguments: list[Any], *, join: bool = True) -> None:
    calls: list[tuple[str, list[Any]]] = []
    if join and group():
        calls.append((join_method(), [group()]))
    calls.append((method, arguments))
    asyncio.run(invoke(calls, seconds=timeout()))


def report(
    *, job: str, success: bool, message: str = "", detail: dict[str, Any] | None = None
) -> None:
    payload: dict[str, Any] = {
        "group": group(),
        "job": job,
        "success": success,
        "message": message,
        "finishedAt": datetime.now(UTC).isoformat(),
    }
    if detail:
        payload["detail"] = detail
    send(result_method(), [payload])
