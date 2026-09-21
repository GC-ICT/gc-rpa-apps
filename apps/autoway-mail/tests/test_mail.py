from pathlib import Path
from typing import Any

import pytest

from autoway_mail import capture, history, inbox, mail
from autoway_mail.inbox import Listing
from autoway_mail.mail import Outcome, Session, Step, StepError, Tally
from gc_rpa_autoway import erp
from gc_rpa_core.browser import RendererHangError
from gc_rpa_core.db import DbEndpoint


class FakeDriver:
    def __init__(self) -> None:
        self.current_window_handle = "main"
        self.window_handles = ["main"]


def listing(key: str = "m1", subject: str = "제목", **fields: str) -> Listing:
    return Listing(
        element=object(),  # type: ignore[arg-type]
        message_id=key,
        subject=subject,
        sender_name="보낸이",
        received_at="2026-09-17 09:30",
        **fields,
    )


def erp_target() -> erp.Target:
    return erp.Target(
        endpoint=DbEndpoint("test-erp.invalid", None, "ERP", "user", "pw"),
        header="EXEC [ERP].[dbo].[HRA700_Work] @_send_cust = {sender}",
        file_table="[ERPFileDB].[dbo].[HRA700_File]",
        key_column="mail_no",
    )


@pytest.fixture
def session(tmp_path: Path, rpa_settings: Any) -> Session:
    store = history.History(tmp_path / "history.db")
    downloads = tmp_path / "download"
    downloads.mkdir()
    return Session(
        driver=FakeDriver(),  # type: ignore[arg-type]
        settings=rpa_settings,
        erp_target=erp_target(),
        workspace=tmp_path,
        downloads=downloads,
        store=store,
    )


class FakeInbox:
    def __init__(self, listings: list[Listing]) -> None:
        self.remaining = list(listings)
        self.opened: Listing | None = None
        self.leaving: list[Listing] = []

    def at(self, _driver: Any, position: int) -> Listing | None:
        return self.remaining[position] if position < len(self.remaining) else None

    def open(self, _driver: Any, found: Listing) -> None:
        self.opened = found

    def leave(self, *_a: Any, **_k: Any) -> None:
        if self.opened is None:
            return
        self.leaving.append(self.opened)
        self.remaining = [found for found in self.remaining if found is not self.opened]
        self.opened = None


@pytest.fixture(autouse=True)
def no_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("enter_mail_frame", "settle"):
        monkeypatch.setattr(inbox, name, lambda *_a, **_k: None)
    monkeypatch.setattr(mail, "close_other_windows", lambda *_a, **_k: 0)
    monkeypatch.setattr(capture, "close_other_windows", lambda *_a, **_k: 0)
    monkeypatch.setattr(inbox, "fill_missing", lambda *_a: False)
    monkeypatch.setattr(capture, "save_attachments", lambda *_a, **_k: 0)
    monkeypatch.setattr(capture, "save_eml", lambda *_a, **_k: 0)
    monkeypatch.setattr(capture, "save_page_images", lambda *_a, **_k: [])
    monkeypatch.setattr(capture, "DOWNLOAD_START_GRACE", 0.01)
    monkeypatch.setattr(capture, "DOWNLOAD_TIMEOUT", 0.05)


def feed(monkeypatch: pytest.MonkeyPatch, listings: list[Listing]) -> FakeInbox:
    fake = FakeInbox(listings)
    monkeypatch.setattr(inbox, "listing_at", fake.at)
    monkeypatch.setattr(inbox, "open_listing", fake.open)
    monkeypatch.setattr(inbox, "retry_move", fake.leave)
    return fake


def writes_pdf(session: Session) -> Any:
    def save(_driver: Any, folder: Path) -> Path:
        path = folder / "document.pdf"
        path.write_bytes(b"%PDF-")
        return path

    return save


def test_folder_name_uses_the_received_stamp_and_sender(session: Session) -> None:
    folder = mail.make_folder(session, listing())

    assert folder.name == "202609170930_보낸이"


def test_folder_name_avoids_collisions(session: Session) -> None:
    first = mail.make_folder(session, listing())
    second = mail.make_folder(session, listing())

    assert first != second
    assert second.name.endswith("_2")


def test_a_registered_mail_is_only_moved(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    session.store.remember("m1", mid="", sender="보낸이", subject="제목", received_at="")
    session.store.mark_registered("m1", "HR-1")
    feed(monkeypatch, [listing()])
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: pytest.fail("다시 등록하면 안 됩니다"))

    tally = mail.run(session)

    assert tally.done == 1
    assert tally.failed == 0


def test_a_secured_mail_is_never_opened(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    feed(monkeypatch, [listing(notify_type="SECURITYMAIL")])
    monkeypatch.setattr(inbox, "open_listing", lambda *_a: pytest.fail("보안메일은 열면 안 됩니다"))

    tally = mail.run(session)

    assert tally.secured == 1
    assert tally.done == 0
    assert [record.key for record in session.store.secured_mails()] == ["m1"]


def test_a_quarantined_mail_is_never_opened(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.store.remember("m1", mid="", sender="보낸이", subject="제목", received_at="")
    session.store.quarantine("m1", "렌더러 무응답")
    monkeypatch.setattr(
        inbox, "open_listing", lambda *_a: pytest.fail("격리 메일은 열면 안 됩니다")
    )
    feed(monkeypatch, [listing()])

    tally = mail.run(session)

    assert tally.quarantined == 1
    assert tally.failed == 0


def test_a_full_pass_registers_and_records(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing()])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")

    tally = mail.run(session)

    assert tally.done == 1
    found = session.store.find("m1")
    assert found is not None
    assert found.document_no == "HR-9"
    assert found.failures == 0


def test_the_document_number_survives_a_move_failure(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing()])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")
    monkeypatch.setattr(
        inbox, "retry_move", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("이동 실패"))
    )

    tally = mail.run(session)

    assert tally.failed == 1
    found = session.store.find("m1")
    assert found is not None
    assert found.document_no == "HR-9"


