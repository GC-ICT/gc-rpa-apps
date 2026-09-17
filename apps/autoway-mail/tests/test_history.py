from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autoway_mail import history
from autoway_mail.history import History, Record


@pytest.fixture
def store(tmp_path: Path) -> History:
    return History(tmp_path / "mail.db")


def remember(store: History, key: str = "m1") -> None:
    store.remember(key, mid="mid-1", sender="보낸이", subject="제목", received_at="202609170930")


def test_find_returns_nothing_for_an_unknown_mail(store: History) -> None:
    assert store.find("없는키") is None


def test_find_returns_nothing_for_an_empty_key(store: History) -> None:
    assert store.find("") is None


def test_remember_keeps_the_list_fields(store: History) -> None:
    remember(store)
    found = store.find("m1")

    assert found is not None
    assert found.subject == "제목"
    assert found.label == "[보낸이] 제목"
    assert not found.registered


def test_remember_twice_refreshes_instead_of_duplicating(store: History) -> None:
    remember(store)
    store.remember("m1", mid="mid-1", sender="보낸이", subject="바뀐 제목", received_at="")

    found = store.find("m1")
    assert found is not None
    assert found.subject == "바뀐 제목"


def test_remember_does_not_clear_the_document_number(store: History) -> None:
    remember(store)
    store.mark_registered("m1", "HR-1")
    remember(store)

    found = store.find("m1")
    assert found is not None
    assert found.document_no == "HR-1"


def test_registered_mail_is_marked(store: History) -> None:
    remember(store)
    store.mark_registered("m1", "HR-1")

    found = store.find("m1")
    assert found is not None
    assert found.registered


def test_failures_add_up(store: History) -> None:
    remember(store)

    assert store.mark_failed("m1", "첫 실패") == 1
    assert store.mark_failed("m1", "둘째 실패") == 2


def test_done_clears_the_failure_streak(store: History) -> None:
    remember(store)
    store.mark_failed("m1", "실패")
    store.mark_done("m1")

    found = store.find("m1")
    assert found is not None
    assert found.failures == 0
    assert found.last_error == ""


def test_a_long_error_is_trimmed(store: History) -> None:
    remember(store)
    store.mark_failed("m1", "가" * 900)

    found = store.find("m1")
    assert found is not None
    assert len(found.last_error) == 500


def test_quarantine_needs_the_threshold(store: History) -> None:
    remember(store)
    for _ in range(history.QUARANTINE_THRESHOLD - 1):
        store.mark_failed("m1", "실패")

    assert not store.quarantined(store.find("m1"))

    store.mark_failed("m1", "실패")
    assert store.quarantined(store.find("m1"))


def test_quarantine_lapses_after_the_retry_window(store: History) -> None:
    remember(store)
    store.quarantine("m1", "렌더러 무응답")
    found = store.find("m1")

    later = datetime.now() + history.QUARANTINE_RETRY + timedelta(minutes=1)
    assert store.quarantined(found)
    assert not store.quarantined(found, moment=later)


def test_quarantine_holds_when_the_timestamp_is_unreadable(store: History) -> None:
    broken = Record("m1", "", "", "", "", "", history.QUARANTINE_THRESHOLD, "", "그날", False)

    assert store.quarantined(broken)


def test_nothing_is_quarantined_without_a_record(store: History) -> None:
    assert not store.quarantined(None)


def test_quarantine_skips_the_threshold_wait(store: History) -> None:
    remember(store)
    store.quarantine("m1", "렌더러 무응답")

    assert [record.key for record in store.quarantined_mails()] == ["m1"]


def test_secured_mails_are_listed(store: History) -> None:
    remember(store)
    store.mark_secured("m1")

    listed = store.secured_mails()
    assert [record.key for record in listed] == ["m1"]
    assert listed[0].secured


def test_history_survives_being_reopened(tmp_path: Path) -> None:
    path = tmp_path / "mail.db"
    with history.opened(path) as first:
        first.remember("m1", mid="", sender="보낸이", subject="제목", received_at="")
        first.mark_registered("m1", "HR-1")

    with history.opened(path) as second:
        found = second.find("m1")

    assert found is not None
    assert found.document_no == "HR-1"
