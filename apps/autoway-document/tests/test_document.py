from pathlib import Path
from typing import Any

import pytest

from autoway_document import document


class FakeElement:
    def __init__(self, text: str = "", attributes: dict[str, str] | None = None) -> None:
        self.text = text
        self.attributes = attributes or {}
        self.clicked = False
        self.shown = True

    def get_attribute(self, name: str) -> str:
        return self.attributes.get(name, "")

    def is_displayed(self) -> bool:
        return self.shown

    def click(self) -> None:
        self.clicked = True

    def find_element(self, by: str, locator: str) -> "FakeElement":
        return self


class FakeSwitch:
    def __init__(self) -> None:
        self.handle = "main"

    def default_content(self) -> None:
        return None

    def window(self, handle: str) -> None:
        self.handle = handle


class FakeDriver:
    def __init__(self, fields: dict[str, FakeElement] | None = None) -> None:
        self.fields = fields or {}
        self.switch_to = FakeSwitch()
        self.window_handles = ["main"]
        self.current_window_handle = "main"
        self.scripted: list[str] = []

    def execute_script(self, script: str, *_args: Any) -> None:
        self.scripted.append(script)

    def find_elements(self, by: str, locator: str) -> list[FakeElement]:
        found = self.fields.get(locator)
        return [found] if found is not None else []


@pytest.fixture
def straight_to_page(monkeypatch: pytest.MonkeyPatch) -> None:
    def look(driver: Any, by: str, locator: str, **_k: Any) -> Any:
        return driver.fields.get(locator)

    monkeypatch.setattr(document, "find_in_frames", look)
    monkeypatch.setattr(document, "wait_ready", lambda *_a, **_k: None)


def test_a_globis_writer_is_named_in_full(straight_to_page: None) -> None:
    driver = FakeDriver(
        {
            document.NUMBER_FIELD: FakeElement("2026-000123"),
            document.WRITER_FIELD: FakeElement("현대글로비스 물류팀"),
            document.TITLE_FIELD: FakeElement("9월 정산 자료"),
        }
    )

    read = document.read_document(driver)

    assert read == document.Document("2026-000123", "현대글로비스", "9월 정산 자료")


def test_any_other_writer_counts_as_hmc(straight_to_page: None) -> None:
    driver = FakeDriver(
        {
            document.NUMBER_FIELD: FakeElement("2026-000124"),
            document.WRITER_FIELD: FakeElement("현대자동차 구매팀"),
            document.TITLE_FIELD: FakeElement("제목"),
        }
    )

    assert document.read_document(driver).sender == "HMC"


def test_the_document_number_falls_back_to_the_text_field(straight_to_page: None) -> None:
    driver = FakeDriver(
        {
            document.NUMBER_FIELD: FakeElement(""),
            document.NUMBER_FALLBACK: FakeElement("2026-000125"),
            document.TITLE_FIELD: FakeElement("제목"),
        }
    )

    assert document.read_document(driver).number == "2026-000125"


def test_a_document_without_a_number_is_refused(straight_to_page: None) -> None:
    with pytest.raises(document.DocumentError, match="문서번호"):
        document.read_document(FakeDriver())


@pytest.mark.parametrize(
    "attributes",
    [{"disabled": "disabled"}, {"aria-disabled": "true"}, {"class": "ant-btn ant-btn-disabled"}],
)
def test_a_dead_save_button_is_noticed(attributes: dict[str, str]) -> None:
    assert document.disabled(FakeElement(attributes=attributes)) is True


def test_a_live_save_button_is_not_dead() -> None:
    assert document.disabled(FakeElement(attributes={"class": "ant-btn"})) is False


def test_no_save_button_means_no_attachments(
    straight_to_page: None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger=document.__name__):
        saved = document.save_attachments(FakeDriver(), tmp_path, tmp_path)

    assert saved == 0
    assert "첨부 없음" in caplog.text


def test_an_empty_list_captures_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(document, "open_approval", lambda _d: None)
    monkeypatch.setattr(document, "first_row", lambda _d: None)

    assert document.capture_one(FakeDriver(), workspace=tmp_path, downloads=tmp_path) is None


def test_a_new_window_takes_the_focus() -> None:
    driver = FakeDriver()
    driver.window_handles = ["main", "popup"]

    assert document.focus_new_window(driver, {"main"}) is True
    assert driver.switch_to.handle == "popup"


def test_no_new_window_leaves_the_focus_alone() -> None:
    driver = FakeDriver()

    assert document.focus_new_window(driver, {"main"}) is False
    assert driver.switch_to.handle == "main"


def test_a_missing_link_says_what_it_looked_for(straight_to_page: None) -> None:
    with pytest.raises(document.DocumentError, match="결재 링크"):
        document.click_in_frames(FakeDriver(), document.APPROVAL_LINK, "결재 링크", timeout=0)


def test_the_pdf_is_written_from_the_printed_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import base64

    monkeypatch.setattr(
        document,
        "call_cdp",
        lambda *_a, **_k: {"data": base64.b64encode(b"%PDF-1.4 ...").decode()},
    )

    path = document.save_pdf(FakeDriver(), tmp_path, "2026-000123")

    assert path.name == "2026-000123.pdf"
    assert path.read_bytes().startswith(b"%PDF")


def test_an_empty_print_result_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(document, "call_cdp", lambda *_a, **_k: {"data": ""})

    with pytest.raises(document.DocumentError, match="빈 결과"):
        document.save_pdf(FakeDriver(), tmp_path, "2026-000123")
