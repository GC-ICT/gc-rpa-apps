import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from gc_rpa_core import app

logger = logging.getLogger("test-app")


class Recorder:
    connected = False

    def __init__(self) -> None:
        self.sent: dict[str, Any] = {}

    def started(self, **kw: Any) -> None:
        self.sent["started"] = kw

    def finished(self, **kw: Any) -> None:
        self.sent["finished"] = kw

    def failed(self, **kw: Any) -> None:
        self.sent["failed"] = kw

    def progress(self, **kw: Any) -> None:
        self.sent.setdefault("progress", []).append(kw)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    opened = Recorder()

    @contextmanager
    def fake_session(**_: Any) -> Iterator[Recorder]:
        yield opened

    monkeypatch.setattr(app.hub, "session", fake_session)
    return opened


def test_a_finished_job_reports_its_summary(
    recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    def job(run: app.Run) -> app.Done:
        run.begin("테스트 시스템")
        run.step("반쯤 왔습니다")
        return app.Done("3건 처리")

    assert app.start("fallback", logger, job) == 0
    assert recorder.sent["started"] == {"name": "테스트 시스템"}
    assert recorder.sent["progress"] == [{"message": "반쯤 왔습니다", "name": "테스트 시스템"}]
    assert recorder.sent["finished"]["message"] == "3건 처리"
    assert "3건 처리" in capsys.readouterr().out


def test_a_broken_job_returns_one_but_still_reports(recorder: Recorder) -> None:
    def job(run: app.Run) -> app.Done:
        run.begin("테스트 시스템")
        return app.Done("2건 실패", broken=True)

    assert app.start("fallback", logger, job) == 1
    assert recorder.sent["failed"]["message"] == "2건 실패"
    assert "finished" not in recorder.sent


def test_a_raised_job_reports_the_error_under_the_fallback_name(recorder: Recorder) -> None:
    def job(_run: app.Run) -> app.Done:
        raise LookupError("설정이 없습니다")

    assert app.start("fallback", logger, job) == 1
    assert recorder.sent["failed"] == {
        "message": "LookupError: 설정이 없습니다",
        "name": "fallback",
    }


def test_a_job_that_broke_after_naming_itself_keeps_the_name(recorder: Recorder) -> None:
    def job(run: app.Run) -> app.Done:
        run.begin("테스트 시스템")
        raise RuntimeError("도중에 터졌습니다")

    app.start("fallback", logger, job)

    assert recorder.sent["failed"]["name"] == "테스트 시스템"


def test_the_note_is_printed_under_the_banner(
    recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    def job(run: app.Run) -> app.Done:
        run.begin("테스트 시스템")
        return app.Done("끝", note="저장 위치: /tmp")

    app.start("fallback", logger, job)

    assert "  저장 위치: /tmp" in capsys.readouterr().out


def test_the_banner_can_say_more_than_the_name(
    recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    def job(run: app.Run) -> app.Done:
        run.begin("테스트 시스템", banner="테스트 시스템 — PU010")
        return app.Done("끝")

    app.start("fallback", logger, job)

    printed = capsys.readouterr().out
    assert "테스트 시스템 — PU010" in printed
    assert recorder.sent["started"] == {"name": "테스트 시스템"}


def test_the_forwarded_errors_carry_the_system_name(recorder: Recorder) -> None:
    def job(run: app.Run) -> app.Done:
        run.begin("테스트 시스템")
        assert run.relay.system_name == "테스트 시스템"
        return app.Done("끝")

    assert app.start("fallback", logger, job) == 0
