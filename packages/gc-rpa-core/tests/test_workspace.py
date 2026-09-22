from dataclasses import replace
from pathlib import Path

import pytest

from gc_rpa_core import workspace
from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint


def settings(move_path: str) -> RpaConfig:
    empty = DbEndpoint(host="", port=None, database="", user="", password="")
    return RpaConfig(
        name="테스트",
        url="https://test-site.invalid",
        user_id="test_user",
        password="test_pw",
        otp="",
        use_otp=False,
        move_path=move_path,
        exe_name="test_app.exe",
        source=empty,
        target=empty,
    )


def test_the_workspace_comes_from_the_schedule(tmp_path: Path) -> None:
    configured = settings(str(tmp_path / "from-schedule"))

    assert workspace.workspace(configured) == (tmp_path / "from-schedule").resolve()
    assert workspace.workspace(configured).is_dir()


def test_downloads_sit_under_the_workspace(tmp_path: Path) -> None:
    configured = settings(str(tmp_path / "from-schedule"))
    base = (tmp_path / "from-schedule").resolve()

    assert workspace.download_dir(configured) == base / workspace.DOWNLOAD_SUBDIR


@pytest.mark.parametrize("move_path", ["", "   "])
def test_an_empty_move_path_is_refused(move_path: str) -> None:
    with pytest.raises(workspace.WorkspaceError, match="file_move_path"):
        workspace.workspace(replace(settings("x"), move_path=move_path))


def test_a_path_that_cannot_be_made_names_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_path: str) -> Path:
        raise FileNotFoundError(3, "지정된 경로를 찾을 수 없습니다")

    monkeypatch.setattr(workspace, "resolve_dir", refuse)

    with pytest.raises(workspace.WorkspaceError, match=r"file_move_path .* D:") as caught:
        workspace.workspace(settings("D:\\rpa\\autoway"))

    assert "지정된 경로를 찾을 수 없습니다" in str(caught.value)
