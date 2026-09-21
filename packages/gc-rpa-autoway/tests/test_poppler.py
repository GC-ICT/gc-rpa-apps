from pathlib import Path

import pytest

from gc_rpa_autoway import poppler


def test_poppler_comes_from_the_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(poppler.POPPLER_ENV, str(tmp_path / "poppler" / "bin"))

    assert poppler.poppler_path() == str(tmp_path / "poppler" / "bin")


def test_poppler_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(poppler.POPPLER_ENV, raising=False)

    assert poppler.poppler_path() == ""


def test_poppler_is_not_complained_about_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(poppler.POPPLER_ENV, raising=False)

    assert poppler.complaint() == ""


def test_a_missing_poppler_folder_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(poppler.POPPLER_ENV, str(tmp_path / "nowhere"))

    assert "폴더가 없습니다" in poppler.complaint()


def test_the_poppler_root_is_corrected_to_the_binary_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binaries = tmp_path / "poppler" / "Library" / "bin"
    binaries.mkdir(parents=True)
    (binaries / f"{poppler.POPPLER_BINARY}.exe").write_bytes(b"")
    monkeypatch.setenv(poppler.POPPLER_ENV, str(tmp_path / "poppler"))

    complaint = poppler.complaint()
    assert str(binaries) in complaint
    assert "고쳐야 합니다" in complaint


def test_the_right_poppler_folder_is_quiet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / f"{poppler.POPPLER_BINARY}.exe").write_bytes(b"")
    monkeypatch.setenv(poppler.POPPLER_ENV, str(tmp_path))

    assert poppler.complaint() == ""


def test_a_folder_without_poppler_anywhere_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(poppler.POPPLER_ENV, str(tmp_path))

    assert poppler.POPPLER_BINARY in poppler.complaint()
