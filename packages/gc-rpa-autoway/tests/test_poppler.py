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


class FakePage:
    def __init__(self, darkest: int) -> None:
        self.darkest = darkest
        self.saved: Path | None = None

    def convert(self, _mode: str) -> "FakePage":
        return self

    def getextrema(self) -> tuple[int, int]:
        return self.darkest, 255

    def save(self, path: Path, _format: str) -> None:
        self.saved = path
        path.write_bytes(b"jpeg")


def test_a_white_page_counts_as_blank() -> None:
    assert poppler.blank(FakePage(255)) is True


def test_a_page_with_ink_is_not_blank() -> None:
    assert poppler.blank(FakePage(12)) is False


def test_blank_pages_are_left_out_and_numbering_stays_tight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"%PDF-")
    pages = [FakePage(10), FakePage(255), FakePage(40)]
    monkeypatch.setattr(poppler, "convert_from_path", lambda *_a, **_k: pages)

    written = poppler.to_images(pdf)

    assert [path.name for path in written] == ["document_1.jpg", "document_2.jpg"]
