from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from autoway_mail import __main__ as entry
from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint


def _reporter(sent: dict[str, object]) -> Any:
    class Recorder:
        connected = False

        def started(self, **kw: object) -> None:
            sent.update(kw)

        def finished(self, **kw: object) -> None:
            sent.update(kw)

        def failed(self, **kw: object) -> None:
            sent.update(kw)

        def send(self, *_: object, **__: object) -> None:
            return None

    @contextmanager
    def fake() -> Iterator[Recorder]:
        yield Recorder()

    return fake


def _endpoint() -> DbEndpoint:
    return DbEndpoint(host="", port=None, database="", user="", password="")


def _settings(name: str) -> RpaConfig:
    return RpaConfig(
        name=name,
        url="https://test-site.invalid",
        user_id="test_user",
        password="test_pw",
        otp="",
        use_otp=False,
        move_path="test_move_dir",
        exe_name="test_app.exe",
        source=_endpoint(),
        target=_endpoint(),
    )


def test_notify_never_raises() -> None:
    def boom(**_: object) -> None:
        raise RuntimeError("허브 죽음")

    entry.notify(boom, message="원인")


def test_describe_handles_empty_exception_message() -> None:
    assert entry.describe(ValueError()) == "ValueError: 상세 메시지가 없습니다"
    assert entry.describe(ValueError("원인")) == "ValueError: 원인"


def test_main_returns_one_and_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def fail(*_a: object, **_k: object) -> Path:
        raise ValueError("메일 수집 실패")

    monkeypatch.setattr(entry.mail, "load", lambda: _settings("테스트 RPA"))
    monkeypatch.setattr(entry.mail, "run", fail)
    monkeypatch.setattr(entry, "reporter", _reporter(sent))

    assert entry.main() == 1
    assert sent["name"] == "테스트 RPA"
    assert "메일 수집 실패" in str(sent["message"])


def test_main_falls_back_when_config_has_no_name(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    monkeypatch.setattr(entry.mail, "load", lambda: _settings(""))
    monkeypatch.setattr(entry.mail, "run", lambda *_a, **_k: Path("x.xlsx"))
    monkeypatch.setattr(entry, "reporter", _reporter(sent))

    assert entry.main() == 0
    assert sent["name"] == entry.FALLBACK_SYSTEM
