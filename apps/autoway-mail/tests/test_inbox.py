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
    assert found.subject == ""


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


def pane(**texts: str) -> Any:
    return FakePane(
        {
            inbox.READ_SENDER: texts.get("sender", ""),
            inbox.READ_DATE: texts.get("date", ""),
            inbox.READ_TITLE: texts.get("title", ""),
        }
    )


def test_the_read_pane_fills_an_empty_listing() -> None:
    found = listing()

    assert inbox.fill_missing(
        pane(sender="보낸이", date="2026-09-17 오후 1:25", title="[긴급] 정산 자료"), found
    )
    assert found.sender == "보낸이"
    assert inbox.clean_digits(found.received_at) == "20260917125"
    assert inbox.clean_text(found.subject) == "긴급 정산 자료"


def test_the_display_name_replaces_the_address() -> None:
    found = listing(subject="제목", received_at="202609170930", sender_mail="a@b.c")

    assert found.sender == "a@b.c"
    assert inbox.fill_missing(pane(sender="보낸이"), found)
    assert found.sender == "보낸이"


def test_a_pane_without_a_display_name_keeps_the_address() -> None:
    found = listing(subject="제목", received_at="202609170930", sender_mail="a@b.c")

    assert not inbox.fill_missing(pane(sender="   "), found)
    assert found.sender == "a@b.c"


def test_a_complete_listing_is_left_alone() -> None:
    found = listing(subject="제목", received_at="202609170930", sender_name="보낸이")

    assert not inbox.fill_missing(FakePane({}), found)  # type: ignore[arg-type]


def test_a_missing_subject_with_no_pane_is_an_error() -> None:
    with pytest.raises(inbox.InboxError, match="제목"):
        inbox.fill_missing(FakePane({}), listing())  # type: ignore[arg-type]


def test_a_stale_list_is_read_again(monkeypatch: pytest.MonkeyPatch) -> None:
    from selenium.common.exceptions import StaleElementReferenceException

    monkeypatch.setattr(inbox, "LIST_RETRY_PAUSE", 0)
    attempts: list[int] = []

    def flaky(_driver: Any, position: int) -> Listing | None:
        attempts.append(position)
        if len(attempts) < 3:
            raise StaleElementReferenceException("stale")
        return listing(message_id="m1")

    monkeypatch.setattr(inbox, "look_up_listing", flaky)

    found = inbox.listing_at(object(), 0)  # type: ignore[arg-type]

    assert found is not None and found.key == "m1"
    assert len(attempts) == 3


def test_a_list_that_never_settles_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from selenium.common.exceptions import StaleElementReferenceException

    monkeypatch.setattr(inbox, "LIST_RETRY_PAUSE", 0)

    def always(*_a: Any, **_k: Any) -> Listing | None:
        raise StaleElementReferenceException("stale")

    monkeypatch.setattr(inbox, "look_up_listing", always)

    with pytest.raises(inbox.InboxError, match="5회 읽었으나"):
        inbox.listing_at(object(), 0)  # type: ignore[arg-type]


def test_an_empty_list_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inbox, "LIST_RETRY_PAUSE", 0)
    calls: list[int] = []

    def empty(_driver: Any, position: int) -> Listing | None:
        calls.append(position)
        return None

    monkeypatch.setattr(inbox, "look_up_listing", empty)

    assert inbox.listing_at(object(), 0) is None  # type: ignore[arg-type]
    assert len(calls) == 1


def test_a_dead_session_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inbox, "LIST_RETRY_PAUSE", 0)

    def dead(*_a: Any, **_k: Any) -> Listing | None:
        raise RuntimeError("invalid session id")

    monkeypatch.setattr(inbox, "look_up_listing", dead)

    with pytest.raises(RuntimeError, match="invalid session id"):
        inbox.listing_at(object(), 0)  # type: ignore[arg-type]
