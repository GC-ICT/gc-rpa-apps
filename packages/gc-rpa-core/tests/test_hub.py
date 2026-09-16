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


class FakeClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[Any]]] = []

    async def send(self, target: str, arguments: list[Any]) -> None:
        self.sent.append((target, arguments))


@pytest.fixture
def connected(monkeypatch: pytest.MonkeyPatch) -> Any:
    client = FakeClient()

    def run_threadsafe(coroutine: Any, loop: Any) -> Any:
        import asyncio

        class Done:
            def result(self, _: float) -> None:
                asyncio.new_event_loop().run_until_complete(coroutine)

        return Done()

    monkeypatch.setattr(hub.asyncio, "run_coroutine_threadsafe", run_threadsafe)
    return hub.Session(client, object()), client  # type: ignore[arg-type]


def test_defaults() -> None:
    assert hub.method() == "SendMessageToGroup"
    assert hub.group() == "test_group"
    assert hub.system() == "test_system"
    assert hub.timeout() == 30.0


def test_hub_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNALR_HUB_URL")

    with pytest.raises(MissingConfigError):
        hub.hub_url()


def test_send_passes_group_system_level_message(connected: Any) -> None:
    opened, client = connected

    opened.send("INFO", "본문")

    assert client.sent == [("SendMessageToGroup", ["test_group", "test_system", "INFO", "본문"])]


def test_started_sends_info(connected: Any) -> None:
    opened, client = connected

    opened.started()

    assert client.sent[0][1] == ["test_group", "test_system", "INFO", "시작합니다"]


def test_finished_prefixes_message(connected: Any) -> None:
    opened, client = connected

    opened.finished(message="a.xlsx → D:/x")

    assert client.sent[0][1][3] == "완료했습니다: a.xlsx → D:/x"


def test_failed_sends_error(connected: Any) -> None:
    opened, client = connected

    opened.failed(message="LoginError: 요소를 찾지 못했습니다")

    assert client.sent[0][1][2] == "ERROR"


def test_name_overrides_system(connected: Any) -> None:
    opened, client = connected

    opened.started(name="Mobis AS RPA")

    assert client.sent[0][1][1] == "Mobis AS RPA"


def test_disconnected_session_drops_messages_without_raising() -> None:
    opened = hub.Session(None, None)

    assert opened.connected is False
    opened.started()
    opened.finished(message="a")
    opened.failed(message="b")


def test_method_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNALR_METHOD", "ReportResult")

    assert hub.method() == "ReportResult"
