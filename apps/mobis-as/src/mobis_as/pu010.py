from __future__ import annotations

import logging
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


logger = logging.getLogger(__name__)


def schedule_id() -> str:
    return optional_env(SCHEDULE_ID_ENV, DEFAULT_SCHEDULE_ID)


def run(*, headless: bool = False) -> Path:
    logger.info("[1/6] 설정 조회   schedule_id=%s", schedule_id())
    settings = config.load(schedule_id())
    target = common.download_dir()

    logger.info("[2/6] 브라우저")
    with chrome(settings.url, download_dir=target, headless=headless) as driver:
        logger.info("[3/6] 로그인      %s", settings.url)
        driver.get(settings.url)
        wait_ready(driver)
        common.login(driver, settings)

        logger.info("[4/6] 화면 열기   %s", SCREEN_CODE)
        click(driver, By.ID, MY_MENU_BUTTON)
        click(driver, By.XPATH, MY_MENU_ITEM)

        logger.info("[5/6] 조회·다운로드")
        before = settled_files(target)
        click(driver, By.XPATH, SEARCH_BUTTON)
        click(driver, By.XPATH, EXCEL_BUTTON)
        downloaded = wait_download(target, before=before)
        logger.info("      받음: %s (%s)", downloaded.name, size_text(downloaded))

    moved = move_to(downloaded, settings.move_path)
    logger.info("[6/6] 파일 이동   %s", moved.parent)
    return moved


def size_text(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1024:,.0f} KB" if size >= 1024 else f"{size} B"
