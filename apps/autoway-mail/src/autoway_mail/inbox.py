from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

from gc_rpa_core.browser import session_dead

MAIL_MODULE_LINK = "a[href*='autowaymail']"
MAIL_FRAMES = ("ifrSubSys", "subsysFrame")
ROW_NAME = "divItem"
ROW_CHECKBOX = "input[name='chkMailListSelect']"
SENDER_NAME = ".m-list__sender-link-name"
READ_SENDER = ".m-read__from-name"
READ_DATE = ".m-read__date"
READ_TITLE = ".m-read__title"
ALERT_OVERLAY = "alert_overlay"
EXPORT_POPUP_CLOSE = "divMsgExportPop_px"
ERP_FOLDER = "ERP 접수함"
SECURITY_NOTIFY_TYPE = "SECURITYMAIL"
ADDRESS_IN_NAME = re.compile(r"<[^<>]*@[^<>]*>")

LIST_ATTRIBUTES = {
    "message_id": "messageid",
    "mid": "mid",
    "subject": "subject",
    "sender_mail": "sendermail",
    "received_at": "receivedate",
    "notify_type": "notifytype",
    "secure_id": "securitymailid",
}

TOOLBAR_BUTTON = "//button[contains(@onclick,{action!r})]"
MOVE_ACTION = "MailList_btnMove_OnClick"
MOVE_EXPAND_ACTION = "MailList_btnMoveCopySubLayerExpend_OnClick"
MOVE_APPLY_ACTION = "MailList_btnMoveAction_OnClick"
MOVE_TARGET = (
    '//a[contains(@onclick,"MailList_MoveLayerItem_OnClick") and contains(text(),"{folder}")]'
)

CONFIRM_BUTTONS = (
    '//*[contains(@id,"alert") or contains(@class,"alert")]//button[normalize-space(.)="확인"]',
    '//*[contains(@id,"alert") or contains(@class,"alert")]//a[normalize-space(.)="확인"]',
    '//*[contains(@id,"alert") or contains(@class,"alert")]//button[normalize-space(.)="닫기"]',
)

LAYER_SETTLE_SECONDS = 4.0
SCROLL_SETTLE_SECONDS = 8.0
SCROLL_LIMIT = 20
LIST_ATTEMPTS = 5
LIST_RETRY_PAUSE = 2.0
READ_PANE_TIMEOUT = 20.0
READ_SENDER_TIMEOUT = 8.0
READ_SENDER_POLL = 0.3
MODULE_TIMEOUT = 40.0

logger = logging.getLogger(__name__)


class InboxError(RuntimeError):
    pass


@dataclass
class Listing:
    element: WebElement
    message_id: str = ""
    mid: str = ""
    subject: str = ""
    sender_mail: str = ""
    sender_name: str = ""
    received_at: str = ""
    notify_type: str = ""
    secure_id: str = ""

    @property
    def key(self) -> str:
        return self.message_id.strip() or self.mid.strip()

    @property
    def sender(self) -> str:
        return self.sender_name or self.sender_mail

    @property
    def label(self) -> str:
        return f"[{self.sender}] {self.subject}"

    @property
    def secured(self) -> bool:
        if self.notify_type.strip().upper() == SECURITY_NOTIFY_TYPE:
            return True
        return bool(self.secure_id.strip())


@dataclass
class FrameSearch:
    element: WebElement | None
    searched: dict[str, int] = field(default_factory=dict)

    def describe(self) -> str:
        return ", ".join(f"{kind} {count}개" for kind, count in self.searched.items())


def display_name(value: str) -> str:
    text = ADDRESS_IN_NAME.sub("", value or "").strip().strip('"').strip()
    return "" if "@" in text else text


def clean_text(value: str) -> str:
    return re.sub(r"[^가-힣0-9a-zA-Z\s]", "", value or "").strip()


def clean_digits(value: str) -> str:
    return re.sub(r"[^0-9]", "", value or "")


def safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", value).strip()[:60]


def enter_mail_frame(driver: WebDriver) -> None:
    driver.switch_to.default_content()
    for name in MAIL_FRAMES:
        try:
            driver.switch_to.frame(name)
            return
        except Exception:
            driver.switch_to.default_content()
    raise InboxError(f"메일 프레임을 찾지 못했습니다: {', '.join(MAIL_FRAMES)}")


def here_or_none(driver: WebDriver, by: str, locator: str) -> WebElement | None:
    try:
        return driver.find_element(by, locator)
    except NoSuchElementException:
        return None


