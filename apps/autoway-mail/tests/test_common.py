from dataclasses import replace
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


def test_workspace_comes_from_the_schedule(tmp_path: Path, rpa_settings: Any) -> None:
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))

    assert common.workspace(configured) == (tmp_path / "from-schedule").resolve()
    assert common.workspace(configured).is_dir()


def test_downloads_and_history_sit_under_the_workspace(tmp_path: Path, rpa_settings: Any) -> None:
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))
    base = (tmp_path / "from-schedule").resolve()

    assert common.download_dir(configured) == base / common.DOWNLOAD_SUBDIR
    assert common.history_path(configured) == base / common.HISTORY_FILE


@pytest.mark.parametrize("move_path", ["", "   "])
def test_an_empty_move_path_is_refused(move_path: str, rpa_settings: Any) -> None:
    with pytest.raises(common.WorkspaceError, match="file_move_path"):
        common.workspace(replace(rpa_settings, move_path=move_path))


def test_size_text_switches_unit_at_one_kilobyte(tmp_path: Path) -> None:
    small = tmp_path / "small.txt"
    small.write_bytes(b"x" * 512)
    large = tmp_path / "large.txt"
    large.write_bytes(b"x" * 2048)

    assert common.size_text(small) == "512 B"
    assert common.size_text(large) == "2 KB"


def test_poppler_comes_from_the_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.POPPLER_ENV, str(tmp_path / "poppler" / "bin"))

    assert common.poppler_path() == str(tmp_path / "poppler" / "bin")


def test_poppler_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.POPPLER_ENV, raising=False)

    assert common.poppler_path() == ""
