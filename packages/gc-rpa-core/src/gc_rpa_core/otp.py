from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from gc_rpa_core import config
from gc_rpa_core.browser import chrome, click, fill, wait_ready

LOGIN_ID_INPUT = "//input[@placeholder='로그인 ID']"
NEXT_BUTTON = "//button[.//span[text()='다음']]"
PASSWORD_INPUT = "//input[@placeholder='비밀번호']"
LOGIN_BUTTON = "//button[.//span[text()='로그인']]"

MAIL_MENU = "//p[normalize-space(text())='메일']"
MAIL_BODY_FRAME = "viewContentIframeId"

CHANGE_HOST = "login.office.hiworks.com"
CHANGE_PATH = "password-change"
CHANGE_INPUT = "//form//input[@type='password']"
CHANGE_SUBMIT = "//form//button"
SIGNED_IN_PATH = "/main"

FRAME_TIMEOUT = 20.0
ARRIVAL_TIMEOUT = 180.0
ARRIVAL_PAUSE = 5.0

DIGITS = re.compile(r"\d+")

logger = logging.getLogger(__name__)


class OtpError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    subject: str
    code: re.Pattern[str]

    @property
    def locator(self) -> str:
        return f"//span[normalize-space(text())='{self.subject}']"


VPN = Profile("HMG SSLVPN OTP", re.compile(r"OTP\s*:\s*\[\s*(\d+)\s*\]"))
PORTAL = Profile("[고객포탈]로그인 인증번호 안내", re.compile(r"인증번호는\s*(\d{6})\s*입니다"))


def bumped(password: str) -> str:
    found = DIGITS.search(password.strip())
    if not found:
        raise OtpError("비밀번호에 숫자가 없어 다음 비밀번호를 만들 수 없습니다")
    raised = str(int(found.group(0)) + 1).zfill(len(found.group(0)))
    return password.strip()[: found.start()] + raised + password.strip()[found.end() :]


def on_change_page(driver: WebDriver) -> bool:
    address = (driver.current_url or "").lower()
    return CHANGE_HOST in address and CHANGE_PATH in address


def signed_in_already(driver: WebDriver) -> bool:
    path = (urlparse(driver.current_url or "").path or "").rstrip("/").lower()
    return path.endswith(SIGNED_IN_PATH)


def sign_in(driver: WebDriver, settings: config.RpaConfig, password: str) -> None:
    driver.get(settings.url)
    wait_ready(driver)
    fill(driver, By.XPATH, LOGIN_ID_INPUT, settings.user_id)
    click(driver, By.XPATH, NEXT_BUTTON)
    fill(driver, By.XPATH, PASSWORD_INPUT, password)
    click(driver, By.XPATH, LOGIN_BUTTON)
    wait_ready(driver)


def change_password(driver: WebDriver, current: str, fresh: str) -> None:
    boxes = driver.find_elements(By.XPATH, CHANGE_INPUT)
    if len(boxes) < 3:
        raise OtpError(f"비밀번호 변경 화면에 입력란이 {len(boxes)}개뿐입니다")
    for box, value in zip(boxes[:3], (current, fresh, fresh), strict=True):
        box.clear()
        box.send_keys(value)
    click(driver, By.XPATH, CHANGE_SUBMIT)
    WebDriverWait(driver, FRAME_TIMEOUT).until(EC.alert_is_present())
    driver.switch_to.alert.accept()
    wait_ready(driver)


def renew_password(driver: WebDriver, settings: config.RpaConfig, schedule_id: str) -> str:
    fresh = bumped(settings.password)
    change_password(driver, settings.password, fresh)
    config.save_password(schedule_id, fresh)
    logger.info("      하이웍스 비밀번호를 바꾸고 설정에 반영했습니다")
    return fresh


@dataclass
class Mailbox:
    driver: WebDriver
    profile: Profile
    seen: int = 0

    def listed(self) -> int:
        self.driver.switch_to.default_content()
        click(self.driver, By.XPATH, MAIL_MENU)
        wait_ready(self.driver)
        return len(self.driver.find_elements(By.XPATH, self.profile.locator))

    def mark(self) -> None:
        self.seen = self.listed()

    def read(self, *, timeout: float = ARRIVAL_TIMEOUT) -> str:
        deadline = time.monotonic() + timeout
        while self.listed() <= self.seen:
            if time.monotonic() >= deadline:
                raise OtpError(f"OTP 메일이 {timeout:.0f}초 안에 오지 않았습니다")
            time.sleep(ARRIVAL_PAUSE)
        return self.newest()

    def newest(self) -> str:
        found = self.driver.find_elements(By.XPATH, self.profile.locator)
        if not found:
            raise OtpError(f"'{self.profile.subject}' 메일을 찾지 못했습니다")
        found[0].click()
        WebDriverWait(self.driver, FRAME_TIMEOUT).until(
            EC.frame_to_be_available_and_switch_to_it(MAIL_BODY_FRAME)
        )
        body = self.driver.find_element(By.TAG_NAME, "body").text
        self.driver.switch_to.default_content()

        code = self.profile.code.search(body)
        if not code:
            raise OtpError(f"'{self.profile.subject}' 본문에서 번호를 찾지 못했습니다")
        return code.group(1)


@contextmanager
def mailbox(schedule_id: str, profile: Profile, *, downloads: Path) -> Iterator[Mailbox]:
    settings = config.load(schedule_id)
    with chrome(settings.url, download_dir=downloads, headless=True) as driver:
        sign_in(driver, settings, settings.password)
        if on_change_page(driver):
            logger.info("      하이웍스가 비밀번호 변경을 요구합니다")
            fresh = renew_password(driver, settings, schedule_id)
            if not signed_in_already(driver):
                sign_in(driver, settings, fresh)
        yield Mailbox(driver=driver, profile=profile)
