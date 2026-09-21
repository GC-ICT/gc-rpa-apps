from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from gc_rpa_core import config, otp
from gc_rpa_core.browser import chrome, click, click_if_shown, fill, wait_ready

PROCESS = "f5vpn.exe"

SESSION_LINK = "//a[contains(text(), '여기를 클릭해주세요')]"
ID_INPUT = "txt_id"
PASSWORD_INPUT = "txt_pass"
SUBMIT_BUTTON = "btn-login"
INSPECT_BUTTON = "cphDownloadBtnDiv"
PROCEED_LINK = "//a[contains(text(), 'Proceed')]"

NATIVE_DIALOG_KEYS = ("tab", "tab", "enter")
DIALOG_WAIT = 3.0
KEY_PAUSE = 0.5
LAUNCH_WAIT = 10.0
CONNECT_WAIT = 30.0

logger = logging.getLogger(__name__)


class VpnError(RuntimeError):
    pass


def running() -> bool:
    try:
        listed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {PROCESS}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise VpnError(f"{PROCESS} 상태를 확인하지 못했습니다: {exc}") from exc
    return PROCESS in listed.stdout


def allow_native_app() -> None:
    import pyautogui

    pyautogui.FAILSAFE = False
    time.sleep(DIALOG_WAIT)
    for key in NATIVE_DIALOG_KEYS:
        pyautogui.press(key)
        time.sleep(KEY_PAUSE)
    time.sleep(LAUNCH_WAIT)


def dismiss_extra_windows(driver: WebDriver) -> None:
    kept = driver.current_window_handle
    for handle in driver.window_handles:
        if handle != kept:
            driver.switch_to.window(handle)
            driver.close()
    driver.switch_to.window(kept)


def sign_in(driver: WebDriver, settings: config.RpaConfig) -> None:
    driver.get(settings.url)
    wait_ready(driver)
    if click_if_shown(driver, By.XPATH, SESSION_LINK):
        wait_ready(driver)

    fill(driver, By.ID, ID_INPUT, settings.user_id)
    fill(driver, By.ID, PASSWORD_INPUT, settings.password)
    click(driver, By.CLASS_NAME, SUBMIT_BUTTON)
    wait_ready(driver)
    dismiss_extra_windows(driver)


def submit_code(driver: WebDriver, code: str) -> None:
    fill(driver, By.ID, PASSWORD_INPUT, code)
    click(driver, By.CLASS_NAME, SUBMIT_BUTTON)
    wait_ready(driver)


def run_inspector(driver: WebDriver) -> None:
    click(driver, By.CLASS_NAME, INSPECT_BUTTON)
    allow_native_app()
    click(driver, By.XPATH, PROCEED_LINK)
    click(driver, By.CLASS_NAME, INSPECT_BUTTON)
    allow_native_app()


def launch_client(driver: WebDriver) -> None:
    click(driver, By.CLASS_NAME, SUBMIT_BUTTON)
    click(driver, By.CLASS_NAME, INSPECT_BUTTON)
    allow_native_app()
    time.sleep(CONNECT_WAIT)


def connect(*, portal_schedule_id: str, otp_schedule_id: str, downloads: Path) -> None:
    if running():
        logger.info("      %s 가 이미 떠 있어 접속을 건너뜁니다", PROCESS)
        return

    settings = config.load(portal_schedule_id)
    with (
        otp.mailbox(otp_schedule_id, otp.VPN, downloads=downloads) as box,
        chrome(settings.url, download_dir=downloads) as driver,
    ):
        box.mark()
        sign_in(driver, settings)
        code = box.read()
        logger.info("      OTP 를 받았습니다")
        submit_code(driver, code)
        run_inspector(driver)
        launch_client(driver)

    if not running():
        raise VpnError(f"{PROCESS} 가 뜨지 않아 VPN 에 붙지 못했습니다")
    logger.info("      VPN 에 붙었습니다")
