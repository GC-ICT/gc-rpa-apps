from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from selenium.webdriver.remote.webdriver import WebDriver

from autoway_mail import capture, common, erp, history, inbox
from gc_rpa_core import config
from gc_rpa_core.browser import RendererHangError, session_dead

TASK_CODE = "MAIL"

MAX_MAILS = 15
MAX_FAILURES = 10
LISTED_LIMIT = 20

FAILED_FOLDER = "failed"
HOLDING_FOLDER = "holding"

logger = logging.getLogger(__name__)


class Step(Enum):
    OPEN = "메일 열기"
    FOLDER = "폴더 생성"
    ATTACHMENTS = "첨부 저장"
    EML = "EML 저장"
    PDF = "본문 PDF"
    REGISTER = "ERP 등록"
    MOVE = "접수함 이동"


class Outcome(Enum):
    REGISTERED = "등록"
    MOVED = "이동"


class StepError(RuntimeError):
    def __init__(self, step: Step, cause: BaseException, folder: Path | None) -> None:
        super().__init__(f"[{step.value}] {cause}")
        self.step = step
        self.cause = cause
        self.folder = folder


@dataclass
class Tally:
    done: int = 0
    failed: int = 0
    secured: int = 0
    quarantined: int = 0
    stopped: str = ""

    @property
    def summary(self) -> str:
        text = f"성공 {self.done}건, 실패 {self.failed}건"
        if self.secured:
            text += f", 보안메일 {self.secured}건"
        if self.quarantined:
            text += f", 격리 {self.quarantined}건"
        if self.stopped:
            text += f" ({self.stopped}으로 조기 종료)"
        return text


@dataclass
class Session:
    driver: WebDriver
    settings: config.RpaConfig
    erp_target: erp.Target
    workspace: Path
    downloads: Path
    store: history.History
    report: Callable[[str], None] = lambda _: None

    @property
    def failed_dir(self) -> Path:
        return self.workspace / FAILED_FOLDER

    @property
    def holding_dir(self) -> Path:
        return self.workspace / HOLDING_FOLDER


