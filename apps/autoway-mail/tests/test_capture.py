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


class FakeWindows:
    def __init__(self, opens_after: int) -> None:
        self.opens_after = opens_after
        self.looks = 0
        self.current = "main"
        self.ready_waits = 0

    @property
    def window_handles(self) -> list[str]:
        self.looks += 1
        return ["main", "popup"] if self.looks > self.opens_after else ["main"]

    @property
    def switch_to(self) -> "FakeWindows":
        return self

    def window(self, handle: str) -> None:
        self.current = handle


def test_the_popup_is_waited_for(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeWindows(opens_after=3)
    monkeypatch.setattr(capture, "POPUP_SETTLE", 0)
    monkeypatch.setattr(capture, "wait_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(capture, "wait_for_body", lambda *_a, **_k: None)

    capture.focus_popup(driver, {"main"})  # type: ignore[arg-type]

    assert driver.current == "popup"
    assert driver.looks > 3


def test_a_popup_that_never_opens_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeWindows(opens_after=10_000)
    monkeypatch.setattr(capture, "wait_ready", lambda *_a, **_k: None)

    with pytest.raises(capture.CaptureError, match="열리지 않았습니다"):
        capture.focus_popup(driver, {"main"}, timeout=0.3)  # type: ignore[arg-type]


def test_the_popup_page_is_waited_for_before_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeWindows(opens_after=0)
    waited: list[object] = []
    monkeypatch.setattr(capture, "POPUP_SETTLE", 0)
    monkeypatch.setattr(capture, "wait_for_body", lambda *_a, **_k: None)
    monkeypatch.setattr(capture, "wait_ready", lambda d, **_k: waited.append(d))

    capture.focus_popup(driver, {"main"})  # type: ignore[arg-type]

    assert waited == [driver]


class FakeBody:
    def __init__(self, lengths: list[int]) -> None:
        self.lengths = lengths
        self.asked = 0

    def execute_script(self, _script: str) -> int:
        value = self.lengths[min(self.asked, len(self.lengths) - 1)]
        self.asked += 1
        return value


def test_the_body_is_waited_for_until_it_settles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "BODY_POLL", 0)
    driver = FakeBody([0, 120, 400, 400])

    capture.wait_for_body(driver, timeout=5)  # type: ignore[arg-type]

    assert driver.asked == 4


def test_a_body_still_growing_is_not_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "BODY_POLL", 0)
    driver = FakeBody([100, 200, 300, 300])

    capture.wait_for_body(driver, timeout=5)  # type: ignore[arg-type]

    assert driver.asked == 4


def test_a_body_that_stays_empty_is_reported(caplog: pytest.LogCaptureFixture) -> None:
    driver = FakeBody([0, 0])

    with caplog.at_level("WARNING", logger=capture.logger.name):
        capture.wait_for_body(driver, timeout=0.3)  # type: ignore[arg-type]

    assert "본문이" in caplog.text


def test_a_window_left_open_earlier_is_not_mistaken_for_the_popup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Leftover(FakeWindows):
        @property
        def window_handles(self) -> list[str]:
            self.looks += 1
            if self.looks > self.opens_after:
                return ["main", "stray", "popup"]
            return ["main", "stray"]

    driver = Leftover(opens_after=2)
    monkeypatch.setattr(capture, "POPUP_SETTLE", 0)
    monkeypatch.setattr(capture, "wait_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(capture, "wait_for_body", lambda *_a, **_k: None)

    capture.focus_popup(driver, {"main", "stray"})  # type: ignore[arg-type]

    assert driver.current == "popup"


class FakePage:
    def __init__(self, measured: tuple[float, float]) -> None:
        self.measured = measured

    def execute_script(self, _script: str) -> list[float]:
        return list(self.measured)


def sized(monkeypatch: pytest.MonkeyPatch, reported: tuple[float, float]) -> None:
    monkeypatch.setattr(
        capture,
        "call_cdp",
        lambda *_a, **_k: {"cssContentSize": {"width": reported[0], "height": reported[1]}},
    )


def test_the_page_is_as_tall_as_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    sized(monkeypatch, (960, 1080))

    page = capture.whole_page(FakePage((960, 9600)))  # type: ignore[arg-type]

    assert page["paperHeight"] == pytest.approx(100.0 + capture.PAGE_PADDING)
    assert page["paperWidth"] == pytest.approx(10.0 + capture.PAGE_PADDING)


def test_a_very_long_body_is_split_into_sheets(monkeypatch: pytest.MonkeyPatch) -> None:
    sized(monkeypatch, (960, 96000))

    page = capture.whole_page(FakePage((960, 96000)))  # type: ignore[arg-type]

    assert page["paperHeight"] == capture.A4_HEIGHT


def test_an_unmeasurable_page_falls_back_to_a4(monkeypatch: pytest.MonkeyPatch) -> None:
    sized(monkeypatch, (0, 0))

    page = capture.whole_page(FakePage((0, 0)))  # type: ignore[arg-type]

    assert (page["paperWidth"], page["paperHeight"]) == (capture.A4_WIDTH, capture.A4_HEIGHT)
