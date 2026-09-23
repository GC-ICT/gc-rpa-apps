from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from autoway_document import __main__ as entry
from autoway_document import common, document
from gc_rpa_autoway import erp, site
from gc_rpa_core import app, config
from gc_rpa_core.config import RpaConfig, RpaDatabase
from gc_rpa_core.db import DbEndpoint


def erp_database() -> RpaDatabase:
    return RpaDatabase(
        name="ERP",
        source=DbEndpoint("test-erp.invalid", None, "ERP", "user", "pw"),
        target=DbEndpoint("", None, "", "", ""),
        tables=("[ERPFileDB].[dbo].[HRA600_F]",),
        queries=("EXEC [ERP].[dbo].[HRA600_Work] @_send_cust = {sender}",),
    )


def _hub(sent: dict[str, Any]) -> Any:
    class Recorder:
        connected = False

        def started(self, **kw: Any) -> None:
            sent["started"] = kw

        def finished(self, **kw: Any) -> None:
            sent["finished"] = kw

        def failed(self, **kw: Any) -> None:
            sent["failed"] = kw

        def progress(self, **kw: Any) -> None:
            sent.setdefault("progress", []).append(kw)

        def send(self, *_: Any, **__: Any) -> None:
            return None

    @contextmanager
    def fake(**_: Any) -> Iterator[Recorder]:
        yield Recorder()

    return fake


class FakeSwitch:
    def default_content(self) -> None:
        return None

    def window(self, _handle: str) -> None:
        return None


class FakeDriver:
    def __init__(self) -> None:
        self.current_window_handle = "main"
        self.window_handles = ["main"]
        self.switch_to = FakeSwitch()


@pytest.fixture
def quiet_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def fake_chrome(*_a: Any, **_k: Any) -> Iterator[object]:
        yield FakeDriver()

    monkeypatch.setattr(entry, "chrome", fake_chrome)
    monkeypatch.setattr(site, "login", lambda *_a: None)
    monkeypatch.setattr(config, "usable_database", lambda _settings: erp_database())
    monkeypatch.setattr(document, "capture_one", lambda *_a, **_k: None)


def test_main_logs_in_and_reports(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert "finished" in sent
    assert "failed" not in sent


def test_main_reports_a_failure(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}

    def boom() -> RpaConfig:
        raise LookupError("설정이 없습니다")

    monkeypatch.setattr(common, "load", boom)
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "설정이 없습니다" in sent["failed"]["message"]


def captured(tmp_path: Any) -> document.Captured:
    return document.Captured(
        document=document.Document("2026-000123", "현대글로비스", "9월 정산"),
        folder=tmp_path / "2026-000123",
        attachments=2,
        pdf=tmp_path / "2026-000123" / "2026-000123.pdf",
        images=[],
    )


def feed(monkeypatch: pytest.MonkeyPatch, documents: list[document.Captured | None]) -> None:
    remaining = list(documents)

    def take(*_a: Any, **_k: Any) -> document.Captured | None:
        return remaining.pop(0) if remaining else None

    monkeypatch.setattr(document, "capture_one", take)


def test_one_document_is_approved_and_registered(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig, tmp_path: Any
) -> None:
    sent: dict[str, Any] = {}
    steps: list[str] = []
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    feed(monkeypatch, [captured(tmp_path)])
    monkeypatch.setattr(document, "approve", lambda _driver: steps.append("결재"))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: steps.append("등록") or "2609220007")
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert steps == ["결재", "등록"]
    assert "2609220007" in sent["finished"]["message"]
    assert "첨부 2건" in sent["finished"]["message"]


def test_a_missing_erp_setting_fails_the_run(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig, tmp_path: Any
) -> None:
    sent: dict[str, Any] = {}
    steps: list[str] = []

    def missing(_settings: RpaConfig) -> RpaDatabase:
        raise LookupError("쓸 수 있는 DB 가 없습니다")

    monkeypatch.setattr(config, "usable_database", missing)
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    feed(monkeypatch, [captured(tmp_path)])
    monkeypatch.setattr(document, "approve", lambda _driver: steps.append("결재"))
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert steps == []
    assert "쓸 수 있는 DB 가 없습니다" in sent["failed"]["message"]


def test_an_empty_approval_box_is_reported(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert sent["finished"]["message"] == "결재할 문서가 없습니다"


def test_the_round_stops_at_the_document_limit(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig, tmp_path: Any
) -> None:
    sent: dict[str, Any] = {}
    approved: list[str] = []
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(document, "capture_one", lambda *_a, **_k: captured(tmp_path))
    monkeypatch.setattr(document, "approve", lambda _driver: approved.append("결재"))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "2609220007")
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert len(approved) == entry.MAX_DOCUMENTS
    assert f"{entry.MAX_DOCUMENTS}건" in sent["finished"]["message"]


def test_a_failure_keeps_what_was_already_registered(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig, tmp_path: Any
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    feed(monkeypatch, [captured(tmp_path), captured(tmp_path)])
    monkeypatch.setattr(document, "approve", lambda _driver: None)

    registered: list[str] = []

    def register(*_a: Any, **_k: Any) -> str:
        if registered:
            raise RuntimeError("ERP 가 응답하지 않습니다")
        registered.append("2609220007")
        return "2609220007"

    monkeypatch.setattr(erp, "register", register)
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "1건 결재·ERP 등록" in sent["failed"]["message"]
    assert "ERP 가 응답하지 않습니다" in sent["failed"]["message"]