def unique_dir(parent: Path, name: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    candidate = parent / name
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = parent / f"{name}_{suffix}"
    return candidate


def make_folder(session: Session, listing: inbox.Listing) -> Path:
    stamp = inbox.clean_digits(listing.received_at)
    folder = unique_dir(session.workspace, f"{stamp}_{inbox.safe_name(listing.sender)}")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def hold(session: Session, folder: Path) -> Path:
    moved = unique_dir(session.holding_dir, folder.name)
    shutil.move(str(folder), str(moved))
    return moved


def discard(folder: Path) -> None:
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        logger.warning("      올린 폴더를 지우지 못했습니다: %s (%s)", folder, exc)


def keep_failure(session: Session, folder: Path | None) -> None:
    if folder is None or not folder.is_dir():
        return
    try:
        capture.gather_downloads(session.downloads, folder)
        kept = unique_dir(session.failed_dir, folder.name)
        shutil.move(str(folder), str(kept))
        logger.info("      실패 폴더를 보관했습니다: %s", kept)
    except Exception as exc:
        logger.warning("      실패 폴더 보관을 건너뜁니다: %s", exc)


def recover(session: Session, folder: Path | None) -> None:
    inbox.settle(session.driver)
    keep_failure(session, folder)


def remember(session: Session, listing: inbox.Listing) -> None:
    if not listing.key:
        return
    session.store.remember(
        listing.key,
        mid=listing.mid,
        sender=listing.sender,
        subject=listing.subject,
        received_at=listing.received_at,
    )


def process(session: Session, listing: inbox.Listing) -> tuple[Outcome, str]:
    folder: Path | None = None
    step = Step.OPEN
    try:
        inbox.open_listing(session.driver, listing)
        if inbox.fill_missing(session.driver, listing):
            remember(session, listing)
        logger.info("      %s", listing.label)

        step = Step.FOLDER
        folder = make_folder(session, listing)

        step = Step.ATTACHMENTS
        capture.save_attachments(session.driver, folder, session.downloads)

        step = Step.EML
        capture.save_eml(session.driver, folder, session.downloads)

        step = Step.PDF
        pdf = capture.save_body_pdf(session.driver, folder)
        capture.save_page_images(pdf, common.poppler_path())

        step = Step.REGISTER
        folder = hold(session, folder)
        document_no = erp.register(
            folder,
            sender=listing.sender,
            subject=inbox.clean_text(listing.subject),
            target=session.erp_target,
        )
        if listing.key:
            session.store.mark_registered(listing.key, document_no)
        discard(folder)
        folder = None

        step = Step.MOVE
        inbox.windows_closed_to(session.driver, session.driver.current_window_handle)
        inbox.enter_mail_frame(session.driver)
        inbox.retry_move(session.driver)
        if listing.key:
            session.store.mark_done(listing.key)
        return Outcome.REGISTERED, document_no
    except Exception as exc:
        raise StepError(step, exc, folder) from exc


def move_registered(session: Session, listing: inbox.Listing) -> None:
    inbox.open_listing(session.driver, listing)
    inbox.windows_closed_to(session.driver, session.driver.current_window_handle)
    inbox.enter_mail_frame(session.driver)
    inbox.retry_move(session.driver)
    if listing.key:
        session.store.mark_done(listing.key)


def note_failure(session: Session, listing: inbox.Listing, step: Step, exc: BaseException) -> None:
    if not listing.key:
        return
    failures = session.store.mark_failed(listing.key, f"[{step.value}] {exc}")
    if failures >= history.QUARANTINE_THRESHOLD:
        logger.warning("      연속 %d회 실패로 격리합니다: %s", failures, listing.label)


def skip_reason(session: Session, listing: inbox.Listing, tally: Tally) -> str:
    if listing.secured:
        tally.secured += 1
        if listing.key:
            session.store.mark_secured(listing.key)
        return "보안메일이라 열지 않습니다"

    found = session.store.find(listing.key)
    if session.store.quarantined(found):
        tally.quarantined += 1
        return f"격리된 메일이라 열지 않습니다 (연속 실패 {found.failures if found else 0}회)"
    return ""


def run(session: Session) -> Tally:
    tally = Tally()
    position = 0

    while tally.done + tally.failed < MAX_MAILS:
        listing = inbox.listing_at(session.driver, position)
        if listing is None:
            break

        remember(session, listing)
        reason = skip_reason(session, listing, tally)
        if reason:
            logger.info("      %s: %s", reason, listing.label)
            position += 1
            continue

        found = session.store.find(listing.key)
        try:
            if found is not None and found.registered:
                logger.info("      이미 등록된 메일이라 이동만 합니다: %s", listing.label)
                move_registered(session, listing)
                outcome, document_no = Outcome.MOVED, found.document_no
            else:
                outcome, document_no = process(session, listing)
        except StepError as failure:
            tally.failed += 1
            position += 1
            if not stop_after(session, listing, failure, tally):
                continue
            break
        except Exception as exc:
            tally.failed += 1
            position += 1
            logger.error("      실패: %s / %s", listing.label, exc)
            if session_dead(exc):
                tally.stopped = "드라이버 세션 끊김"
                break
            note_failure(session, listing, Step.MOVE, exc)
            recover(session, None)
            if tally.failed >= MAX_FAILURES:
                tally.stopped = f"실패 {MAX_FAILURES}회"
                break
            continue

        tally.done += 1
        detail = f"{outcome.value} {document_no}".strip()
        logger.info("      %s / 누적 %d건 | %s", detail, tally.done, listing.label)
        session.report(f"{detail} | {listing.label} ({tally.done}/{MAX_MAILS})")

    return tally


def stop_after(session: Session, listing: inbox.Listing, failure: StepError, tally: Tally) -> bool:
    step, cause = failure.step, failure.cause

    if isinstance(cause, RendererHangError):
        logger.error("      [%s] 렌더러 무응답: %s", step.value, listing.label)
        if listing.key:
            session.store.quarantine(listing.key, f"[{step.value}] {cause}")
            logger.warning("      즉시 격리합니다: %s", listing.label)
        tally.stopped = "렌더러 무응답"
        return True

    logger.error("      [%s] 실패: %s / %s", step.value, listing.label, cause)
    if session_dead(cause):
        tally.stopped = "드라이버 세션 끊김"
        return True

    note_failure(session, listing, step, cause)
    recover(session, failure.folder)
    if tally.failed >= MAX_FAILURES:
        tally.stopped = f"실패 {MAX_FAILURES}회"
        return True
    return False


def report_listed(title: str, records: tuple[history.Record, ...], note: str) -> None:
    if not records:
        return
    logger.warning("%s %d건 (%s)", title, len(records), note)
    for record in records[:LISTED_LIMIT]:
        logger.warning("  - %s / 수신 %s", record.label, record.received_at)
    if len(records) > LISTED_LIMIT:
        logger.warning("  ... 외 %d건", len(records) - LISTED_LIMIT)
