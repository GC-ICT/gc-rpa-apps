from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from gc_rpa_core import config
from gc_rpa_core.browser import accept_alert, click, fill, settled_files, wait_download, wait_ready

USER_ID_INPUT = "txtID"
PASSWORD_INPUT = "txtPW"
LOGIN_BUTTON = "btnLogIn"

MENU_PATH = ("생산작업지시", "작업지시서 조회", "2시간 작업지시서")
MENU_ITEM = "//td[text()='{}']"
BODY_FRAME = "iSubBody"
FRAME_TIMEOUT = 30.0

PLANT_SELECT = "ctl00_ContentBody_ddlPLANT"
EXCEL_BUTTON = "ctl00_ContentBody_btnExcelBar"
ASSEMBLY_ITEM = "//li[contains(text(), '조립')]"
JOB_LINK = "//a[contains(@href, 'javascript:LineClick')]"
JOB_ID = re.compile(r"LineClick\('(\d{8}-\d{3})'")

CHOOSE_PLANT = """
const chosen = document.getElementById(arguments[0]);
if (!chosen) { return false; }
chosen.value = arguments[1];
chosen.dispatchEvent(new Event('change', {bubbles: true}));
return true;
"""

logger = logging.getLogger(__name__)


class OrderError(RuntimeError):
    pass


def login(driver: WebDriver, settings: config.RpaConfig) -> None:
    driver.get(settings.url)
    wait_ready(driver)
    fill(driver, By.ID, USER_ID_INPUT, settings.user_id)
    fill(driver, By.ID, PASSWORD_INPUT, settings.password)
    click(driver, By.ID, LOGIN_BUTTON)
    wait_ready(driver)
    accept_alert(driver)


def enter_body(driver: WebDriver) -> None:
    driver.switch_to.default_content()
    WebDriverWait(driver, FRAME_TIMEOUT).until(
        EC.frame_to_be_available_and_switch_to_it(BODY_FRAME)
    )


def open_menu(driver: WebDriver) -> None:
    for label in MENU_PATH:
        click(driver, By.XPATH, MENU_ITEM.format(label))
    enter_body(driver)


def open_list(driver: WebDriver, plant: str) -> None:
    enter_body(driver)
    if not driver.execute_script(CHOOSE_PLANT, PLANT_SELECT, plant):
        raise OrderError(f"{plant}공장 선택 상자를 찾지 못했습니다")
    wait_ready(driver)
    enter_body(driver)


def job_ids(driver: WebDriver) -> list[str]:
    found = set()
    for link in driver.find_elements(By.XPATH, JOB_LINK):
        match = JOB_ID.search(link.get_attribute("href") or "")
        if match:
            found.add(match.group(1))
    return sorted(found, reverse=True)


def assembly_jobs(driver: WebDriver) -> list[str]:
    lines = len(driver.find_elements(By.XPATH, ASSEMBLY_ITEM))
    found = job_ids(driver)
    if lines > len(found):
        logger.warning("      조립 %d줄인데 작업지시 링크는 %d개뿐입니다", lines, len(found))
    return found[:lines]


def fetch(driver: WebDriver, job: str, downloads: Path) -> Path:
    before = settled_files(downloads)
    click(driver, By.XPATH, f"//a[contains(@href, '{job}')]")
    wait_ready(driver)
    click(driver, By.ID, EXCEL_BUTTON)
    return wait_download(downloads, before=before)


def sweep(driver: WebDriver, plant: str, downloads: Path) -> list[Path]:
    open_list(driver, plant)
    jobs = assembly_jobs(driver)
    if not jobs:
        logger.info("      %s공장 조립 작업이 없습니다", plant)
        return []

    taken = []
    for job in jobs:
        open_list(driver, plant)
        logger.info("      %s공장 %s", plant, job)
        taken.append(fetch(driver, job, downloads))
    return taken


def run(
    driver: WebDriver,
    settings: config.RpaConfig,
    *,
    plants: Sequence[str],
    downloads: Path,
) -> list[Path]:
    login(driver, settings)
    open_menu(driver)

    taken: list[Path] = []
    for plant in plants:
        got = sweep(driver, plant, downloads)
        logger.info("      %s공장 %d건 받았습니다", plant, len(got))
        taken.extend(got)
    return taken
