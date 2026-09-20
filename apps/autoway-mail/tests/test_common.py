from pathlib import Path
from typing import Any

import pytest

from autoway_mail import common


def test_schedule_id_defaults_to_five(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.SCHEDULE_ID_ENV, raising=False)

    assert common.schedule_id() == "5"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.SCHEDULE_ID_ENV, "11")

    assert common.schedule_id() == "11"


def test_the_history_file_sits_in_the_workspace(tmp_path: Path, rpa_settings: Any) -> None:
    assert common.history_path(rpa_settings) == (tmp_path / "work").resolve() / common.HISTORY_FILE


def test_headless_is_on_unless_the_env_says_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.HEADLESS_ENV, raising=False)
    assert common.headless() is True

    monkeypatch.setenv(common.HEADLESS_ENV, "N")
    assert common.headless() is False
