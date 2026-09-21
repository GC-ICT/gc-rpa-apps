from pathlib import Path
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig
from hd_seat_jit import orders


class FakeLink:
    def __init__(self, job: str) -> None:
        self.href = f"javascript:LineClick('{job}','X')"

    def get_attribute(self, name: str) -> str:
        return self.href if name == "href" else ""


class FakeSwitch:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def default_content(self) -> None:
        self.driver.frames.append("top")


class FakeDriver:
    def __init__(self, jobs: dict[str, list[str]], assembly: dict[str, int] | None = None) -> None:
        self.jobs = jobs
        self.assembly = assembly or {plant: len(found) for plant, found in jobs.items()}
        self.plant = ""
        self.frames: list[str] = []
        self.scripts: list[tuple[str, tuple[Any, ...]]] = []
        self.switch_to = FakeSwitch(self)
        self.visited: list[str] = []

    def get(self, url: str) -> None:
        self.visited.append(url)

    def execute_script(self, script: str, *args: Any) -> Any:
        self.scripts.append((script, args))
        if script is orders.CHOOSE_PLANT:
            self.plant = str(args[1])
            return True
        return None

    def find_elements(self, by: str, locator: str) -> list[Any]:
        if locator == orders.JOB_LINK:
            return [FakeLink(job) for job in self.jobs.get(self.plant, [])]
        if locator == orders.ASSEMBLY_ITEM:
            return [object()] * self.assembly.get(self.plant, 0)
        return []


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, str]]:
    pressed: list[tuple[str, str]] = []

    monkeypatch.setattr(orders, "click", lambda _d, by, what: pressed.append((by, what)))
    monkeypatch.setattr(orders, "fill", lambda _d, by, what, _v: pressed.append((by, what)))
    monkeypatch.setattr(orders, "wait_ready", lambda *_a, **_k: None)
    monkeypatch.setattr(orders, "accept_alert", lambda *_a, **_k: True)
    monkeypatch.setattr(orders, "enter_body", lambda driver: driver.switch_to.default_content())
    monkeypatch.setattr(orders, "settled_files", lambda _d: set())

    taken = iter(tmp_path / f"{index}.xlsx" for index in range(100))
    monkeypatch.setattr(orders, "wait_download", lambda *_a, **_k: next(taken))
    return pressed


def settings() -> RpaConfig:
    from gc_rpa_core.db import DbEndpoint

    empty = DbEndpoint("", None, "", "", "")
    return RpaConfig("t", "u", "myid", "mypw", "", False, "", "", empty, empty)


def test_login_fills_the_form_and_clears_the_alert(quiet: Any) -> None:
    orders.login(FakeDriver({}), settings())

    assert [what for _, what in quiet] == [
        orders.USER_ID_INPUT,
        orders.PASSWORD_INPUT,
        orders.LOGIN_BUTTON,
    ]


def test_the_menu_is_walked_in_order(quiet: Any) -> None:
    orders.open_menu(FakeDriver({}))

    assert [what for _, what in quiet] == [orders.MENU_ITEM.format(m) for m in orders.MENU_PATH]


def test_job_ids_come_back_newest_first_without_repeats() -> None:
    driver = FakeDriver({"1": ["20260921-001", "20260921-003", "20260921-001"]})
    driver.plant = "1"

    assert orders.job_ids(driver) == ["20260921-003", "20260921-001"]


def test_only_as_many_jobs_as_assembly_lines_are_taken() -> None:
    driver = FakeDriver({"1": ["20260921-001", "20260921-002", "20260921-003"]}, assembly={"1": 2})
    driver.plant = "1"

    assert orders.wanted_jobs(driver) == ["20260921-003", "20260921-002"]


def test_fewer_links_than_assembly_lines_is_a_warning_not_a_crash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    driver = FakeDriver({"1": ["20260921-001"]}, assembly={"1": 3})
    driver.plant = "1"

    with caplog.at_level("WARNING", logger=orders.__name__):
        assert orders.wanted_jobs(driver) == ["20260921-001"]

    assert "3줄" in caplog.text


def test_a_plant_without_assembly_work_downloads_nothing(quiet: Any, tmp_path: Path) -> None:
    driver = FakeDriver({"1": ["20260921-001"]}, assembly={"1": 0})

    assert orders.sweep(driver, "1", tmp_path) == []


def test_the_list_is_reopened_before_every_download(quiet: Any, tmp_path: Path) -> None:
    driver = FakeDriver({"2": ["20260921-001", "20260921-002"]})

    taken = orders.sweep(driver, "2", tmp_path)

    chosen = [args for script, args in driver.scripts if script is orders.CHOOSE_PLANT]
    assert len(taken) == 2
    assert len(chosen) == 3


def test_every_plant_is_swept(quiet: Any, tmp_path: Path) -> None:
    driver = FakeDriver({"1": ["20260921-001"], "2": [], "3": ["20260921-007"]})

    taken = orders.run(driver, settings(), plants=("1", "2", "3"), folder=tmp_path)

    assert len(taken) == 2


def test_a_missing_plant_box_is_an_error(quiet: Any, tmp_path: Path) -> None:
    driver = FakeDriver({})
    driver.execute_script = lambda *_a: False  # type: ignore[method-assign]

    with pytest.raises(orders.OrderError, match="1공장"):
        orders.sweep(driver, "1", tmp_path)
