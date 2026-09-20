import logging
from collections.abc import Iterator
from typing import Any

import pytest

from gc_rpa_core.report import describe_error, print_banner, start_logging


@pytest.fixture
def restored_levels() -> Iterator[None]:
    touched = ("urllib3", "gc_rpa_core.browser")
    before = {name: logging.getLogger(name).level for name in touched}
    yield
    for name, level in before.items():
        logging.getLogger(name).setLevel(level)


def test_describe_error_names_the_type_and_first_line() -> None:
    assert describe_error(ValueError("원인")) == "ValueError: 원인"


def test_describe_error_keeps_only_the_first_line() -> None:
    assert describe_error(ValueError("첫 줄\n둘째 줄")) == "ValueError: 첫 줄"


@pytest.mark.parametrize("text", ["", "   ", "Message:", "Message: None", "None"])
def test_describe_error_replaces_an_empty_detail(text: str) -> None:
    assert describe_error(ValueError(text)) == "ValueError: 상세 메시지가 없습니다"


def test_describe_error_handles_selenium_style_empty_message() -> None:
    from selenium.common.exceptions import TimeoutException

    assert describe_error(TimeoutException()) == "TimeoutException: 상세 메시지가 없습니다"


def test_print_banner_wraps_the_text(capsys: pytest.CaptureFixture[str]) -> None:
    print_banner("완료했습니다")

    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == printed[2] == "=" * 46
    assert printed[1] == "  완료했습니다"


def test_start_logging_quiets_the_chatty_libraries(restored_levels: None) -> None:
    start_logging()

    assert logging.getLogger("urllib3").level == logging.WARNING


def test_start_logging_keeps_the_named_loggers_talking(restored_levels: None) -> None:
    start_logging(verbose=("gc_rpa_core.browser",))

    assert logging.getLogger("gc_rpa_core.browser").level == logging.INFO


def test_start_logging_reads_the_level_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, restored_levels: None
) -> None:
    asked: dict[str, Any] = {}
    monkeypatch.setenv("GC_RPA_LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: asked.update(kwargs))

    start_logging()

    assert asked["level"] == "DEBUG"
