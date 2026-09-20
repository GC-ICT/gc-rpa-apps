from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gc_rpa_autoway import files


def test_workspace_comes_from_the_schedule(tmp_path: Path, rpa_settings: Any) -> None:
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))

    assert files.workspace(configured) == (tmp_path / "from-schedule").resolve()
    assert files.workspace(configured).is_dir()


def test_downloads_sit_under_the_workspace(tmp_path: Path, rpa_settings: Any) -> None:
    configured = replace(rpa_settings, move_path=str(tmp_path / "from-schedule"))
    base = (tmp_path / "from-schedule").resolve()

    assert files.download_dir(configured) == base / files.DOWNLOAD_SUBDIR


@pytest.mark.parametrize("move_path", ["", "   "])
def test_an_empty_move_path_is_refused(move_path: str, rpa_settings: Any) -> None:
    with pytest.raises(files.WorkspaceError, match="file_move_path"):
        files.workspace(replace(rpa_settings, move_path=move_path))


def test_poppler_comes_from_the_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(files.POPPLER_ENV, str(tmp_path / "poppler" / "bin"))

    assert files.poppler_path() == str(tmp_path / "poppler" / "bin")


def test_poppler_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(files.POPPLER_ENV, raising=False)

    assert files.poppler_path() == ""


def test_poppler_is_not_complained_about_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(files.POPPLER_ENV, raising=False)

    assert files.poppler_complaint() == ""


def test_a_missing_poppler_folder_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(files.POPPLER_ENV, str(tmp_path / "nowhere"))

    assert "폴더가 없습니다" in files.poppler_complaint()


def test_the_poppler_root_is_corrected_to_the_binary_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binaries = tmp_path / "poppler" / "Library" / "bin"
    binaries.mkdir(parents=True)
    (binaries / f"{files.POPPLER_BINARY}.exe").write_bytes(b"")
    monkeypatch.setenv(files.POPPLER_ENV, str(tmp_path / "poppler"))

    complaint = files.poppler_complaint()
    assert str(binaries) in complaint
    assert "고쳐야 합니다" in complaint


def test_the_right_poppler_folder_is_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / f"{files.POPPLER_BINARY}.exe").write_bytes(b"")
    monkeypatch.setenv(files.POPPLER_ENV, str(tmp_path))

    assert files.poppler_complaint() == ""


def test_a_folder_without_poppler_anywhere_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(files.POPPLER_ENV, str(tmp_path))

    assert files.POPPLER_BINARY in files.poppler_complaint()
