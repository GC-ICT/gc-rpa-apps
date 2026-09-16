from __future__ import annotations

from pathlib import Path

from selenium.webdriver.common.by import By

from gc_rpa_core import config
from gc_rpa_core.browser import chrome, click, move_to, settled_files, wait_download, wait_ready
from gc_rpa_core.env import optional_env
from mobis_as import common

SCHEDULE_ID_ENV = "MOBIS_AS_SCHEDULE_ID"
DEFAULT_SCHEDULE_ID = "1"

SCREEN_CODE = "PU010"
MY_MENU_BUTTON = "mainframe.VFrameSet.HFrameSet.LeftFrame.form.divLnbFix.form.btnLnbMymenu"
MY_MENU_ITEM = (
    "//*[contains(@id, 'grdMymenu') and contains(@id, 'treeitemtext:text')"
    f" and contains(text(), '[{SCREEN_CODE}]')]"
)
SEARCH_BUTTON = "//*[contains(@id, 'inner_form.btnSearch:icontext')]"
EXCEL_BUTTON = "//*[contains(@id, 'btnExcelDwnl:icontext')]"


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def run(*, headless: bool = False) -> Path:
    settings = config.load(schedule_id())
    target = common.download_dir()

    with chrome(settings.url, download_dir=target, headless=headless) as driver:
        driver.get(settings.url)
        wait_ready(driver)
        common.login(driver, settings)

        click(driver, By.ID, MY_MENU_BUTTON)
        click(driver, By.XPATH, MY_MENU_ITEM)

        before = settled_files(target)
        click(driver, By.XPATH, SEARCH_BUTTON)
        click(driver, By.XPATH, EXCEL_BUTTON)

        downloaded = wait_download(target, before=before)

    return move_to(downloaded, settings.move_path)
