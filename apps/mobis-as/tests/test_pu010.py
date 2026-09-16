from pathlib import Path

import pytest

from gc_rpa_core.config import RpaConfig
from mobis_as import pu010


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


def test_notify_never_raises() -> None:
    from mobis_as import __main__ as entry

    def boom(**_: object) -> None:
        raise RuntimeError("허브 죽음")

    entry.notify(boom, message="원인")


def test_describe_handles_empty_exception_message() -> None:
    from selenium.common.exceptions import TimeoutException

    from mobis_as import __main__ as entry

    assert entry.describe(TimeoutException()) == "TimeoutException: 상세 메시지가 없습니다"
    assert entry.describe(ValueError("원인")) == "ValueError: 원인"


def test_main_returns_one_and_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from mobis_as import __main__ as entry

    sent: dict[str, object] = {}

    def fail(**_: object) -> None:
        raise ValueError("다운로드 실패")

    monkeypatch.setattr(entry.pu010, "load", lambda: _settings("테스트 RPA"))
    monkeypatch.setattr(entry.pu010, "run", fail)
    monkeypatch.setattr(entry.hub, "started", lambda **kw: None)
    monkeypatch.setattr(entry.hub, "failed", lambda **kw: sent.update(kw))

    assert entry.main() == 1
    assert sent["name"] == "테스트 RPA"
    assert "다운로드 실패" in str(sent["message"])


def test_main_falls_back_when_config_has_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from mobis_as import __main__ as entry

    sent: dict[str, object] = {}

    monkeypatch.setattr(entry.pu010, "load", lambda: _settings(""))
    monkeypatch.setattr(entry.pu010, "run", lambda **_: Path("x.xlsx"))
    monkeypatch.setattr(entry.hub, "started", lambda **kw: None)
    monkeypatch.setattr(entry.hub, "finished", lambda **kw: sent.update(kw))

    assert entry.main() == 0
    assert sent["name"] == entry.FALLBACK_SYSTEM
