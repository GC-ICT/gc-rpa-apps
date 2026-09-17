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
from gc_rpa_core.browser import (
    PARTIAL_SUFFIXES,
    RendererHangError,
    call_cdp,
    settled_files,
    wait_ready,
)

ATTACHMENT_CHECKBOX = "chk_all_box"
ATTACHMENT_SAVE = "button.l-file__button"
EXPORT_TOOLBAR = '//button[contains(@onclick,"MailList_btnMsgExport_OnClick")]'
EXPORT_TOOLBAR_FALLBACK = "button.m-toolbar__button"
EXPORT_SAVE = (
    '//button[contains(@onclick,"aMultiDownLoad_OnClick") and not(contains(@onclick,"MailView_"))]'
)
POPUP_OPEN = '//button[contains(@onclick,"MailView_btnPopup_OnClick")]'

POPUP_TIMEOUT = 20.0
POPUP_SETTLE = 0.5
BODY_TIMEOUT = 15.0
BODY_MIN_TEXT = 20
BODY_POLL = 0.5
EXPAND_SETTLE = 0.6

ATTACHMENT_TIMEOUT = 3.0
EXPORT_TIMEOUT = 10.0

DOWNLOAD_START_GRACE = 5.0
DOWNLOAD_TIMEOUT = 180.0

PDF_NAME = "document.pdf"
PDF_SETUP_TIMEOUT = 5.0
PDF_PRINT_TIMEOUT = 20.0
PDF_PARAMS = {
    "printBackground": True,
    "preferCSSPageSize": False,
    "marginTop": 0.0,
    "marginBottom": 0.0,
    "marginLeft": 0.0,
    "marginRight": 0.0,
    "scale": 1.0,
}
A4_WIDTH = 8.27
A4_HEIGHT = 11.69
PIXELS_PER_INCH = 96.0
PAGE_PADDING = 0.2
MAX_PAGE_INCHES = 200.0

EXPAND_PAGE = """
var loose = '::-webkit-scrollbar{display:none !important}'
  + 'html,body{overflow:visible !important;height:auto !important;max-height:none !important}';
function relax(doc) {
  var style = doc.createElement('style');
  style.textContent = loose;
  (doc.head || doc.documentElement).appendChild(style);
}
relax(document);
var frames = document.querySelectorAll('iframe, frame');
for (var i = 0; i < frames.length; i++) {
  try {
    var inner = frames[i].contentDocument;
    if (!inner || !inner.body) { continue; }
    relax(inner);
    var tall = Math.max(inner.body.scrollHeight, inner.documentElement.scrollHeight);
    var wide = Math.max(inner.body.scrollWidth, inner.documentElement.scrollWidth);
    frames[i].setAttribute('scrolling', 'no');
    frames[i].style.height = tall + 'px';
    frames[i].style.maxHeight = 'none';
    if (wide > frames[i].clientWidth) { frames[i].style.width = wide + 'px'; }
  } catch (e) {}
}
return frames.length;
"""

logger = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    pass


def downloading(downloads: Path) -> bool:
    return any(path.name.endswith(PARTIAL_SUFFIXES) for path in downloads.iterdir())


def wait_for_downloads(downloads: Path) -> None:
    grace = time.monotonic() + DOWNLOAD_START_GRACE
    while time.monotonic() < grace:
        if downloading(downloads) or settled_files(downloads):
            break
        time.sleep(0.2)

    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    while downloading(downloads):
        if time.monotonic() >= deadline:
            partial = [path.name for path in downloads.iterdir() if not path.is_dir()]
            logger.warning("      %g초 안에 내려받지 못했습니다: %s", DOWNLOAD_TIMEOUT, partial)
            return
        time.sleep(0.5)


def gather_downloads(downloads: Path, folder: Path) -> int:
    wait_for_downloads(downloads)
    moved = 0
    for path in sorted(settled_files(downloads)):
        shutil.move(str(path), str(folder / path.name))
        moved += 1
    return moved


def save_attachments(driver: WebDriver, folder: Path, downloads: Path) -> int:
    time.sleep(1.0)
    checkbox = inbox.find_within(
        driver, By.ID, ATTACHMENT_CHECKBOX, "첨부 전체선택", timeout=ATTACHMENT_TIMEOUT
    )
    if checkbox is None:
        logger.info("      첨부 없음")
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
    saved = gather_downloads(downloads, folder)
    logger.info("      첨부 %d건", saved)
    return saved


