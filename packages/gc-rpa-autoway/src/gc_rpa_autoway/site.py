from __future__ import annotations

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from gc_rpa_core import config
from gc_rpa_core.browser import accept_alert, click, fill, wait_ready

USER_ID_INPUT = ":r1:"
PASSWORD_INPUT = ":r2:"
LOGIN_BUTTON = '//button[@type="submit" and contains(text(),"로그인")]'

NOTICE_CLOSE = "a[onclick*=\"fnCloseLayeredPopupWithID('Layer_Notice')\"]"
DIALOG_CLOSE = (
    '//button[contains(@class,"btn_dialog_close")]',
    '//button[contains(@class,"btn_close") and @aria-label="닫기"]',
)


class LoginError(RuntimeError):
    pass


def close_if_shown(driver: WebDriver, by: str, locator: str) -> None:
    for element in driver.find_elements(by, locator):
        try:
            if not element.is_displayed():
                continue
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)


def login(driver: WebDriver, settings: config.RpaConfig) -> None:
    driver.get(settings.url)
    wait_ready(driver)
    close_if_shown(driver, By.CSS_SELECTOR, NOTICE_CLOSE)

    try:
        fill(driver, By.ID, USER_ID_INPUT, settings.user_id)
        fill(driver, By.ID, PASSWORD_INPUT, settings.password)
        click(driver, By.XPATH, LOGIN_BUTTON)
    except TimeoutException as exc:
        raise LoginError("로그인 화면 요소를 찾지 못했습니다") from exc

    accept_alert(driver)
    for locator in DIALOG_CLOSE:
        close_if_shown(driver, By.XPATH, locator)
