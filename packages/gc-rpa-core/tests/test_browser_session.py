import threading
import time
from typing import Any

import pytest
from selenium.common.exceptions import InvalidSessionIdException, TimeoutException
from urllib3.exceptions import MaxRetryError

from gc_rpa_core.browser import RendererHangError, call_cdp, causes, session_dead


class FakeDriver:
    def __init__(self, behaviour: Any) -> None:
        self.behaviour = behaviour
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute_cdp_cmd(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((command, params))
        if callable(self.behaviour):
            return self.behaviour()
        return self.behaviour


def test_session_dead_spots_a_wrapped_cause() -> None:
    try:
        try:
            raise InvalidSessionIdException("invalid session id")
        except InvalidSessionIdException as inner:
            raise RuntimeError("PDF 저장 실패") from inner
    except RuntimeError as outer:
        assert session_dead(outer)


def test_session_dead_spots_a_message_marker() -> None:
    assert session_dead(RuntimeError("Chrome not reachable"))


def test_session_dead_ignores_an_ordinary_failure() -> None:
    assert not session_dead(TimeoutException("요소를 찾지 못했습니다"))


def test_session_dead_survives_a_cycle() -> None:
    first = RuntimeError("첫째")
    second = RuntimeError("둘째")
    first.__context__ = second
    second.__context__ = first

    assert not session_dead(first)


def test_session_dead_spots_urllib3_pool_failure() -> None:
    assert session_dead(MaxRetryError(pool=None, url="/session"))  # type: ignore[arg-type]


def test_causes_walks_the_chain_once() -> None:
    inner = ValueError("안쪽")
    outer = RuntimeError("바깥")
    outer.__cause__ = inner

    assert list(causes(outer)) == [outer, inner]


def test_call_cdp_returns_the_result() -> None:
    driver = FakeDriver({"data": "abc"})

    assert call_cdp(driver, "Page.printToPDF", {"scale": 1}) == {"data": "abc"}  # type: ignore[arg-type]
    assert driver.calls == [("Page.printToPDF", {"scale": 1})]


def test_call_cdp_returns_an_empty_dict_when_the_command_answers_nothing() -> None:
    driver = FakeDriver(None)

    assert call_cdp(driver, "Emulation.setEmulatedMedia", {}) == {}  # type: ignore[arg-type]


def test_call_cdp_reraises_the_command_error() -> None:
    def boom() -> dict[str, Any]:
        raise InvalidSessionIdException("invalid session id")

    with pytest.raises(InvalidSessionIdException):
        call_cdp(FakeDriver(boom), "Page.printToPDF", {})  # type: ignore[arg-type]


def test_call_cdp_gives_up_when_the_renderer_stops_answering() -> None:
    release = threading.Event()

    def hang() -> dict[str, Any]:
        release.wait(5)
        return {}

    try:
        with pytest.raises(RendererHangError, match="렌더러 무응답"):
            call_cdp(FakeDriver(hang), "Page.printToPDF", {}, timeout=0.2)  # type: ignore[arg-type]
    finally:
        release.set()


def test_call_cdp_does_not_wait_for_a_hung_command_to_finish() -> None:
    release = threading.Event()

    def hang() -> dict[str, Any]:
        release.wait(5)
        return {}

    started = time.monotonic()
    try:
        with pytest.raises(RendererHangError):
            call_cdp(FakeDriver(hang), "Page.printToPDF", {}, timeout=0.2)  # type: ignore[arg-type]
        assert time.monotonic() - started < 2.0
    finally:
        release.set()
