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


def test_kill_browsers_does_nothing_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from gc_rpa_core import browser

    monkeypatch.setattr(browser.os, "name", "posix")
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_k: pytest.fail("윈도우가 아니면 죽이지 않습니다")
    )

    browser.kill_browsers()


def test_only_our_own_driver_is_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    from gc_rpa_core import browser

    called: list[list[str]] = []
    monkeypatch.setattr(browser.os, "name", "nt")
    monkeypatch.setattr(browser.subprocess, "run", lambda args, **_k: called.append(args))
    monkeypatch.setattr(browser, "OWN_DRIVERS", {4242})

    browser.kill_browsers()

    assert called == [["taskkill", "/F", "/T", "/PID", "4242"]]


def test_a_stranger_chrome_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    from gc_rpa_core import browser

    monkeypatch.setattr(browser.os, "name", "nt")
    monkeypatch.setattr(browser, "OWN_DRIVERS", set())
    monkeypatch.setattr(
        browser.subprocess, "run", lambda *_a, **_k: pytest.fail("남의 크롬은 건드리지 않습니다")
    )

    browser.kill_browsers()


def test_a_started_driver_is_remembered(monkeypatch: pytest.MonkeyPatch) -> None:
    from gc_rpa_core import browser

    class FakeService:
        process = type("Process", (), {"pid": 777})()

    class FakeDriver:
        service = FakeService()

    monkeypatch.setattr(browser, "OWN_DRIVERS", set())

    assert browser.remember_driver(FakeDriver()) == 777  # type: ignore[arg-type]
    assert 777 in browser.OWN_DRIVERS


def test_exit_cleanup_registers_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    import signal

    from gc_rpa_core import browser

    installed: list[int] = []
    monkeypatch.setattr(signal, "signal", lambda number, _handler: installed.append(number))
    monkeypatch.setattr(browser.atexit, "register", lambda _f: None)

    browser.clean_up_browsers_on_exit()

    assert signal.SIGTERM in installed
    assert signal.SIGINT in installed
