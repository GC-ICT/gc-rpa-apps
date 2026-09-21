import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint
from hd_seat_jit import vpn


def settings() -> RpaConfig:
    empty = DbEndpoint("", None, "", "", "")
    return RpaConfig("t", "https://vpn.invalid", "myid", "mypw", "", False, "", "", empty, empty)


class FakeSwitch:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def window(self, handle: str) -> None:
        self.driver.focused = handle


class FakeDriver:
    def __init__(self, handles: tuple[str, ...] = ("main",)) -> None:
        self.window_handles = list(handles)
        self.current_window_handle = handles[0]
        self.focused = handles[0]
        self.closed: list[str] = []
        self.switch_to = FakeSwitch(self)
        self.visited: list[str] = []

    def get(self, url: str) -> None:
        self.visited.append(url)

    def close(self) -> None:
        self.closed.append(self.focused)

    def find_elements(self, by: str, locator: str) -> list[Any]:
        return []


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    pressed: list[tuple[str, str]] = []
    monkeypatch.setattr(vpn, "click", lambda _d, by, what: pressed.append((by, what)))
    monkeypatch.setattr(vpn, "click_if_shown", lambda *_a: 0)
    monkeypatch.setattr(vpn, "fill", lambda _d, by, what, _v: pressed.append((by, what)))
    monkeypatch.setattr(vpn, "wait_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(vpn, "allow_native_app", lambda: None)
    monkeypatch.setattr(vpn.time, "sleep", lambda _s: None)
    return pressed


def listing(monkeypatch: pytest.MonkeyPatch, output: str) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(args=[], returncode=0, stdout=output),
    )


def test_a_live_client_is_noticed(monkeypatch: pytest.MonkeyPatch) -> None:
    listing(monkeypatch, "f5vpn.exe   1234 Console")

    assert vpn.running() is True


def test_no_client_is_noticed(monkeypatch: pytest.MonkeyPatch) -> None:
    listing(monkeypatch, "정보: 실행 중인 작업이 없습니다.")

    assert vpn.running() is False


def test_a_missing_tasklist_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("tasklist 없음")

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(vpn.VpnError, match="상태를 확인하지 못했습니다"):
        vpn.running()


def test_an_open_connection_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(vpn, "running", lambda: True)

    def never(*_a: Any, **_k: Any) -> None:
        raise AssertionError("이미 붙어 있으면 접속을 시도하면 안 됩니다")

    monkeypatch.setattr(vpn.config, "load", never)

    with caplog.at_level("INFO", logger=vpn.__name__):
        vpn.connect(portal_schedule_id="18", otp_schedule_id="17", downloads=tmp_path)

    assert "건너뜁니다" in caplog.text


def test_the_login_form_is_filled_then_extra_windows_closed(quiet: Any) -> None:
    driver = FakeDriver(("main", "popup"))

    vpn.sign_in(driver, settings())

    assert [what for _, what in quiet] == [vpn.ID_INPUT, vpn.PASSWORD_INPUT, vpn.SUBMIT_BUTTON]
    assert driver.closed == ["popup"]
    assert driver.focused == "main"


def test_the_code_goes_into_the_password_box(quiet: Any) -> None:
    vpn.submit_code(FakeDriver(), "483920")

    assert [what for _, what in quiet] == [vpn.PASSWORD_INPUT, vpn.SUBMIT_BUTTON]


def test_a_client_that_never_starts_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, quiet: Any
) -> None:
    states = iter([False, False])
    monkeypatch.setattr(vpn, "running", lambda: next(states))
    monkeypatch.setattr(vpn.config, "load", lambda _id: settings())

    class FakeBox:
        def mark(self) -> None:
            return None

        def read(self, **_k: Any) -> str:
            return "483920"

    @contextmanager
    def fake_mailbox(*_a: Any, **_k: Any) -> Any:
        yield FakeBox()

    @contextmanager
    def fake_chrome(*_a: Any, **_k: Any) -> Any:
        yield FakeDriver()

    monkeypatch.setattr(vpn.otp, "mailbox", fake_mailbox)
    monkeypatch.setattr(vpn, "chrome", fake_chrome)

    with pytest.raises(vpn.VpnError, match="붙지 못했습니다"):
        vpn.connect(portal_schedule_id="18", otp_schedule_id="17", downloads=tmp_path)
