from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint
from hkmc_api_app import __main__ as entry


def _endpoint() -> DbEndpoint:
    return DbEndpoint(
        host="test-source.invalid",
        port=1801,
        database="test_source_db",
        user="test_source_user",
        password="test_source_pw",
    )


def _settings(name: str = "테스트 수집") -> RpaConfig:
    return RpaConfig(
        name=name,
        url="",
        user_id="",
        password="",
        otp="",
        use_otp=False,
        move_path="",
        exe_name="test_app.exe",
        source=_endpoint(),
        target=DbEndpoint("", None, "", "", ""),
    )


def _reporter(sent: dict[str, object]) -> Any:
    class Recorder:
        connected = False

        def started(self, **kw: object) -> None:
            sent.setdefault("started", kw)

        def finished(self, **kw: object) -> None:
            sent["finished"] = kw

        def failed(self, **kw: object) -> None:
            sent["failed"] = kw

        def send(self, *_: object, **__: object) -> None:
            return None

    @contextmanager
    def fake() -> Iterator[Recorder]:
        yield Recorder()

    return fake


def test_schedule_id_defaults_to_four(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(entry.SCHEDULE_ID_ENV, raising=False)

    assert entry.schedule_id() == "4"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(entry.SCHEDULE_ID_ENV, "9")

    assert entry.schedule_id() == "9"


def test_companies_default_to_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(entry.COMPANIES_ENV, raising=False)

    assert entry.companies() == ("HMC", "KIA")


def test_companies_can_be_narrowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(entry.COMPANIES_ENV, " hmc ")

    assert entry.companies() == ("HMC",)


def test_describe_handles_empty_exception_message() -> None:
    assert entry.describe(ValueError()) == "ValueError: 상세 메시지가 없습니다"
    assert entry.describe(ValueError("원인")) == "ValueError: 원인"


def test_main_reports_success_with_a_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr(entry.config, "load", lambda _: _settings())
    monkeypatch.setattr(entry, "run", lambda _: {"HMC/001": 307, "KIA/001": 142})
    monkeypatch.setattr(entry, "reporter", _reporter(sent))

    assert entry.main() == 0
    assert "finished" in sent
    assert "449행" in str(sent["finished"])


def test_main_reports_failure_when_an_api_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr(entry.config, "load", lambda _: _settings())
    monkeypatch.setattr(entry, "run", lambda _: {"HMC/001": 307, "HMC/006": -1})
    monkeypatch.setattr(entry, "reporter", _reporter(sent))

    assert entry.main() == 1
    assert "failed" in sent
    assert "HMC/006" in str(sent["failed"])


def test_main_returns_one_when_schedule_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def boom(_: str) -> RpaConfig:
        raise LookupError("설정이 없습니다")

    monkeypatch.setattr(entry.config, "load", boom)
    monkeypatch.setattr(entry, "reporter", _reporter(sent))

    assert entry.main() == 1
    assert "설정이 없습니다" in str(sent["failed"])