def press_export_toolbar(driver: WebDriver, *, attempts: int = 3) -> None:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            inbox.accept_dialog(driver, timeout=0)
            inbox.dismiss_layer(driver)
            button = inbox.find_within(
                driver, By.XPATH, EXPORT_TOOLBAR, "EML 저장 버튼", timeout=EXPORT_TIMEOUT
            )
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

    save = inbox.find_within(
        driver, By.XPATH, EXPORT_SAVE, "EML 내려받기 버튼", timeout=EXPORT_TIMEOUT
    )
    if save is None:
        logger.warning("      EML 내려받기 버튼을 찾지 못해 원본을 남기지 못합니다")
        inbox.enter_mail_frame(driver)
        inbox.close_export_popup(driver)
        return gather_downloads(downloads, folder)

    inbox.press(driver, save)
    time.sleep(1.0)
    inbox.accept_dialog(driver, timeout=1.0)
    inbox.enter_mail_frame(driver)
    time.sleep(0.4)
    inbox.close_export_popup(driver)
    saved = gather_downloads(downloads, folder)
    if not saved:
        logger.warning("      EML 이 내려오지 않았습니다")
    else:
        logger.info("      EML %d건", saved)
    return saved


BODY_LENGTH_SCRIPT = """
var total = document.body ? document.body.innerText.trim().length : 0;
var frames = document.querySelectorAll('iframe, frame');
for (var i = 0; i < frames.length; i++) {
  try {
    var inner = frames[i].contentDocument;
    if (inner && inner.body) { total += inner.body.innerText.trim().length; }
  } catch (e) {}
}
return total;
"""


def body_text_length(driver: WebDriver) -> int:
    return int(driver.execute_script(BODY_LENGTH_SCRIPT) or 0)


def wait_for_body(driver: WebDriver, *, timeout: float = BODY_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    settled = -1
    while time.monotonic() < deadline:
        length = body_text_length(driver)
        if length >= BODY_MIN_TEXT and length == settled:
            return
        settled = length
        time.sleep(BODY_POLL)
    logger.warning("      본문이 %g초 안에 자리잡지 않았습니다 (%d자)", timeout, settled)


def focus_popup(driver: WebDriver, before: set[str], *, timeout: float = POPUP_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        opened = [handle for handle in driver.window_handles if handle not in before]
        if opened:
            driver.switch_to.window(opened[-1])
            wait_ready(driver, timeout=timeout)
            wait_for_body(driver)
            time.sleep(POPUP_SETTLE)
            return
        time.sleep(0.2)
    raise CaptureError(f"본문 팝업 창이 {timeout:g}초 안에 열리지 않았습니다")


def content_inches(driver: WebDriver) -> tuple[float, float]:
    metrics = call_cdp(driver, "Page.getLayoutMetrics", {}, timeout=PDF_SETUP_TIMEOUT)
    content = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
    width = float(content.get("width") or 0) / PIXELS_PER_INCH
    height = float(content.get("height") or 0) / PIXELS_PER_INCH
    if not width or not height:
        return A4_WIDTH, A4_HEIGHT
    if height > MAX_PAGE_INCHES:
        logger.warning("      본문이 길어 %g인치까지만 담습니다", MAX_PAGE_INCHES)
        height = MAX_PAGE_INCHES
    return width + PAGE_PADDING, height + PAGE_PADDING


def whole_page(driver: WebDriver) -> dict[str, object]:
    width, height = content_inches(driver)
    return {**PDF_PARAMS, "paperWidth": width, "paperHeight": height, "landscape": False}


def write_pdf(driver: WebDriver, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PDF_NAME

    try:
        frames = driver.execute_script(EXPAND_PAGE)
        logger.debug("      본문 프레임 %s개를 펼쳤습니다", frames)
        time.sleep(EXPAND_SETTLE)
    except Exception:
        logger.debug("      본문 펼치기를 건너뜁니다")

    try:
        call_cdp(
            driver, "Emulation.setEmulatedMedia", {"media": "screen"}, timeout=PDF_SETUP_TIMEOUT
        )
    except RendererHangError:
        raise
    except Exception:
        logger.debug("      화면 CSS 적용을 건너뜁니다")

    result = call_cdp(driver, "Page.printToPDF", whole_page(driver), timeout=PDF_PRINT_TIMEOUT)
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

    opener = inbox.find_within(
        driver, By.XPATH, POPUP_OPEN, "본문 팝업 버튼", timeout=EXPORT_TIMEOUT
    )
    if opener is None:
        raise CaptureError("본문 팝업 버튼을 찾지 못했습니다")

    before = set(driver.window_handles)
    inbox.press(driver, opener)

    try:
        focus_popup(driver, before)
        inbox.dismiss_layer(driver, settle=1.0)
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
