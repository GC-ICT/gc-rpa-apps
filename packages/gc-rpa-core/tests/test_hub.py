from typing import Any

import pytest

from gc_rpa_core import hub
from gc_rpa_core.env import MissingConfigError


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNALR_HUB_URL", "http://test-hub.invalid/testHub")
    monkeypatch.setenv("SIGNALR_GROUP", "test_group")
    monkeypatch.setenv("SIGNALR_SYSTEM", "test_system")
    monkeypatch.delenv("SIGNALR_METHOD", raising=False)
    monkeypatch.delenv("SIGNALR_TIMEOUT", raising=False)


@pytest.fixture
def delivered(monkeypatch: pytest.MonkeyPatch) -> list[list[Any]]:
    captured: list[list[Any]] = []

    async def fake(arguments: list[Any], *, seconds: float) -> None:
        captured.append(arguments)

    monkeypatch.setattr(hub, "deliver", fake)
    return captured


def test_defaults() -> None:
    assert hub.method() == "SendMessage"
    assert hub.group() == "test_group"
    assert hub.system() == "test_system"
    assert hub.timeout() == 30.0


def test_hub_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNALR_HUB_URL")

    with pytest.raises(MissingConfigError):
        hub.hub_url()


def test_send_passes_four_strings(delivered: list[list[Any]]) -> None:
    hub.send("INFO", "본문")

    assert delivered == [["test_group", "test_system", "INFO", "본문"]]


def test_report_success_uses_info(delivered: list[list[Any]]) -> None:
    hub.report(success=True, message="PU010 완료")

    assert delivered[0] == ["test_group", "test_system", "INFO", "PU010 완료"]


def test_report_failure_uses_error(delivered: list[list[Any]]) -> None:
    hub.report(success=False, message="LoginError: 요소 없음")

    assert delivered[0] == ["test_group", "test_system", "ERROR", "LoginError: 요소 없음"]


def test_name_overrides_system(delivered: list[list[Any]]) -> None:
    hub.report(success=True, message="완료", name="mobisAS2")

    assert delivered[0][1] == "mobisAS2"


def test_method_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNALR_METHOD", "ReportResult")

    assert hub.method() == "ReportResult"
