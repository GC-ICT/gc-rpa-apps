from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint
from mobis_as import pu010


def _reporter(sent: dict[str, object]) -> Any:
    class Recorder:
        def started(self, **kw: object) -> None:
            sent.update(kw)

        def finished(self, **kw: object) -> None:
            sent.update(kw)

        def failed(self, **kw: object) -> None:
            sent.update(kw)

        connected = False

        def send(self, *_: object, **__: object) -> None:
            return None

    @contextmanager
    def fake() -> Iterator[Recorder]:
        yield Recorder()

    return fake


def _endpoint() -> DbEndpoint:
    return DbEndpoint(host="", port=None, database="", user="", password="")


def _settings(name: str) -> RpaConfig:
    return RpaConfig(
        name=name,
        url="https://test-site.invalid",
        user_id="test_user",
        password="test_pw",
        otp="test_otp",
        use_otp=True,
        move_path="test_move_dir",
        exe_name="test_app.exe",
        source=_endpoint(),
        target=_endpoint(),
    )


def test_schedule_id_defaults_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pu010.SCHEDULE_ID_ENV, raising=False)

    assert pu010.schedule_id() == "1"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(pu010.SCHEDULE_ID_ENV, "7")

    assert pu010.schedule_id() == "7"


def test_locators_are_nexacro_ids() -> None:
    assert pu010.MY_MENU_BUTTON.startswith("mainframe.VFrameSet.HFrameSet.LeftFrame")
    assert "btnSearch" in pu010.SEARCH_BUTTON
    assert "btnExcelDwnl" in pu010.EXCEL_BUTTON


def test_menu_item_is_matched_by_screen_code_not_row_index() -> None:
    assert "[PU010]" in pu010.MY_MENU_ITEM
    assert "gridrow_" not in pu010.MY_MENU_ITEM


def test_main_returns_one_and_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from mobis_as import __main__ as entry

    sent: dict[str, object] = {}

    def fail(*_a: object, **_k: object) -> None:
        raise ValueError("다운로드 실패")

    monkeypatch.setattr(entry.pu010, "load", lambda: _settings("테스트 RPA"))
    monkeypatch.setattr(entry.pu010, "run", fail)
    monkeypatch.setattr(entry.hub, "session", _reporter(sent))

    assert entry.main() == 1
    assert sent["name"] == "테스트 RPA"
    assert "다운로드 실패" in str(sent["message"])


def test_main_falls_back_when_config_has_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from mobis_as import __main__ as entry

    sent: dict[str, object] = {}

    monkeypatch.setattr(entry.pu010, "load", lambda: _settings(""))
    monkeypatch.setattr(entry.pu010, "run", lambda *_a, **_k: Path("x.xlsx"))
    monkeypatch.setattr(entry.hub, "session", _reporter(sent))

    assert entry.main() == 0
    assert sent["name"] == entry.FALLBACK_SYSTEM
