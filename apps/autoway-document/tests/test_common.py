import pytest

from autoway_document import common


def test_schedule_id_defaults_to_eleven(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.SCHEDULE_ID_ENV, raising=False)

    assert common.schedule_id() == "11"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.SCHEDULE_ID_ENV, "12")

    assert common.schedule_id() == "12"


def test_headless_is_on_unless_the_env_says_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.HEADLESS_ENV, raising=False)
    assert common.headless() is True

    monkeypatch.setenv(common.HEADLESS_ENV, "N")
    assert common.headless() is False


def test_the_file_rows_are_keyed_by_the_document_number() -> None:
    assert common.ERP_KEY_COLUMN == "docu_no"
