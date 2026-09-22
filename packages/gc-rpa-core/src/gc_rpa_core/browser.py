from __future__ import annotations

import atexit
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, TimeoutException
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
DOWNLOAD_POLL = 0.5
PARTIAL_SUFFIXES = (".crdownload", ".tmp", ".part")
STAMP_FORMAT = "%H%M%S"
SLOW_START_SECONDS = 3.0

CDP_TIMEOUT = 20.0
FRAME_POLL = 0.3
FRAMES = "iframe, frame"
EXPAND_SETTLE = 0.6

EXPAND_PAGE = """
var loose = '::-webkit-scrollbar{display:none !important}'
  + 'html,body{overflow:visible !important;height:auto !important;max-height:none !important}';
function relax(doc) {
  var style = doc.createElement('style');
  style.textContent = loose;
  (doc.head || doc.documentElement).appendChild(style);
}
function unclip(doc) {
  var view = doc.defaultView || window;
  var opened = 0;
  var all = doc.querySelectorAll('*');
  for (var i = 0; i < all.length; i++) {
    var box = all[i];
    if (box.scrollHeight <= box.clientHeight + 4) { continue; }
    var flow = view.getComputedStyle(box).overflowY;
    if (flow !== 'auto' && flow !== 'scroll' && flow !== 'hidden') { continue; }
    box.style.maxHeight = 'none';
    box.style.height = box.scrollHeight + 'px';
    box.style.overflow = 'visible';
    opened++;
  }
  return opened;
}
function stretch(frame) {
  var inner = frame.contentDocument;
  if (!inner || !inner.body) { return 0; }
  relax(inner);
  var opened = unclip(inner);
  var tall = Math.max(inner.body.scrollHeight, inner.documentElement.scrollHeight);
  var wide = Math.max(inner.body.scrollWidth, inner.documentElement.scrollWidth);
  frame.setAttribute('scrolling', 'no');
  frame.style.height = tall + 'px';
  frame.style.maxHeight = 'none';
  if (wide > frame.clientWidth) { frame.style.width = wide + 'px'; }
  return opened;
}
var opened = 0;
for (var pass = 0; pass < 2; pass++) {
  relax(document);
  opened += unclip(document);
  var frames = document.querySelectorAll('iframe, frame');
  for (var i = 0; i < frames.length; i++) {
    try { opened += stretch(frames[i]); } catch (e) {}
  }
}
return opened;
"""


OWN_DRIVERS: set[int] = set()
TERMINATION_SIGNALS = ("SIGINT", "SIGTERM", "SIGBREAK")

DEAD_SESSION_MARKERS = (
    "max retries exceeded",
    "invalid session id",
    "failed to establish a new connection",
    "connection refused",
    "remote end closed connection without response",
    "chrome not reachable",
    "no such session",
)

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


class RendererHangError(RuntimeError):
    pass


