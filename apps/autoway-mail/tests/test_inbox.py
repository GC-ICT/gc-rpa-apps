from typing import Any

import pytest

from autoway_mail import inbox
from autoway_mail.inbox import Listing


def listing(**fields: str) -> Listing:
    return Listing(element=object(), **fields)  # type: ignore[arg-type]


def test_key_prefers_the_message_id() -> None:
    assert listing(message_id="  m1 ", mid="mid-1").key == "m1"


def test_key_falls_back_to_the_mid() -> None:
    assert listing(message_id="  ", mid="mid-1").key == "mid-1"


def test_key_is_empty_when_neither_is_present() -> None:
    assert listing().key == ""


def test_sender_prefers_the_display_name() -> None:
    assert listing(sender_name="보낸이", sender_mail="a@b.c").sender == "보낸이"


def test_sender_falls_back_to_the_address() -> None:
    assert listing(sender_mail="a@b.c").sender == "a@b.c"


def test_readable_needs_a_subject_or_a_date() -> None:
    assert not listing().readable
    assert listing(subject="제목").readable
    assert listing(received_at="202609170930").readable


def test_security_mail_is_spotted_by_notify_type() -> None:
    assert listing(notify_type="securitymail").secured


def test_security_mail_is_spotted_by_id_alone() -> None:
    assert listing(secure_id="7355268").secured


def test_an_ordinary_mail_is_not_secured() -> None:
    assert not listing(notify_type="", secure_id="  ").secured


def test_clean_text_drops_punctuation() -> None:
    assert inbox.clean_text("[긴급] 정산 자료(9월)!") == "긴급 정산 자료9월"


def test_clean_digits_keeps_only_numbers() -> None:
    assert inbox.clean_digits("2026-07-24 13:25") == "202607241325"


def test_safe_name_replaces_path_characters() -> None:
    assert inbox.safe_name("보낸이/이름:주소") == "보낸이_이름_주소"


def test_safe_name_is_capped() -> None:
    assert len(inbox.safe_name("가" * 200)) == 60


def test_label_reads_as_sender_then_subject() -> None:
    assert listing(sender_name="보낸이", subject="제목").label == "[보낸이] 제목"


class FakeElement:
    def __init__(self, attributes: dict[str, str], sender: str = "") -> None:
        self.attributes = attributes
        self.sender = sender

    def find_element(self, by: str, locator: str) -> Any:
        from selenium.common.exceptions import NoSuchElementException

        if locator == inbox.ROW_CHECKBOX:
            return self
        if locator == inbox.SENDER_NAME:
            if not self.sender:
                raise NoSuchElementException(locator)
            return FakeText(self.sender)
        raise NoSuchElementException(locator)

    def get_attribute(self, name: str) -> str | None:
        return self.attributes.get(name)


class FakeText:
    def __init__(self, text: str) -> None:
        self.text = text


def test_read_listing_maps_every_attribute() -> None:
    element = FakeElement(
        {
            "messageid": "m1",
            "mid": "mid-1",
            "subject": "제목",
            "sendermail": "a@b.c",
            "receivedate": "202609170930",
            "notifytype": "",
            "securitymailid": "",
        },
        sender="보낸이",
    )

    found = inbox.read_listing(element)  # type: ignore[arg-type]

    assert found.key == "m1"
    assert found.subject == "제목"
    assert found.sender == "보낸이"
    assert found.received_at == "202609170930"


def test_read_listing_survives_a_row_without_a_checkbox() -> None:
    from selenium.common.exceptions import NoSuchElementException

    class Bare:
        def find_element(self, by: str, locator: str) -> Any:
            raise NoSuchElementException(locator)

    found = inbox.read_listing(Bare())  # type: ignore[arg-type]

    assert found.key == ""
    assert not found.readable


def test_read_listing_survives_a_missing_sender_name() -> None:
    element = FakeElement({"messageid": "m1", "sendermail": "a@b.c"})

    assert inbox.read_listing(element).sender == "a@b.c"  # type: ignore[arg-type]


class FakePane:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts

    def find_element(self, by: str, locator: str) -> Any:
        from selenium.common.exceptions import NoSuchElementException

        if locator not in self.texts:
            raise NoSuchElementException(locator)
        return FakeText(self.texts[locator])


def test_the_read_pane_fills_an_unreadable_listing() -> None:
    driver = FakePane(
        {
            inbox.READ_SENDER: "보낸이",
            inbox.READ_DATE: "2026-09-17 오후 1:25",
            inbox.READ_TITLE: "[긴급] 정산 자료",
        }
    )
    found = listing()

    assert not found.readable
    inbox.fill_from_pane(driver, found)  # type: ignore[arg-type]

    assert found.readable
    assert found.sender == "보낸이"
    assert inbox.clean_digits(found.received_at) == "20260917125"
    assert inbox.clean_text(found.subject) == "긴급 정산 자료"


def test_a_missing_read_pane_field_is_an_error() -> None:
    driver = FakePane({inbox.READ_SENDER: "보낸이"})

    with pytest.raises(inbox.InboxError, match="수신일시"):
        inbox.fill_from_pane(driver, listing())  # type: ignore[arg-type]