def test_a_renderer_hang_quarantines_and_stops_the_run(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing(), listing("m2")])

    def hang(*_a: Any, **_k: Any) -> Path:
        raise RendererHangError("Page.printToPDF 가 20초 안에 끝나지 않았습니다")

    monkeypatch.setattr(capture, "save_body_pdf", hang)

    tally = mail.run(session)

    assert tally.stopped == "렌더러 무응답"
    assert tally.failed == 1
    assert session.store.quarantined(session.store.find("m1"))


def test_a_dead_session_stops_the_run(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    feed(monkeypatch, [listing(), listing("m2")])

    def dead(*_a: Any, **_k: Any) -> Path:
        raise RuntimeError("invalid session id")

    monkeypatch.setattr(capture, "save_body_pdf", dead)

    tally = mail.run(session)

    assert tally.stopped == "드라이버 세션 끊김"
    assert tally.failed == 1


def test_an_ordinary_failure_moves_on_to_the_next_mail(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing(), listing("m2")])
    calls: list[str] = []

    def sometimes(_driver: Any, folder: Path) -> Path:
        calls.append(folder.name)
        if len(calls) == 1:
            raise RuntimeError("본문을 읽지 못했습니다")
        path = folder / "document.pdf"
        path.write_bytes(b"%PDF-")
        return path

    monkeypatch.setattr(capture, "save_body_pdf", sometimes)
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")

    tally = mail.run(session)

    assert (tally.done, tally.failed) == (1, 1)
    assert session.store.find("m1") is not None


def test_the_run_stops_after_too_many_failures(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing(f"m{n}") for n in range(mail.MAX_FAILURES + 5)])

    def always(*_a: Any, **_k: Any) -> Path:
        raise RuntimeError("본문을 읽지 못했습니다")

    monkeypatch.setattr(capture, "save_body_pdf", always)

    tally = mail.run(session)

    assert tally.failed == mail.MAX_FAILURES
    assert tally.stopped == f"실패 {mail.MAX_FAILURES}회"


def test_the_run_stops_at_the_mail_limit(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    feed(monkeypatch, [listing(f"m{n}") for n in range(mail.MAX_MAILS + 5)])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")

    tally = mail.run(session)

    assert tally.done == mail.MAX_MAILS


def test_an_empty_inbox_ends_the_run(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    feed(monkeypatch, [])

    tally = mail.run(session)

    assert (tally.done, tally.failed) == (0, 0)
    assert tally.summary == "성공 0건, 실패 0건"


def test_failed_folders_are_kept(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    feed(monkeypatch, [listing()])

    def boom(_driver: Any, folder: Path) -> Path:
        raise RuntimeError("본문을 읽지 못했습니다")

    monkeypatch.setattr(capture, "save_body_pdf", boom)

    mail.run(session)

    assert list(session.failed_dir.iterdir())


def test_step_error_carries_the_step_and_folder(tmp_path: Path) -> None:
    failure = StepError(Step.PDF, RuntimeError("원인"), tmp_path)

    assert failure.step is Step.PDF
    assert failure.folder == tmp_path
    assert "본문 PDF" in str(failure)


def test_summary_mentions_every_bucket() -> None:
    tally = Tally(done=3, failed=1, secured=2, quarantined=1, stopped="렌더러 무응답")

    assert (
        tally.summary == "성공 3건, 실패 1건, 보안메일 2건, 격리 1건 (렌더러 무응답으로 조기 종료)"
    )


def test_outcomes_read_in_korean() -> None:
    assert Outcome.REGISTERED.value == "등록"
    assert Outcome.MOVED.value == "이동"


def test_an_uploaded_folder_is_removed(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    feed(monkeypatch, [listing()])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")

    mail.run(session)

    assert not list(session.holding_dir.iterdir())


def test_a_folder_that_failed_after_upload_is_not_kept_as_a_failure(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing()])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")

    def refuse(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("이동 실패")

    monkeypatch.setattr(inbox, "retry_move", refuse)

    mail.run(session)

    assert not session.failed_dir.exists() or not list(session.failed_dir.iterdir())


def test_an_unreadable_listing_is_filled_from_the_read_pane(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = Listing(element=object(), message_id="m1")  # type: ignore[arg-type]
    feed(monkeypatch, [bare])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")

    def fill(_driver: Any, found: Listing) -> None:
        found.sender_name = "보낸이"
        found.received_at = "2026-09-17 13:25"
        found.subject = "제목"

    monkeypatch.setattr(inbox, "fill_missing", lambda d, f: bool(fill(d, f)) or True)

    assert mail.run(session).done == 1
    found = session.store.find("m1")
    assert found is not None
    assert found.subject == "제목"


def test_a_readable_listing_never_touches_the_read_pane(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed(monkeypatch, [listing()])
    monkeypatch.setattr(capture, "save_body_pdf", writes_pdf(session))
    monkeypatch.setattr(erp, "register", lambda *_a, **_k: "HR-9")
    monkeypatch.setattr(inbox, "fill_missing", lambda *_a: False)

    assert mail.run(session).done == 1
