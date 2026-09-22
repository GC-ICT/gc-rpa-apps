import logging
from pathlib import Path
from typing import Any

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


def test_move_to_appends_time_to_the_name(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    downloaded = source / "test_download.xlsx"
    downloaded.write_text("x")
    destination = tmp_path / "dst" / "test_move_dir"

    moved = browser.move_to(downloaded, str(destination))

    assert moved.parent == destination
    assert moved.stem.startswith("test_download_")
    assert moved.suffix == ".xlsx"
    assert len(moved.stem) == len("test_download_") + 6
    assert moved.is_file()
    assert not downloaded.exists()


def test_move_to_can_keep_the_original_name(tmp_path: Path) -> None:
    downloaded = tmp_path / "test_download.xlsx"
    downloaded.write_text("x")
    destination = tmp_path / "dst"

    moved = browser.move_to(downloaded, str(destination), stamp=False)

    assert moved == destination / "test_download.xlsx"


def test_stamped_name_uses_time() -> None:
    from datetime import datetime

    name = browser.stamped_name(Path("PU010_20260916.xlsx"), datetime(2026, 9, 16, 12, 15, 30))

    assert name == "PU010_20260916_121530.xlsx"


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


def test_move_to_overwrites_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "src"
    destination = tmp_path / "dst"
    source.mkdir()
    destination.mkdir()
    downloaded = source / "test_download.xlsx"
    downloaded.write_text("새 파일")
    (destination / "test_download.xlsx").write_text("기존 파일")

    moved = browser.move_to(downloaded, str(destination), stamp=False)

    assert moved.read_text() == "새 파일"
    assert not downloaded.exists()


def test_move_to_works_across_filesystems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def cross_device(*_: object) -> None:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(browser.os, "replace", cross_device)
    downloaded = tmp_path / "test_download.xlsx"
    downloaded.write_text("내용")
    destination = tmp_path / "dst"

    moved = browser.move_to(downloaded, str(destination))

    assert moved.read_text() == "내용"
    assert not downloaded.exists()


class Shown:
    def __init__(self, shown: bool = True, stubborn: bool = False) -> None:
        self.shown = shown
        self.stubborn = stubborn
        self.clicked = False

    def is_displayed(self) -> bool:
        return self.shown

    def click(self) -> None:
        if self.stubborn:
            raise RuntimeError("가려져 있습니다")
        self.clicked = True


class Page:
    def __init__(self, elements: list[Shown]) -> None:
        self.elements = elements
        self.scripted: list[Any] = []

    def find_elements(self, by: str, locator: str) -> list[Shown]:
        return self.elements

    def execute_script(self, script: str, *args: Any) -> None:
        self.scripted.append(args)


def test_click_if_shown_presses_what_is_visible() -> None:
    page = Page([Shown(), Shown(shown=False), Shown()])

    assert browser.click_if_shown(page, "css", "button") == 2
    assert [element.clicked for element in page.elements] == [True, False, True]


def test_click_if_shown_falls_back_to_a_script_click() -> None:
    page = Page([Shown(stubborn=True)])

    assert browser.click_if_shown(page, "css", "button") == 1
    assert page.scripted


def test_click_if_shown_is_quiet_when_nothing_is_there() -> None:
    assert browser.click_if_shown(Page([]), "css", "button") == 0


def test_a_page_that_refuses_scripts_hides_nothing() -> None:
    from gc_rpa_core import browser

    class Stubborn:
        def execute_script(self, _script: str) -> int:
            raise RuntimeError("스크립트를 막았습니다")

    assert browser.hide_toolbars(Stubborn()) == 0  # type: ignore[arg-type]


def test_the_toolbar_words_reach_the_script() -> None:
    from gc_rpa_core import browser

    seen: list[str] = []

    class Page:
        def execute_script(self, script: str) -> int:
            seen.append(script)
            return 2

    assert browser.hide_toolbars(Page()) == 2  # type: ignore[arg-type]
    assert "결재" in seen[0]
    assert "MARKS" not in seen[0]
