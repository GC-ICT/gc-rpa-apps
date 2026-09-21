from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from gc_rpa_core import app
from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint
from hd_seat_jit import __main__ as entry
from hd_seat_jit import common, loader, orders, sheet, vpn

TARGET = loader.Target(
    endpoint=DbEndpoint("test-erp.invalid", None, "MES01", "rpa", "pw"),
    temp_table="SDB500_Temp",
    queries=("EXEC SDB500_WORK",),
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
def whole_run(
    monkeypatch: pytest.MonkeyPatch, rpa_settings: RpaConfig, workbook: Callable[..., Path]
) -> dict[str, Any]:
    done: dict[str, Any] = {}

    @contextmanager
    def fake_chrome(*_a: Any, **_k: Any) -> Iterator[object]:
        yield object()

    def fake_sweep(_driver: Any, _settings: Any, *, plants: Any, folder: Path) -> list[Path]:
        done["plants"] = tuple(plants)
        return [workbook(folder / f"{plant}.xlsx") for plant in plants]

    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(loader, "target", lambda _settings: TARGET)
    monkeypatch.setattr(vpn, "connect", lambda **kw: done.update(vpn=kw))
    monkeypatch.setattr(entry, "chrome", fake_chrome)
    monkeypatch.setattr(orders, "run", fake_sweep)
    monkeypatch.setattr(loader, "write", lambda _t, rows: done.setdefault("rows", len(rows)))
    monkeypatch.setattr(loader, "finish", lambda _t: 1)
    return done


def test_a_whole_run_reports_what_it_did(
    monkeypatch: pytest.MonkeyPatch, whole_run: dict[str, Any]
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert whole_run["plants"] == common.PLANTS
    assert whole_run["rows"] == len(common.PLANTS)
    assert "3건 받아 3행 적재" in sent["finished"]["message"]


def test_the_vpn_is_asked_for_with_its_own_schedule_ids(
    monkeypatch: pytest.MonkeyPatch, whole_run: dict[str, Any]
) -> None:
    monkeypatch.setattr(app.hub, "session", _hub({}))

    entry.main()

    assert whole_run["vpn"]["portal_schedule_id"] == "18"
    assert whole_run["vpn"]["otp_schedule_id"] == "17"


def test_the_uploaded_workbooks_are_gone_afterwards(
    monkeypatch: pytest.MonkeyPatch, whole_run: dict[str, Any], tmp_path: Path
) -> None:
    monkeypatch.setattr(app.hub, "session", _hub({}))

    entry.main()

    assert list((tmp_path / "work" / "download").glob("*.xlsx")) == []


def test_leftovers_from_the_last_run_are_thrown_away_first(
    monkeypatch: pytest.MonkeyPatch,
    whole_run: dict[str, Any],
    rpa_settings: RpaConfig,
    tmp_path: Path,
) -> None:
    stale = tmp_path / "work" / "download" / "stale.xlsx"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"")
    monkeypatch.setattr(app.hub, "session", _hub({}))

    entry.main()

    assert not stale.exists()


def test_a_failed_vpn_stops_before_the_browser(
    monkeypatch: pytest.MonkeyPatch, whole_run: dict[str, Any]
) -> None:
    sent: dict[str, Any] = {}

    def boom(**_k: Any) -> None:
        raise vpn.VpnError("f5vpn.exe 가 뜨지 않았습니다")

    monkeypatch.setattr(vpn, "connect", boom)
    monkeypatch.setattr(orders, "run", lambda *_a, **_k: pytest.fail("VPN 없이 열면 안 됩니다"))
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "f5vpn.exe" in sent["failed"]["message"]


def test_a_workbook_that_cannot_be_read_stops_the_load(
    monkeypatch: pytest.MonkeyPatch, whole_run: dict[str, Any], tmp_path: Path
) -> None:
    sent: dict[str, Any] = {}

    def half_broken(_driver: Any, _settings: Any, *, plants: Any, folder: Path) -> list[Path]:
        broken = folder / "broken.xlsx"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_bytes(b"not a workbook")
        return [broken]

    monkeypatch.setattr(orders, "run", half_broken)
    monkeypatch.setattr(loader, "write", lambda *_a: pytest.fail("깨진 파일이 있으면 적재 금지"))
    monkeypatch.setattr(app.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "broken.xlsx" in sent["failed"]["message"]


def test_the_rows_carry_every_field(
    monkeypatch: pytest.MonkeyPatch, whole_run: dict[str, Any]
) -> None:
    kept: list[Any] = []
    monkeypatch.setattr(loader, "write", lambda _t, rows: kept.extend(rows) or len(rows))
    monkeypatch.setattr(app.hub, "session", _hub({}))

    entry.main()

    assert all(len(row) == len(sheet.FIELDS) for row in kept)
    assert all(row[-1] == common.CUSTOMER_CODE for row in kept)
