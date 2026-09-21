from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from autoway_document import __main__ as entry
from autoway_document import common
from gc_rpa_autoway import site
from gc_rpa_core import config
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


@pytest.fixture
def quiet_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def fake_chrome(*_a: Any, **_k: Any) -> Iterator[object]:
        yield object()

    monkeypatch.setattr(entry, "chrome", fake_chrome)
    monkeypatch.setattr(site, "login", lambda *_a: None)
    monkeypatch.setattr(config, "usable_database", lambda _settings: erp_database())


def test_main_logs_in_and_reports(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert "finished" in sent
    assert "failed" not in sent


def test_main_names_the_erp_target(
    monkeypatch: pytest.MonkeyPatch,
    quiet_browser: None,
    rpa_settings: RpaConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub({}))

    with caplog.at_level("INFO", logger=entry.FALLBACK_SYSTEM):
        entry.main()

    assert "[ERPFileDB].[dbo].[HRA600_F]" in caplog.text


def test_main_reports_a_failure(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}

    def boom() -> RpaConfig:
        raise LookupError("설정이 없습니다")

    monkeypatch.setattr(common, "load", boom)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "설정이 없습니다" in sent["failed"]["message"]
