from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

WINDOW_SIZE = (1920, 1080)
PAGE_TIMEOUT = 300
ELEMENT_TIMEOUT = 60
ALERT_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 300
PARTIAL_SUFFIXES = (".crdownload", ".tmp", ".part")
SLOW_START_SECONDS = 3.0

MANAGER_LOGGER = "selenium.webdriver.common.selenium_manager"
MANAGER_KEYWORDS = (
    "not found in PATH",
    "detected at",
    "Detected browser",
    "Required driver",
    "Downloading",
    "Driver path",
    "Unable to discover",
)

logger = logging.getLogger(__name__)


class DriverProgressFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return any(keyword in record.getMessage() for keyword in MANAGER_KEYWORDS)


def show_driver_progress() -> None:
    manager = logging.getLogger(MANAGER_LOGGER)
    manager.setLevel(logging.DEBUG)
    if not any(isinstance(f, DriverProgressFilter) for f in manager.filters):
        manager.addFilter(DriverProgressFilter())


class DownloadError(RuntimeError):
    pass


def resolve_dir(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def chrome(url: str, *, download_dir: Path, headless: bool = False) -> Iterator[WebDriver]:
    options = Options()
    options.add_argument("--allow-running-insecure-content")
    options.add_argument(f"--unsafely-treat-insecure-origin-as-secure={url}")
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size={},{}".format(*WINDOW_SIZE))
    options.accept_insecure_certs = True
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )

    show_driver_progress()
    started = time.monotonic()
    driver = webdriver.Chrome(options=options)
    elapsed = time.monotonic() - started
    if elapsed >= SLOW_START_SECONDS:
        logger.info("      드라이버 준비를 마쳤습니다 (%.1f초)", elapsed)

    driver.set_page_load_timeout(PAGE_TIMEOUT)
    driver.set_script_timeout(PAGE_TIMEOUT)
    try:
        driver.set_window_size(*WINDOW_SIZE)
        yield driver
    finally:
        driver.quit()


def wait_ready(driver: WebDriver, *, timeout: float = PAGE_TIMEOUT) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def click(
    driver: WebDriver, by: str, locator: str, *, timeout: float = ELEMENT_TIMEOUT
) -> WebElement:
    element = WebDriverWait(driver, timeout).until(ec.element_to_be_clickable((by, locator)))
    element.click()
    return element


def fill(
    driver: WebDriver, by: str, locator: str, value: str, *, timeout: float = ELEMENT_TIMEOUT
) -> WebElement:
    element = click(driver, by, locator, timeout=timeout)
    element.clear()
    element.send_keys(value)
    return element


def accept_alert(driver: WebDriver, *, timeout: float = ALERT_TIMEOUT) -> bool:
    try:
        WebDriverWait(driver, timeout).until(ec.alert_is_present())
    except TimeoutException:
        return False
    driver.switch_to.alert.accept()
    return True


def settled_files(directory: Path) -> set[Path]:
    return {
        path
        for path in directory.iterdir()
        if path.is_file() and not path.name.endswith(PARTIAL_SUFFIXES)
    }


def wait_download(directory: Path, *, before: set[Path], timeout: float = DOWNLOAD_TIMEOUT) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        added = settled_files(directory) - before
        if added:
            return max(added, key=lambda path: path.stat().st_mtime)
        time.sleep(0.5)

    raise DownloadError(f"{timeout}초 안에 새 파일이 내려오지 않았습니다: {directory}")


def move_to(path: Path, destination: str) -> Path:
    if not destination:
        return path
    moved = resolve_dir(destination) / path.name
    return Path(shutil.move(str(path), str(moved)))
