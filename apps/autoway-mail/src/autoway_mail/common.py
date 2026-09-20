from __future__ import annotations

from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from gc_rpa_core import config
from gc_rpa_core.browser import accept_alert, click, fill, resolve_dir, wait_ready
from gc_rpa_core.env import optional_env

SCHEDULE_ID_ENV = "AUTOWAY_MAIL_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "5"

DOWNLOAD_SUBDIR = "download"
HISTORY_FILE = "history.db"

POPPLER_ENV = "POPPLER_PATH"
POPPLER_BINARY = "pdftoppm"
HEADLESS_ENV = "AUTOWAY_MAIL_HEADLESS"
TRUE_FLAGS = ("Y", "1", "T", "TRUE")

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


class WorkspaceError(RuntimeError):
    pass


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def load() -> config.RpaConfig:
    return config.load(schedule_id())


def erp_database(settings: config.RpaConfig) -> config.RpaDatabase:
    databases = config.load_databases(settings.actprg_id)
    filled = next((database for database in databases if not database.complaint), None)
    if filled is None:
        raise LookupError(
            f"{config.PROCEDURE} 의 actprg_id={settings.actprg_id} 에 "
            f"쓸 수 있는 DB 가 없습니다: {databases[0].complaint}"
        )
    return filled


def workspace(settings: config.RpaConfig) -> Path:
    if not settings.move_path.strip():
        raise WorkspaceError(
            f"{config.PROCEDURE} 의 file_move_path 가 비어 있어 작업 폴더를 정할 수 없습니다"
        )
    return resolve_dir(settings.move_path)


def download_dir(settings: config.RpaConfig) -> Path:
    return resolve_dir(str(workspace(settings) / DOWNLOAD_SUBDIR))


def history_path(settings: config.RpaConfig) -> Path:
    return workspace(settings) / HISTORY_FILE


def poppler_path() -> str:
    return optional_env(POPPLER_ENV)


def poppler_complaint() -> str:
    configured = poppler_path()
    if not configured:
        return ""
    folder = Path(configured)
    if not folder.is_dir():
        return f"{POPPLER_ENV} 폴더가 없습니다: {folder}"
    if any(folder.glob(f"{POPPLER_BINARY}*")):
        return ""
    found = next(iter(folder.rglob(f"{POPPLER_BINARY}*")), None)
    if found is not None:
        return f"{POPPLER_ENV} 를 {found.parent} 로 고쳐야 합니다 (지금은 {folder})"
    return f"{POPPLER_ENV} 폴더에 {POPPLER_BINARY} 가 없습니다: {folder}"


def headless() -> bool:
    return optional_env(HEADLESS_ENV, "1").strip().upper() in TRUE_FLAGS


def size_text(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1024:,.0f} KB" if size >= 1024 else f"{size} B"


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