def find_anywhere(driver: WebDriver, by: str, locator: str, what: str) -> FrameSearch:
    found = here_or_none(driver, by, locator)
    if found is not None:
        return FrameSearch(found)

    searched: dict[str, int] = {}
    for kind in ("iframe", "frame"):
        containers = driver.find_elements(By.TAG_NAME, kind)
        searched[kind] = len(containers)
        for index, container in enumerate(containers):
            try:
                driver.switch_to.frame(container)
                element = driver.find_element(by, locator)
            except Exception:
                enter_mail_frame(driver)
                continue
            logger.debug("      %s 를 %s %d번에서 찾았습니다", what, kind, index)
            return FrameSearch(element, searched)

    enter_mail_frame(driver)
    return FrameSearch(None, searched)


def find_within(
    driver: WebDriver, by: str, locator: str, what: str, *, timeout: float
) -> WebElement | None:
    deadline = time.monotonic() + timeout
    while True:
        found = find_anywhere(driver, by, locator, what).element
        if found is not None or time.monotonic() >= deadline:
            return found
        time.sleep(0.3)


def require_anywhere(driver: WebDriver, by: str, locator: str, what: str) -> WebElement:
    search = find_anywhere(driver, by, locator, what)
    if search.element is None:
        raise InboxError(f"{what} 를 찾지 못했습니다 ({locator} / {search.describe()} 탐색)")
    return search.element


def press(driver: WebDriver, element: WebElement) -> None:
    try:
        element.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        driver.execute_script("arguments[0].click();", element)


def press_toolbar(driver: WebDriver, action: str, what: str) -> None:
    press(driver, require_anywhere(driver, By.XPATH, TOOLBAR_BUTTON.format(action=action), what))


def visible_overlay(driver: WebDriver) -> WebElement | None:
    for element in driver.find_elements(By.ID, ALERT_OVERLAY):
        try:
            if element.is_displayed():
                return element
        except StaleElementReferenceException:
            continue
    return None


def dismiss_layer(driver: WebDriver, *, settle: float = LAYER_SETTLE_SECONDS) -> bool:
    if visible_overlay(driver) is None:
        return False

    deadline = time.monotonic() + settle
    while time.monotonic() < deadline:
        if visible_overlay(driver) is None:
            return True
        time.sleep(0.3)

    for locator in CONFIRM_BUTTONS:
        for button in driver.find_elements(By.XPATH, locator):
            try:
                if not button.is_displayed():
                    continue
                driver.execute_script("arguments[0].click();", button)
            except Exception:
                continue
            time.sleep(0.5)
            if visible_overlay(driver) is None:
                return True

    driver.execute_script(
        f"document.querySelectorAll('#{ALERT_OVERLAY}')"
        ".forEach(function(el){ el.style.display='none'; });"
    )
    logger.warning("      알림 레이어를 닫지 못해 가렸습니다")
    return True


def accept_dialog(driver: WebDriver, *, timeout: float = 1.5) -> str | None:
    try:
        WebDriverWait(driver, timeout).until(ec.alert_is_present())
    except TimeoutException:
        return None

    alert = driver.switch_to.alert
    text = " ".join((alert.text or "").split())
    alert.accept()
    time.sleep(0.4)
    return text


def close_export_popup(driver: WebDriver) -> bool:
    button = here_or_none(driver, By.ID, EXPORT_POPUP_CLOSE)
    if button is None:
        return False
    press(driver, button)
    time.sleep(0.5)
    return True


def waited_for(driver: WebDriver, by: str, locator: str, *, timeout: float) -> bool:
    try:
        WebDriverWait(driver, timeout).until(ec.presence_of_element_located((by, locator)))
        return True
    except TimeoutException:
        return False


def open_module(driver: WebDriver) -> None:
    driver.find_element(By.CSS_SELECTOR, MAIL_MODULE_LINK).click()
    enter_mail_frame(driver)
    if not waited_for(driver, By.NAME, ROW_NAME, timeout=MODULE_TIMEOUT):
        logger.warning("      받은편지함 목록이 %g초 안에 그려지지 않았습니다", MODULE_TIMEOUT)


def read_listing(element: WebElement) -> Listing:
    listing = Listing(element=element)
    try:
        checkbox = element.find_element(By.CSS_SELECTOR, ROW_CHECKBOX)
    except NoSuchElementException:
        return listing

    for name, attribute in LIST_ATTRIBUTES.items():
        setattr(listing, name, checkbox.get_attribute(attribute) or "")
    try:
        listing.sender_name = display_name(element.find_element(By.CSS_SELECTOR, SENDER_NAME).text)
    except NoSuchElementException:
        listing.sender_name = ""
    return listing


def pane_text(driver: WebDriver, locator: str, what: str) -> str:
    found = here_or_none(driver, By.CSS_SELECTOR, locator)
    if found is None:
        raise InboxError(f"읽기창에서 {what} 를 찾지 못했습니다 ({locator})")
    return found.text


