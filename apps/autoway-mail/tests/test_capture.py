from pathlib import Path

import pytest

from autoway_mail import capture


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    folder = tmp_path / "download"
    folder.mkdir()
    return folder


@pytest.fixture
def target(tmp_path: Path) -> Path:
    folder = tmp_path / "mail"
    folder.mkdir()
    return folder


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "DOWNLOAD_START_GRACE", 0.05)
    monkeypatch.setattr(capture, "DOWNLOAD_TIMEOUT", 0.3)


def test_finished_downloads_are_moved(downloads: Path, target: Path) -> None:
    (downloads / "a.eml").write_bytes(b"x")
    (downloads / "b.xlsx").write_bytes(b"x")

    assert capture.gather_downloads(downloads, target) == 2
    assert sorted(path.name for path in target.iterdir()) == ["a.eml", "b.xlsx"]
    assert not list(downloads.iterdir())


def test_a_partial_download_is_left_behind(downloads: Path, target: Path) -> None:
    (downloads / "a.eml").write_bytes(b"x")
    (downloads / "Unconfirmed 1.crdownload").write_bytes(b"x")

    capture.gather_downloads(downloads, target)

    assert [path.name for path in target.iterdir()] == ["a.eml"]
    assert [path.name for path in downloads.iterdir()] == ["Unconfirmed 1.crdownload"]


def test_an_empty_download_folder_moves_nothing(downloads: Path, target: Path) -> None:
    assert capture.gather_downloads(downloads, target) == 0


def test_a_finished_download_is_not_treated_as_partial(downloads: Path) -> None:
    (downloads / "a.eml").write_bytes(b"x")

    assert not capture.downloading(downloads)


@pytest.mark.parametrize("name", ["a.crdownload", "a.tmp", "a.part"])
def test_partial_suffixes_are_spotted(name: str, downloads: Path) -> None:
    (downloads / name).write_bytes(b"x")

    assert capture.downloading(downloads)


def test_waiting_gives_up_and_says_so(downloads: Path, caplog: pytest.LogCaptureFixture) -> None:
    (downloads / "a.crdownload").write_bytes(b"x")

    with caplog.at_level("WARNING", logger=capture.logger.name):
        capture.wait_for_downloads(downloads)

    assert "내려받지 못했습니다" in caplog.text
