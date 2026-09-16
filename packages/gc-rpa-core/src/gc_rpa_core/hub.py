from __future__ import annotations

import asyncio
import logging
from typing import Any

from pysignalr.client import SignalRClient

from gc_rpa_core.env import optional_env, require_env

HUB_URL_ENV = "SIGNALR_HUB_URL"
GROUP_ENV = "SIGNALR_GROUP"
SYSTEM_ENV = "SIGNALR_SYSTEM"
METHOD_ENV = "SIGNALR_METHOD"
TIMEOUT_ENV = "SIGNALR_TIMEOUT"

DEFAULT_METHOD = "SendMessage"
DEFAULT_TIMEOUT = 30.0

INFO_LEVEL = "INFO"
ERROR_LEVEL = "ERROR"

logger = logging.getLogger(__name__)


class HubError(RuntimeError):
    pass


def hub_url() -> str:
    return require_env(HUB_URL_ENV)


def group() -> str:
    return optional_env(GROUP_ENV)


def system() -> str:
    return optional_env(SYSTEM_ENV)


def method() -> str:
    return optional_env(METHOD_ENV, DEFAULT_METHOD)


def timeout() -> float:
    return float(optional_env(TIMEOUT_ENV, str(DEFAULT_TIMEOUT)))


async def deliver(arguments: list[Any], *, seconds: float) -> None:
    client = SignalRClient(hub_url())
    opened = asyncio.Event()

    async def mark_open() -> None:
        opened.set()

    client.on_open(mark_open)

    runner = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(opened.wait(), seconds)
        await client.send(method(), arguments)
    except TimeoutError as exc:
        raise HubError(f"{seconds}초 안에 허브에 연결하지 못했다: {hub_url()}") from exc
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)


def send(level: str, message: str, *, name: str = "") -> None:
    arguments = [group(), name or system(), level, message]
    logger.debug("허브 전송 %s%r", method(), tuple(arguments))
    asyncio.run(deliver(arguments, seconds=timeout()))


def report(*, success: bool, message: str, name: str = "") -> None:
    send(INFO_LEVEL if success else ERROR_LEVEL, message, name=name)
