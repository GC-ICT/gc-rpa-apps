from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint
from hkmc_api_app import __main__ as entry
from hkmc_api_app.build_settings import Build


def _build(name: str = "hkmc-api-001", schedule_id: str = "4") -> Build:
    return Build(name=name, schedule_id=schedule_id, indexes=("001", "002"))


@dataclass
class _FakeSession:
    company: str


@contextmanager
def _nothing() -> Iterator[None]:
    yield None


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


def test_schedule_id_comes_from_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(entry.SCHEDULE_ID_ENV, raising=False)

    assert entry.schedule_id(_build(schedule_id="6")) == "6"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(entry.SCHEDULE_ID_ENV, "9")

    assert entry.schedule_id(_build(schedule_id="6")) == "9"


def test_summarize_counts_rows_and_failures() -> None:
    summary, broken = entry.summarize_totals(
        {"HMC/001": 307, "KIA/001": 0, "HMC/006": entry.FAILED}
    )

    assert broken == ["HMC/006"]
    assert "3건 조회, 307행 데이터 쓰기" in summary
    assert "실패 1건: HMC/006" in summary


def test_summarize_says_nothing_about_failures_when_there_are_none() -> None:
    summary, broken = entry.summarize_totals({"HMC/001": 307})

    assert broken == []
    assert summary == "1건 조회, 307행 데이터 쓰기"


def test_run_walks_each_number_across_companies(monkeypatch: pytest.MonkeyPatch) -> None:
    visited: list[tuple[str, str]] = []

    monkeypatch.setattr(entry.common, "build_client", _nothing)
    monkeypatch.setattr(entry.loader, "writer", lambda *_, **__: _nothing())
    monkeypatch.setattr(
        entry.common, "open_session", lambda _client, company: _FakeSession(company)
    )
    monkeypatch.setattr(
        entry,
        "collect_rows",
        lambda api, opened, _writer: visited.append((api.index, opened.company)) or 0,
    )

    build = Build(name="hkmc-api-001", schedule_id="4", indexes=("001", "007", "016"))
    entry.run(_settings(), build)

    assert visited == [
        ("001", "HMC"),
        ("001", "KIA"),
        ("007", "KIA"),
        ("016", "HMC"),
    ]


