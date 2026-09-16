from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pysignalr.client import SignalRClient

from gc_rpa_core.env import optional_env, require_env

HUB_URL_ENV = "SIGNALR_HUB_URL"
GROUP_ENV = "SIGNALR_GROUP"
SYSTEM_ENV = "SIGNALR_SYSTEM"
METHOD_ENV = "SIGNALR_METHOD"
TIMEOUT_ENV = "SIGNALR_TIMEOUT"

DEFAULT_METHOD = "SendMessageToGroup"
DEFAULT_TIMEOUT = 30.0

INFO_LEVEL = "INFO"
ERROR_LEVEL = "ERROR"

STARTED = "시작합니다"
FINISHED = "완료했습니다"

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


class Session:
    def __init__(
        self, client: SignalRClient | None, loop: asyncio.AbstractEventLoop | None
    ) -> None:
        self.client = client
        self.loop = loop

    @property
    def connected(self) -> bool:
        return self.client is not None and self.loop is not None

    def send(self, level: str, message: str, *, name: str = "") -> None:
        arguments: list[Any] = [group(), name or system(), level, message]
        if not self.connected:
            logger.warning("허브에 연결되어 있지 않아 보내지 못했습니다: %r", tuple(arguments))
            return

        assert self.client is not None and self.loop is not None
        logger.debug("허브로 보냅니다 %s%r", method(), tuple(arguments))
        future = asyncio.run_coroutine_threadsafe(self.client.send(method(), arguments), self.loop)
        future.result(timeout())

    def started(self, *, name: str = "") -> None:
        self.send(INFO_LEVEL, STARTED, name=name)

    def finished(self, *, message: str, name: str = "") -> None:
        self.send(INFO_LEVEL, f"{FINISHED}: {message}", name=name)

    def failed(self, *, message: str, name: str = "") -> None:
        self.send(ERROR_LEVEL, message, name=name)


class HubHandler(logging.Handler):
    def __init__(self, session: Session, *, name: str = "") -> None:
        super().__init__()
        self.session = session
        self.system_name = name

    def emit(self, record: logging.LogRecord) -> None:
        if not self.session.connected:
            return
        level = ERROR_LEVEL if record.levelno >= logging.ERROR else INFO_LEVEL
        try:
            self.session.send(level, record.getMessage(), name=self.system_name)
        except Exception:
            self.handleError(record)


@contextmanager
def forwarding(session: Session, *loggers: logging.Logger, name: str = "") -> Iterator[HubHandler]:
    handler = HubHandler(session, name=name)
    for target in loggers:
        target.addHandler(handler)
    try:
        yield handler
    finally:
        for target in loggers:
            target.removeHandler(handler)


async def cancel_pending() -> bool:
    pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    if not pending:
        return False
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    return True


async def shutdown() -> None:
    while await cancel_pending():
        pass
    await asyncio.get_running_loop().shutdown_asyncgens()
    await cancel_pending()


@contextmanager
def session(*, seconds: float | None = None) -> Iterator[Session]:
    limit = timeout() if seconds is None else seconds
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    client = SignalRClient(hub_url())
    opened = threading.Event()

    async def mark_open() -> None:
        opened.set()

    running: list[asyncio.Task[None]] = []

    async def start_runner() -> None:
        running.append(asyncio.create_task(client.run()))

    client.on_open(mark_open)

    try:
        asyncio.run_coroutine_threadsafe(start_runner(), loop).result(limit)
        if opened.wait(limit):
            yield Session(client, loop)
        else:
            logger.warning("%s초 안에 허브에 연결하지 못했습니다: %s", limit, hub_url())
            yield Session(None, None)
    finally:
        try:
            asyncio.run_coroutine_threadsafe(shutdown(), loop).result(limit)
        except Exception as exc:
            logger.debug("허브 연결 정리 중 무시한 오류: %s", exc)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=limit)
        loop.close()


def send(level: str, message: str, *, name: str = "") -> None:
    with session() as opened:
        opened.send(level, message, name=name)


def started(*, name: str = "") -> None:
    send(INFO_LEVEL, STARTED, name=name)


def finished(*, message: str, name: str = "") -> None:
    send(INFO_LEVEL, f"{FINISHED}: {message}", name=name)


def failed(*, message: str, name: str = "") -> None:
    send(ERROR_LEVEL, message, name=name)
