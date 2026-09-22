from __future__ import annotations

import base64
import logging
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from gc_rpa_autoway import poppler
from gc_rpa_core.browser import (
    call_cdp,
    expand_page,
    find_in_frames,
    here_or_none,
    settled_files,
    wait_download,
    wait_ready,
)

APPROVAL_LINK = '//a[contains(@href, "approval.hmg-corp.io") and .//span[contains(text(), "결재")]]'
WAITING_MENU = (
    "/html/body/div/div/div/div/div/div/div[2]/aside/div/div[3]"
    "/div/ul/li[1]/ul/li[1]/span/p/span[1]"
)
DOCUMENT_ROW = '//tbody[contains(@class,"ant-table-tbody")]//tr[td[1]//input[@type="checkbox"]]'
ROW_SUBJECT = './/span[contains(@class, "ellipsis") and contains(@class, "line2")]'

NUMBER_FIELD = "_REG_NO_"
NUMBER_FALLBACK = "docNoText"
WRITER_FIELD = "_AP_TYPE_W_NM#1_"
TITLE_FIELD = "docTitle"

SAVE_ALL_BUTTON = '//button[.//span[normalize-space(text())="모두저장"]]'
APPROVE_BUTTON = '//button[.//span[normalize-space(text())="결재"]]'
AUTHORIZE_RADIO = 'input.ant-radio-input[type="radio"][value="AUTHORIZE"]'
CONFIRM_BUTTON = '//button[.//span[normalize-space(text())="확인"]]'
DISABLED_MARKS = ("true", "1", "yes")
ARCHIVE_SUFFIX = ".zip"

GLOBIS_MARK = "글로비스"
GLOBIS_NAME = "현대글로비스"
DEFAULT_SENDER = "HMC"

MENU_TIMEOUT = 20.0
FIELD_TIMEOUT = 8.0
BUTTON_TIMEOUT = 5.0
APPROVE_TIMEOUT = 8.0
DIALOG_SETTLE = 2.5
CHOICE_SETTLE = 1.0
APPROVE_SETTLE = 2.0

PDF_PARAMS = {
    "landscape": True,
    "printBackground": True,
    "preferCSSPageSize": False,
    "paperWidth": 11.69,
    "paperHeight": 8.27,
    "marginTop": 0.2,
    "marginBottom": 0.2,
    "marginLeft": 0.2,
    "marginRight": 0.2,
    "scale": 0.95,
}
PDF_TIMEOUT = 30.0

logger = logging.getLogger(__name__)


class DocumentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Document:
    number: str
    sender: str
    title: str


@dataclass(frozen=True)
class Captured:
    approvals: str
    document: Document
    folder: Path
    attachments: int
    pdf: Path
    images: list[Path]


def open_approval(driver: WebDriver) -> None:
    known = set(driver.window_handles)
    click_in_frames(driver, APPROVAL_LINK, "결재 링크", timeout=MENU_TIMEOUT)
    focus_new_window(driver, known)
    wait_ready(driver)
    click_in_frames(driver, WAITING_MENU, "결재 대기함 메뉴", timeout=MENU_TIMEOUT)
    wait_ready(driver)


def click_in_frames(
    driver: WebDriver, locator: str, what: str, *, by: str = By.XPATH, timeout: float
) -> WebElement:
    found = find_in_frames(driver, by, locator, timeout=timeout)
    if found is None:
        raise DocumentError(f"{what} 를 찾지 못했습니다")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", found)
    try:
        found.click()
    except Exception:
        driver.execute_script("arguments[0].click();", found)
    return found


def focus_new_window(driver: WebDriver, known: set[str]) -> bool:
    opened = [handle for handle in driver.window_handles if handle not in known]
    if not opened:
        return False
    driver.switch_to.window(opened[-1])
    return True


def first_row(driver: WebDriver) -> WebElement | None:
    return here_or_none(driver, By.XPATH, DOCUMENT_ROW)


def open_detail(driver: WebDriver, row: WebElement) -> None:
    known = set(driver.window_handles)
    subject = row.find_element(By.XPATH, ROW_SUBJECT)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", subject)
    subject.click()
    focus_new_window(driver, known)
    wait_ready(driver)


