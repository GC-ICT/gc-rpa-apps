from pathlib import Path

import pytest

from autoway_mail import common


def test_schedule_id_defaults_to_five(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.SCHEDULE_ID_ENV, raising=False)

    assert common.schedule_id() == "5"


def test_schedule_id_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(common.SCHEDULE_ID_ENV, "11")

    assert common.schedule_id() == "11"


def test_download_dir_uses_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "downloads"
    monkeypatch.setenv(common.DOWNLOAD_DIR_ENV, str(target))

    assert common.download_dir() == target.resolve()
    assert target.is_dir()


def test_download_dir_defaults_to_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(common.DOWNLOAD_DIR_ENV, raising=False)

    assert common.download_dir() == (tmp_path / "downloads").resolve()


def test_size_text_switches_unit_at_one_kilobyte(tmp_path: Path) -> None:
    small = tmp_path / "small.txt"
    small.write_bytes(b"x" * 512)
    large = tmp_path / "large.txt"
    large.write_bytes(b"x" * 2048)

    assert common.size_text(small) == "512 B"
    assert common.size_text(large) == "2 KB"
