from pathlib import Path

import pytest

from autoway_mail import common, mail
from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint


def _endpoint() -> DbEndpoint:
    return DbEndpoint(host="", port=None, database="", user="", password="")


def _settings(move_path: str = "") -> RpaConfig:
    return RpaConfig(
        name="테스트 오토웨이 메일",
        url="https://test-site.invalid",
        user_id="test_user",
        password="test_pw",
        otp="",
        use_otp=False,
        move_path=move_path,
        exe_name="test_app.exe",
        source=_endpoint(),
        target=_endpoint(),
    )


def test_collect_is_not_implemented_yet(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError):
        mail.collect(_settings(), tmp_path)


def test_run_moves_the_collected_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloads = tmp_path / "downloads"
    moved_to = tmp_path / "moved"
    monkeypatch.setenv(common.DOWNLOAD_DIR_ENV, str(downloads))

    def fake_collect(_: RpaConfig, target: Path) -> Path:
        path = target / "autoway.xlsx"
        path.write_bytes(b"x" * 10)
        return path

    monkeypatch.setattr(mail, "collect", fake_collect)

    result = mail.run(_settings(str(moved_to)))

    assert result.parent == moved_to.resolve()
    assert result.name.startswith("autoway_")
    assert not (downloads / "autoway.xlsx").exists()


def test_run_keeps_the_file_when_move_path_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = tmp_path / "downloads"
    monkeypatch.setenv(common.DOWNLOAD_DIR_ENV, str(downloads))

    def fake_collect(_: RpaConfig, target: Path) -> Path:
        path = target / "autoway.xlsx"
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(mail, "collect", fake_collect)

    assert mail.run(_settings()).parent == downloads.resolve()