def field_text(driver: WebDriver, field: str, *, timeout: float = FIELD_TIMEOUT) -> str:
    found = find_in_frames(driver, By.ID, field, timeout=timeout)
    return found.text.strip() if found is not None else ""


def read_document(driver: WebDriver) -> Document:
    number = field_text(driver, NUMBER_FIELD) or field_text(
        driver, NUMBER_FALLBACK, timeout=BUTTON_TIMEOUT
    )
    if not number:
        raise DocumentError("문서번호를 찾지 못했습니다")

    writer = field_text(driver, WRITER_FIELD, timeout=BUTTON_TIMEOUT)
    sender = GLOBIS_NAME if GLOBIS_MARK in writer else DEFAULT_SENDER
    return Document(number=number, sender=sender, title=field_text(driver, TITLE_FIELD))


def disabled(button: WebElement) -> bool:
    if (button.get_attribute("disabled") or "").strip():
        return True
    if (button.get_attribute("aria-disabled") or "").strip().lower() in DISABLED_MARKS:
        return True
    return "disabled" in (button.get_attribute("class") or "").lower()


def unpack(archive: Path, folder: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as opened:
            opened.extractall(folder)
    except Exception as exc:
        logger.warning("      첨부 압축을 풀지 못해 그대로 둡니다: %s", exc)
        return
    archive.unlink(missing_ok=True)


def save_attachments(driver: WebDriver, folder: Path, downloads: Path) -> int:
    button = find_in_frames(driver, By.XPATH, SAVE_ALL_BUTTON, timeout=BUTTON_TIMEOUT)
    if button is None or not button.is_displayed() or disabled(button):
        logger.info("      첨부 없음")
        return 0

    before = settled_files(downloads)
    button.click()
    archive = wait_download(downloads, before=before)
    landed = folder / archive.name
    shutil.move(str(archive), str(landed))
    if landed.suffix.lower() == ARCHIVE_SUFFIX:
        unpack(landed, folder)

    saved = len([path for path in folder.rglob("*") if path.is_file()])
    logger.info("      첨부 %d건", saved)
    return saved


def save_pdf(driver: WebDriver, folder: Path, number: str) -> Path:
    driver.switch_to.default_content()
    expand_page(driver)
    result = call_cdp(driver, "Page.printToPDF", PDF_PARAMS, timeout=PDF_TIMEOUT)
    encoded = result.get("data") or ""
    if not encoded:
        raise DocumentError("Page.printToPDF 가 빈 결과를 돌려주었습니다")

    path = folder / f"{number}.pdf"
    path.write_bytes(base64.b64decode(str(encoded)))
    if path.stat().st_size <= 0:
        raise DocumentError(f"저장된 PDF 크기가 0입니다: {path}")
    return path


def approve(driver: WebDriver) -> None:
    click_in_frames(driver, APPROVE_BUTTON, "결재 버튼", timeout=APPROVE_TIMEOUT)
    time.sleep(DIALOG_SETTLE)

    click_in_frames(
        driver,
        AUTHORIZE_RADIO,
        "결재 구분(AUTHORIZE)",
        by=By.CSS_SELECTOR,
        timeout=APPROVE_TIMEOUT,
    )
    time.sleep(CHOICE_SETTLE)

    click_in_frames(driver, CONFIRM_BUTTON, "결재 확인 버튼", timeout=APPROVE_TIMEOUT)
    time.sleep(APPROVE_SETTLE)
    logger.info("      결재했습니다")


def capture_one(driver: WebDriver, *, workspace: Path, downloads: Path) -> Captured | None:
    open_approval(driver)
    row = first_row(driver)
    if row is None:
        logger.info("      결재할 문서가 없습니다")
        return None

    main = driver.current_window_handle
    open_detail(driver, row)
    document = read_document(driver)
    logger.info("      %s / %s / %s", document.number, document.sender, document.title)

    folder = workspace / document.number
    folder.mkdir(parents=True, exist_ok=True)
    attachments = save_attachments(driver, folder, downloads)
    pdf = save_pdf(driver, folder, document.number)
    images = poppler.to_images(pdf)
    logger.info("      %s (이미지 %d장)", pdf.name, len(images))

    return Captured(
        approvals=main,
        document=document,
        folder=folder,
        attachments=attachments,
        pdf=pdf,
        images=images,
    )
