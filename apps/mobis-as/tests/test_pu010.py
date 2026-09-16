import pytest

from mobis_as import pu010


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
