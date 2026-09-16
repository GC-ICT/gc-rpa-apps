import logging
from pathlib import Path

import pytest

from gc_rpa_core import browser


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    return tmp_path


def test_resolve_dir_creates_and_absolutises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    resolved = browser.resolve_dir("nested/downloads")

    assert resolved.is_dir()
    assert resolved.is_absolute()
    assert resolved == (tmp_path / "nested" / "downloads").resolve()


def test_settled_files_ignores_partial_downloads(downloads: Path) -> None:
    (downloads / "done.xlsx").write_text("x")
    (downloads / "busy.xlsx.crdownload").write_text("x")
    (downloads / "busy.tmp").write_text("x")

    assert browser.settled_files(downloads) == {downloads / "done.xlsx"}


def test_wait_download_returns_the_new_file(downloads: Path) -> None:
    (downloads / "old.xlsx").write_text("x")
    before = browser.settled_files(downloads)
    (downloads / "new.xlsx").write_text("x")

    assert browser.wait_download(downloads, before=before, timeout=1) == downloads / "new.xlsx"


def test_wait_download_times_out_when_nothing_arrives(downloads: Path) -> None:
    before = browser.settled_files(downloads)

    with pytest.raises(browser.DownloadError, match="새 파일이 내려오지 않았습니다"):
        browser.wait_download(downloads, before=before, timeout=1)


def test_wait_download_ignores_partial_file(downloads: Path) -> None:
    before = browser.settled_files(downloads)
    (downloads / "coming.xlsx.crdownload").write_text("x")

    with pytest.raises(browser.DownloadError):
        browser.wait_download(downloads, before=before, timeout=1)


def test_move_to_relocates_file(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    downloaded = source / "test_download.xlsx"
    downloaded.write_text("x")
    destination = tmp_path / "dst" / "test_move_dir"

    moved = browser.move_to(downloaded, str(destination))

    assert moved == destination / "test_download.xlsx"
    assert moved.is_file()
    assert not downloaded.exists()


def test_move_to_keeps_file_when_destination_blank(tmp_path: Path) -> None:
    downloaded = tmp_path / "test_download.xlsx"
    downloaded.write_text("x")

    assert browser.move_to(downloaded, "") == downloaded


def record(message: str) -> logging.LogRecord:
    return logging.LogRecord("x", logging.DEBUG, "x", 1, message, None, None)


def test_driver_progress_filter_keeps_useful_lines() -> None:
    keep = browser.DriverProgressFilter()

    assert keep.filter(record("Downloading chromedriver 150.0 from https://..."))
    assert keep.filter(record("Detected browser: chrome 150.0.7871.186"))
    assert keep.filter(record("chromedriver not found in PATH"))


def test_driver_progress_filter_drops_noise() -> None:
    keep = browser.DriverProgressFilter()

    assert not keep.filter(record("Sending stats to Plausible: Props { ... }"))
    assert not keep.filter(record("Acquiring lock: /tmp/.../sm.lock"))
    assert not keep.filter(record("Executing process: /path/selenium-manager --debug"))


def test_show_driver_progress_is_idempotent() -> None:
    browser.show_driver_progress()
    browser.show_driver_progress()

    manager = logging.getLogger(browser.MANAGER_LOGGER)
    installed = [f for f in manager.filters if isinstance(f, browser.DriverProgressFilter)]

    assert len(installed) == 1
    assert manager.level == logging.DEBUG