def test_run_opens_one_session_per_company(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    monkeypatch.setattr(entry.common, "build_client", _nothing)
    monkeypatch.setattr(entry.loader, "writer", lambda *_, **__: _nothing())
    monkeypatch.setattr(
        entry.common,
        "open_session",
        lambda _client, company: opened.append(company) or _FakeSession(company),
    )
    monkeypatch.setattr(entry, "collect_rows", lambda *_: 0)

    build = Build(name="hkmc-api-001", schedule_id="4", indexes=("001", "002", "003"))
    entry.run(_settings(), build)

    assert opened == ["HMC", "KIA"]


def test_run_skips_a_company_with_nothing_to_do(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    monkeypatch.setattr(entry.common, "build_client", _nothing)
    monkeypatch.setattr(entry.loader, "writer", lambda *_, **__: _nothing())
    monkeypatch.setattr(
        entry.common,
        "open_session",
        lambda _client, company: opened.append(company) or _FakeSession(company),
    )
    monkeypatch.setattr(entry, "collect_rows", lambda *_: 0)

    build = Build(name="hkmc-api-001", schedule_id="4", indexes=("016",))
    entry.run(_settings(), build)

    assert opened == ["HMC"]


def test_companies_default_to_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(entry.COMPANIES_ENV, raising=False)

    assert entry.companies() == ("HMC", "KIA")


def test_companies_can_be_narrowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(entry.COMPANIES_ENV, " hmc ")

    assert entry.companies() == ("HMC",)


def test_system_name_prefers_the_build_override() -> None:
    build = Build(
        name="hkmc-api-002", schedule_id="6", indexes=("012",), signalr_system="HKMC-API-2"
    )

    assert entry.system_name(build, _settings()) == "HKMC-API-2"


def test_system_name_falls_back_to_the_procedure() -> None:
    assert entry.system_name(_build(), _settings("현대기아 수집")) == "현대기아 수집"


def test_system_name_falls_back_to_the_build_name() -> None:
    assert entry.system_name(_build(), _settings("")) == "hkmc-api-001"


def test_main_reports_success_with_a_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr(entry.build_settings, "current", _build)
    monkeypatch.setattr(entry.config, "load", lambda _: _settings())
    monkeypatch.setattr(entry, "run", lambda *_, **__: {"HMC/001": 307, "KIA/001": 142})
    monkeypatch.setattr(entry.hub, "session", _reporter(sent))

    assert entry.main() == 0
    assert "finished" in sent
    assert "449행" in str(sent["finished"])


def test_main_reports_failure_when_an_api_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr(entry.build_settings, "current", _build)
    monkeypatch.setattr(entry.config, "load", lambda _: _settings())
    monkeypatch.setattr(entry, "run", lambda *_, **__: {"HMC/001": 307, "HMC/006": -1})
    monkeypatch.setattr(entry.hub, "session", _reporter(sent))

    assert entry.main() == 1
    assert "failed" in sent
    assert "HMC/006" in str(sent["failed"])


def test_main_returns_one_when_schedule_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def boom(_: str) -> RpaConfig:
        raise LookupError("설정이 없습니다")

    monkeypatch.setattr(entry.build_settings, "current", _build)
    monkeypatch.setattr(entry.config, "load", boom)
    monkeypatch.setattr(entry.hub, "session", _reporter(sent))

    assert entry.main() == 1
    assert "설정이 없습니다" in str(sent["failed"])


def test_only_005_and_007_sweep_plants() -> None:
    from hkmc_api_app import registry

    assert [api.index for api in registry.APIS if registry.sweeps(api)] == ["005", "007"]


def test_005_sweeps_only_inventory_plants() -> None:
    from hkmc_api_app import api_005_supplier_inventory as api_005
    from hkmc_api_app import registry

    assert registry.plants_for(api_005.API, "HMC") == api_005.INVENTORY_PLANTS["HMC"]
    assert registry.plants_for(api_005.API, "KIA") == api_005.INVENTORY_PLANTS["KIA"]


def test_007_sweeps_every_plant_of_the_company() -> None:
    from hkmc_api_app import common, registry

    assert registry.plants_for(registry.BY_INDEX["007"], "KIA") == tuple(common.PLANTS["KIA"])


def _no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entry.common, "build_client", _nothing)
    monkeypatch.setattr(entry.loader, "writer", lambda *_, **__: _nothing())
    monkeypatch.setattr(
        entry.common, "open_session", lambda _client, company: _FakeSession(company)
    )


def _always_fails(*_: object) -> int:
    raise RuntimeError("인터페이스가 응답하지 않습니다")


def test_expected_failure_is_not_counted_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _no_io(monkeypatch)
    monkeypatch.setattr(entry, "collect_rows", _always_fails)

    build = Build(name="hkmc-api-001", schedule_id="4", indexes=("006",))
    with caplog.at_level("INFO", logger=entry.FALLBACK_SYSTEM):
        totals = entry.run(_settings(), build)

    assert totals == {"HMC/006": 0, "KIA/006": 0}
    assert all(record.levelname == "INFO" for record in caplog.records)
    assert all(
        "(예상된 오류)" in record.getMessage()
        for record in caplog.records
        if "실패" in record.getMessage()
    )


def test_unexpected_failure_is_still_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_io(monkeypatch)
    monkeypatch.setattr(entry, "collect_rows", _always_fails)

    build = Build(name="hkmc-api-001", schedule_id="4", indexes=("001",))
    totals = entry.run(_settings(), build)

    assert totals == {"HMC/001": -1, "KIA/001": -1}


def test_expected_empty_is_per_company(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_io(monkeypatch)
    monkeypatch.setattr(entry, "collect_rows", _always_fails)

    build = Build(name="hkmc-api-001", schedule_id="4", indexes=("005",))
    totals = entry.run(_settings(), build)

    assert totals == {"HMC/005": 0, "KIA/005": -1}