def causes(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def session_dead(exc: BaseException) -> bool:
    from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

    dead = (InvalidSessionIdException, MaxRetryError, ProtocolError, NewConnectionError)
    for cause in causes(exc):
        if isinstance(cause, dead):
            return True
        if any(marker in str(cause).lower() for marker in DEAD_SESSION_MARKERS):
            return True
    return False


def call_cdp(
    driver: WebDriver, command: str, params: dict[str, Any], *, timeout: float = CDP_TIMEOUT
) -> dict[str, Any]:
    outcome: dict[str, Any] = {}

    def work() -> None:
        try:
            outcome["result"] = driver.execute_cdp_cmd(command, params)
        except BaseException as exc:
            outcome["error"] = exc

    worker = threading.Thread(target=work, name=f"cdp-{command}", daemon=True)
    worker.start()
    worker.join(timeout)

    if worker.is_alive():
        raise RendererHangError(
            f"{command} 가 {timeout:g}초 안에 끝나지 않았습니다 (렌더러 무응답)"
        )
    if "error" in outcome:
        raise outcome["error"]
    result: dict[str, Any] = outcome.get("result") or {}
    return result


def remember_driver(driver: WebDriver) -> int:
    process = getattr(getattr(driver, "service", None), "process", None)
    pid = int(getattr(process, "pid", 0) or 0)
    if pid:
        OWN_DRIVERS.add(pid)
    return pid


def kill_browsers() -> None:
    if os.name != "nt":
        logger.debug("윈도우가 아니라 잔여 브라우저 정리를 건너뜁니다")
        return
    for pid in sorted(OWN_DRIVERS):
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    OWN_DRIVERS.clear()


def clean_up_browsers_on_exit() -> None:
    def handle(number: int, frame: object) -> None:
        logger.warning("종료 신호 %s 를 받아 브라우저를 정리합니다", number)
        kill_browsers()
        os._exit(1)

    for name in TERMINATION_SIGNALS:
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            signal.signal(number, handle)
        except (OSError, ValueError):
            logger.debug("%s 처리기를 걸지 못했습니다", name)
    atexit.register(kill_browsers)


def resolve_dir(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def chrome(
    url: str,
    *,
    download_dir: Path,
    headless: bool = False,
    keep_dialogs: bool = False,
) -> Iterator[WebDriver]:
    options = Options()
    options.add_argument("--allow-running-insecure-content")
    options.add_argument(f"--unsafely-treat-insecure-origin-as-secure={url}")
    if headless:
        options.add_argument("--headless=new")
    if keep_dialogs:
        options.set_capability("unhandledPromptBehavior", "ignore")
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

    pid = remember_driver(driver)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    driver.set_script_timeout(PAGE_TIMEOUT)
    try:
        driver.set_window_size(*WINDOW_SIZE)
        yield driver
    finally:
        driver.quit()
        OWN_DRIVERS.discard(pid)


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


def click_if_shown(driver: WebDriver, by: str, locator: str) -> int:
    pressed = 0
    for element in driver.find_elements(by, locator):
        try:
            if not element.is_displayed():
                continue
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)
        pressed += 1
    return pressed


def here_or_none(driver: WebDriver, by: str, locator: str) -> WebElement | None:
    found = driver.find_elements(by, locator)
    return found[0] if found else None


def find_in_frames(
    driver: WebDriver, by: str, locator: str, *, timeout: float = ELEMENT_TIMEOUT
) -> WebElement | None:
    deadline = time.monotonic() + timeout
    while True:
        driver.switch_to.default_content()
        found = here_or_none(driver, by, locator)
        if found is not None:
            return found

        for frame in driver.find_elements("css selector", FRAMES):
            driver.switch_to.default_content()
            try:
                driver.switch_to.frame(frame)
            except Exception:
                continue
            found = here_or_none(driver, by, locator)
            if found is not None:
                return found

        driver.switch_to.default_content()
        if time.monotonic() >= deadline:
            return None
        time.sleep(FRAME_POLL)


def close_other_windows(driver: WebDriver, keep: str = "") -> int:
    kept = keep or driver.current_window_handle
    closed = 0
    for handle in list(driver.window_handles):
        if handle == kept:
            continue
        driver.switch_to.window(handle)
        driver.close()
        closed += 1
    driver.switch_to.window(kept)
    return closed


def accept_alert(driver: WebDriver, *, timeout: float = ALERT_TIMEOUT) -> bool:
    try:
        WebDriverWait(driver, timeout).until(ec.alert_is_present())
    except TimeoutException:
        return False
    driver.switch_to.alert.accept()
    return True


def expand_page(driver: WebDriver) -> int:
    try:
        opened = int(driver.execute_script(EXPAND_PAGE) or 0)
    except Exception:
        logger.debug("본문 펼치기를 건너뜁니다")
        return 0

    logger.debug("잘려 있던 영역 %d곳을 펼쳤습니다", opened)
    time.sleep(EXPAND_SETTLE)
    return opened


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
        time.sleep(DOWNLOAD_POLL)

    raise DownloadError(f"{timeout}초 안에 새 파일이 내려오지 않았습니다: {directory}")


def stamped_name(path: Path, moment: datetime | None = None) -> str:
    when = (moment or datetime.now()).strftime(STAMP_FORMAT)
    return f"{path.stem}_{when}{path.suffix}"


def move_to(path: Path, destination: str, *, stamp: bool = True) -> Path:
    if not destination:
        return path

    moved = resolve_dir(destination) / (stamped_name(path) if stamp else path.name)
    if moved.exists():
        logger.info("      같은 이름의 파일을 덮어씁니다: %s", moved.name)
    try:
        os.replace(path, moved)
    except OSError:
        shutil.copy2(path, moved)
        path.unlink()
    return moved
