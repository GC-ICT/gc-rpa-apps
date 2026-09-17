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


def test_workspace_uses_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "autoway"
    monkeypatch.setenv(common.WORKSPACE_ENV, str(target))

    assert common.workspace() == target.resolve()
    assert target.is_dir()


def test_workspace_defaults_beside_the_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(common.WORKSPACE_ENV, raising=False)

    assert common.workspace() == (tmp_path / common.DEFAULT_WORKSPACE).resolve()


def test_workspace_comes_from_the_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    monkeypatch.delenv(common.WORKSPACE_ENV, raising=False)
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))

    assert common.workspace(configured) == (tmp_path / "from-schedule").resolve()


def test_the_schedule_beats_the_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    monkeypatch.setenv(common.WORKSPACE_ENV, str(tmp_path / "from-env"))
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))

    assert common.workspace(configured) == (tmp_path / "from-schedule").resolve()


def test_the_env_is_used_when_the_schedule_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    monkeypatch.setenv(common.WORKSPACE_ENV, str(tmp_path / "from-env"))

    assert (
        common.workspace(replace(rpa_settings, move_path="")) == (tmp_path / "from-env").resolve()
    )


def test_downloads_and_history_follow_the_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    monkeypatch.delenv(common.WORKSPACE_ENV, raising=False)
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))
    base = (tmp_path / "from-schedule").resolve()

    assert common.download_dir(configured) == base / common.DOWNLOAD_SUBDIR
    assert common.history_path(configured) == base / common.HISTORY_FILE


def test_an_empty_move_path_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(common.WORKSPACE_ENV, raising=False)

    assert (
        common.workspace(replace(rpa_settings, move_path=""))
        == (tmp_path / common.DEFAULT_WORKSPACE).resolve()
    )


def test_downloads_sit_inside_the_workspace(workspace: Path) -> None:
    assert common.download_dir() == workspace / common.DOWNLOAD_SUBDIR
    assert common.download_dir().is_dir()


def test_history_sits_inside_the_workspace(workspace: Path) -> None:
    assert common.history_path().parent == workspace


@pytest.mark.parametrize("value", ["Y", "1", "true", " T "])
def test_headless_accepts_the_usual_flags(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.HEADLESS_ENV, value)

    assert common.headless()


def test_headless_is_on_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.HEADLESS_ENV, raising=False)

    assert common.headless()


def test_headless_can_be_turned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.HEADLESS_ENV, "N")

    assert not common.headless()


def test_size_text_switches_unit_at_one_kilobyte(tmp_path: Path) -> None:
    small = tmp_path / "small.txt"
    small.write_bytes(b"x" * 512)
    large = tmp_path / "large.txt"
    large.write_bytes(b"x" * 2048)

    assert common.size_text(small) == "512 B"
    assert common.size_text(large) == "2 KB"
