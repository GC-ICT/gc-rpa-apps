from __future__ import annotations

from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from gc_rpa_core import RpaConfig
from gc_rpa_core.browser import accept_alert, click, fill, resolve_dir
from gc_rpa_core.env import bundle_dir, optional_env

DOWNLOAD_DIR_ENV = "MOBIS_AS_DOWNLOAD_DIR"
DEFAULT_DOWNLOAD_DIR = "downloads"

LOGIN_BOX = "mainframe.VFrameSet.LoginFrame.form.divLogin.form.divLoginBox.form"
USER_ID_INPUT = f"{LOGIN_BOX}.edtUsrId:input"
PASSWORD_INPUT = f"{LOGIN_BOX}.edtPwd:input"
OTP_INPUT = f"{LOGIN_BOX}.edtOtpKey:input"
LOGIN_BUTTON = f"{LOGIN_BOX}.btnOtpLogin"


class LoginError(RuntimeError):
    pass


def download_dir() -> Path:
    configured = optional_env(DOWNLOAD_DIR_ENV)
    if configured:
        return resolve_dir(configured)
    return resolve_dir(str(bundle_dir() / DEFAULT_DOWNLOAD_DIR))


def login(driver: WebDriver, config: RpaConfig) -> None:
    try:
        fill(driver, By.ID, USER_ID_INPUT, config.user_id)
        fill(driver, By.ID, PASSWORD_INPUT, config.password)
        if config.use_otp:
            fill(driver, By.ID, OTP_INPUT, config.otp)
        click(driver, By.ID, LOGIN_BUTTON)
    except TimeoutException as exc:
        raise LoginError("로그인 화면 요소를 찾지 못했다") from exc

    accept_alert(driver)
