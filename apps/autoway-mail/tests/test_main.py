from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

import pytest

from autoway_mail import __main__ as entry
from autoway_mail import common, inbox, mail
from gc_rpa_autoway import erp, site
from gc_rpa_core.config import RpaConfig, RpaDatabase
from gc_rpa_core.db import DbEndpoint


def erp_database() -> RpaDatabase:
    return RpaDatabase(
        name="ERP",
        source=DbEndpoint("test-erp.invalid", None, "ERP", "user", "pw"),
        target=DbEndpoint("", None, "", "", ""),
        tables=("[ERPFileDB].[dbo].[HRA700_File]",),
        queries=("EXEC [ERP].[dbo].[HRA700_Work] @_send_cust = {sender}",),
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
    monkeypatch.setattr(inbox, "open_module", lambda *_a: None)
    monkeypatch.setattr(erp, "usable_database", lambda _settings: erp_database())


def test_main_reports_the_tally(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))
    monkeypatch.setattr(mail, "run", lambda _: mail.Tally(done=3))

    assert entry.main() == 0
    assert "성공 3건" in str(sent["finished"])


def test_main_returns_one_when_a_mail_failed(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))
    monkeypatch.setattr(mail, "run", lambda _: mail.Tally(done=1, failed=2))

    assert entry.main() == 1
    assert "실패 2건" in str(sent["failed"])


def test_main_returns_one_when_the_schedule_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    def boom() -> RpaConfig:
        raise LookupError("설정이 없습니다")

    monkeypatch.setattr(common, "load", boom)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "설정이 없습니다" in str(sent["failed"])


def test_main_falls_back_when_the_schedule_has_no_name(
    monkeypatch: pytest.MonkeyPatch, quiet_browser: None, rpa_settings: RpaConfig
) -> None:
    rpa_settings = replace(rpa_settings, name="")
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))
    monkeypatch.setattr(mail, "run", lambda _: mail.Tally())

    assert entry.main() == 0
    assert sent["started"]["name"] == entry.FALLBACK_SYSTEM