def pane_sender(driver: WebDriver, *, timeout: float | None = None) -> str:
    deadline = time.monotonic() + (READ_SENDER_TIMEOUT if timeout is None else timeout)
    while True:
        shown = here_or_none(driver, By.CSS_SELECTOR, READ_SENDER)
        text = shown.text.strip() if shown is not None else ""
        if text or time.monotonic() >= deadline:
            return display_name(text)
        time.sleep(READ_SENDER_POLL)


def fill_missing(driver: WebDriver, listing: Listing) -> bool:
    filled = False
    if not listing.subject:
        listing.subject = pane_text(driver, READ_TITLE, "제목")
        filled = True
    if not listing.received_at:
        listing.received_at = pane_text(driver, READ_DATE, "수신일시")
        filled = True

    if not listing.sender_name:
        listing.sender_name = pane_sender(driver)
        filled = filled or bool(listing.sender_name)
    return filled


def read_listings(driver: WebDriver) -> list[Listing]:
    return [read_listing(element) for element in driver.find_elements(By.NAME, ROW_NAME)]


def load_more(driver: WebDriver, seen: int) -> int:
    rows = driver.find_elements(By.NAME, ROW_NAME)
    if not rows:
        return 0
    driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", rows[-1])

    deadline = time.monotonic() + SCROLL_SETTLE_SECONDS
    while time.monotonic() < deadline:
        time.sleep(0.5)
        grown = len(driver.find_elements(By.NAME, ROW_NAME))
        if grown > seen:
            logger.info("      목록을 더 불러왔습니다: %d건 → %d건", seen, grown)
            return grown
    return seen


def look_up_listing(driver: WebDriver, position: int) -> Listing | None:
    accept_dialog(driver, timeout=0)
    enter_mail_frame(driver)
    try:
        WebDriverWait(driver, 10).until(ec.presence_of_all_elements_located((By.NAME, ROW_NAME)))
    except TimeoutException:
        return None

    listings = read_listings(driver)
    for _ in range(SCROLL_LIMIT):
        if position < len(listings):
            return listings[position]
        before = len(listings)
        if load_more(driver, before) <= before:
            return None
        listings = read_listings(driver)

    logger.warning("      목록 추가 로드 상한(%d회)에 닿았습니다", SCROLL_LIMIT)
    return None


def listing_at(
    driver: WebDriver, position: int, *, attempts: int = LIST_ATTEMPTS
) -> Listing | None:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return look_up_listing(driver, position)
        except StaleElementReferenceException as exc:
            last = exc
            logger.warning("      목록이 갱신 중이라 다시 읽습니다 %d/%d", attempt, attempts)
        except Exception as exc:
            if session_dead(exc):
                raise
            last = exc
            logger.warning("      목록 조회 실패 → 재시도 %d/%d: %s", attempt, attempts, exc)
        time.sleep(LIST_RETRY_PAUSE)

    raise InboxError(f"목록 {position}번 행을 {attempts}회 읽었으나 실패했습니다: {last}")


def open_listing(driver: WebDriver, listing: Listing) -> None:
    press(driver, listing.element)
    if not waited_for(driver, By.CSS_SELECTOR, READ_TITLE, timeout=READ_PANE_TIMEOUT):
        logger.warning("      읽기창이 %g초 안에 그려지지 않았습니다", READ_PANE_TIMEOUT)


def move_selected(driver: WebDriver, folder: str = ERP_FOLDER) -> None:
    dismiss_layer(driver, settle=2.0)
    press_toolbar(driver, MOVE_ACTION, "이동 버튼")
    time.sleep(0.6)
    press_toolbar(driver, MOVE_EXPAND_ACTION, "폴더 목록 펼치기")
    time.sleep(0.6)
    press(driver, require_anywhere(driver, By.XPATH, MOVE_TARGET.format(folder=folder), folder))
    time.sleep(0.6)
    press_toolbar(driver, MOVE_APPLY_ACTION, "이동 실행 버튼")
    time.sleep(0.8)


def retry_move(driver: WebDriver, *, attempts: int = 3, folder: str = ERP_FOLDER) -> None:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            move_selected(driver, folder)
            return
        except Exception as exc:
            if session_dead(exc):
                raise
            last = exc
            logger.warning("      접수함 이동 실패 → 재시도 %d/%d: %s", attempt, attempts, exc)
            settle(driver)
    raise InboxError(f"접수함 이동을 {attempts}회 시도했으나 실패했습니다: {last}")


def settle(driver: WebDriver) -> None:
    for step in (
        lambda: accept_dialog(driver, timeout=0),
        lambda: enter_mail_frame(driver),
        lambda: close_export_popup(driver),
        lambda: dismiss_layer(driver, settle=1.0),
    ):
        try:
            step()
        except Exception:
            continue
