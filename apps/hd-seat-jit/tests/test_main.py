from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig
from hd_seat_jit import __main__ as entry
from hd_seat_jit import common


def _hub(sent: dict[str, Any]) -> Any:
    class Recorder:
        connected = False

        def started(self, **kw: Any) -> None:
            sent["started"] = kw

        def finished(self, **kw: Any) -> None:
            sent["finished"] = kw

        def failed(self, **kw: Any) -> None:
            sent["failed"] = kw

        def progress(self, **kw: Any) -> None:
            sent.setdefault("progress", []).append(kw)

        def send(self, *_: Any, **__: Any) -> None:
            return None

    @contextmanager
    def fake(**_: Any) -> Iterator[Recorder]:
        yield Recorder()

    return fake


def test_main_reads_the_settings_and_reports(
    monkeypatch: pytest.MonkeyPatch, rpa_settings: RpaConfig
) -> None:
    sent: dict[str, Any] = {}
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))

    assert entry.main() == 0
    assert sent["started"]["name"] == "테스트 현대시트"
    assert "failed" not in sent


def test_main_makes_the_download_folder(
    monkeypatch: pytest.MonkeyPatch, rpa_settings: RpaConfig, tmp_path: Any
) -> None:
    monkeypatch.setattr(common, "load", lambda: rpa_settings)
    monkeypatch.setattr(entry.hub, "session", _hub({}))

    entry.main()

    assert ((tmp_path / "work").resolve() / "download").is_dir()


def test_main_reports_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    def boom() -> RpaConfig:
        raise LookupError("설정이 없습니다")

    monkeypatch.setattr(common, "load", boom)
    monkeypatch.setattr(entry.hub, "session", _hub(sent))

    assert entry.main() == 1
    assert "설정이 없습니다" in sent["failed"]["message"]
