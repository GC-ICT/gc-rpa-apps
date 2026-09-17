from __future__ import annotations

import base64
import logging
import shutil
import time
from pathlib import Path

from pdf2image import convert_from_path
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from autoway_mail import inbox
from gc_rpa_core.browser import RendererHangError, call_cdp

ATTACHMENT_CHECKBOX = "chk_all_box"
ATTACHMENT_SAVE = "button.l-file__button"
EXPORT_TOOLBAR = '//button[contains(@onclick,"MailList_btnMsgExport_OnClick")]'
EXPORT_TOOLBAR_FALLBACK = "button.m-toolbar__button"
EXPORT_SAVE = '//button[contains(@onclick,"aMultiDownLoad_OnClick")]'
POPUP_OPEN = '//button[contains(@onclick,"MailView_btnPopup_OnClick")]'

PDF_NAME = "document.pdf"
PDF_SETUP_TIMEOUT = 5.0
PDF_PRINT_TIMEOUT = 20.0
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

logger = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    pass


def gather_downloads(downloads: Path, folder: Path) -> int:
    moved = 0
    for path in sorted(downloads.iterdir()):
        if path.is_file():
            shutil.move(str(path), str(folder / path.name))
            moved += 1
    return moved


def save_attachments(driver: WebDriver, folder: Path, downloads: Path) -> int:
    time.sleep(1.0)
    checkbox = inbox.find_anywhere(driver, By.ID, ATTACHMENT_CHECKBOX, "첨부 전체선택").element
    if checkbox is None:
        inbox.enter_mail_frame(driver)
        return 0

    inbox.press(driver, checkbox)
    time.sleep(0.5)

    button = inbox.here_or_none(driver, By.CSS_SELECTOR, ATTACHMENT_SAVE)
    if button is None:
        inbox.enter_mail_frame(driver)
        button = inbox.here_or_none(driver, By.CSS_SELECTOR, ATTACHMENT_SAVE)
    if button is None:
        inbox.enter_mail_frame(driver)
        raise CaptureError("첨부 저장 버튼을 찾지 못했습니다")

    inbox.press(driver, button)
    time.sleep(0.8)
    inbox.accept_dialog(driver, timeout=1.0)
    inbox.enter_mail_frame(driver)
    inbox.dismiss_layer(driver)
    return gather_downloads(downloads, folder)


def press_export_toolbar(driver: WebDriver, *, attempts: int = 3) -> None:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            inbox.accept_dialog(driver, timeout=0)
            inbox.dismiss_layer(driver)
            button = inbox.find_anywhere(driver, By.XPATH, EXPORT_TOOLBAR, "EML 저장 버튼").element
            if button is None:
                button = inbox.require_anywhere(
                    driver, By.CSS_SELECTOR, EXPORT_TOOLBAR_FALLBACK, "EML 저장 버튼"
                )
            inbox.press(driver, button)
            return
        except Exception as exc:
            last = exc
            logger.warning("      EML 저장 버튼 클릭 실패 → 재시도 %d/%d", attempt, attempts)
            time.sleep(1.0)
            inbox.enter_mail_frame(driver)
    raise CaptureError(f"EML 저장 버튼을 {attempts}회 눌렀으나 실패했습니다: {last}")


def save_eml(driver: WebDriver, folder: Path, downloads: Path) -> int:
    time.sleep(0.6)
    inbox.enter_mail_frame(driver)
    time.sleep(0.4)

    press_export_toolbar(driver)
    time.sleep(0.8)
    inbox.accept_dialog(driver, timeout=1.5)
    time.sleep(0.4)

    save = inbox.find_anywhere(driver, By.XPATH, EXPORT_SAVE, "EML 내려받기 버튼").element
    if save is None:
        inbox.enter_mail_frame(driver)
        inbox.close_export_popup(driver)
        raise CaptureError("EML 내려받기 버튼을 찾지 못했습니다")

    inbox.press(driver, save)
    time.sleep(1.0)
    inbox.accept_dialog(driver, timeout=1.0)
    inbox.enter_mail_frame(driver)
    time.sleep(0.4)
    inbox.close_export_popup(driver)
    return gather_downloads(downloads, folder)


def focus_popup(driver: WebDriver, main: str) -> None:
    opened = [handle for handle in driver.window_handles if handle != main]
    if not opened:
        raise CaptureError("본문 팝업 창이 열리지 않았습니다")
    driver.switch_to.window(opened[-1])
    time.sleep(2.0)


def write_pdf(driver: WebDriver, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PDF_NAME

    try:
        call_cdp(
            driver, "Emulation.setEmulatedMedia", {"media": "print"}, timeout=PDF_SETUP_TIMEOUT
        )
    except RendererHangError:
        raise
    except Exception:
        logger.debug("      인쇄 CSS 적용을 건너뜁니다")

    result = call_cdp(driver, "Page.printToPDF", PDF_PARAMS, timeout=PDF_PRINT_TIMEOUT)
    encoded = result.get("data") or ""
    if not encoded:
        raise CaptureError("Page.printToPDF 가 빈 결과를 돌려주었습니다")

    path.write_bytes(base64.b64decode(encoded))
    if path.stat().st_size <= 0:
        raise CaptureError(f"저장된 PDF 크기가 0입니다: {path}")
    return path


def save_body_pdf(driver: WebDriver, folder: Path) -> Path:
    main = driver.current_window_handle
    time.sleep(0.6)
    inbox.enter_mail_frame(driver)
    time.sleep(0.4)

    opener = inbox.require_anywhere(driver, By.XPATH, POPUP_OPEN, "본문 팝업 버튼")
    inbox.press(driver, opener)
    time.sleep(3.0)

    try:
        focus_popup(driver, main)
        path = write_pdf(driver, folder)
    except RendererHangError:
        raise
    except Exception:
        inbox.windows_closed_to(driver, main)
        inbox.enter_mail_frame(driver)
        raise

    inbox.windows_closed_to(driver, main)
    inbox.enter_mail_frame(driver)
    return path


def save_page_images(pdf: Path, poppler: str) -> list[Path]:
    written: list[Path] = []
    try:
        pages = (
            convert_from_path(str(pdf), poppler_path=poppler)
            if poppler
            else convert_from_path(str(pdf))
        )
    except Exception as exc:
        logger.warning("      본문 이미지 변환을 건너뜁니다: %s", exc)
        return written

    for number, page in enumerate(pages, start=1):
        image = pdf.with_name(f"{pdf.stem}_{number}.jpg")
        page.save(image, "JPEG")
        written.append(image)
    return written
