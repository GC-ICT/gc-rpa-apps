from pathlib import Path

import pytest

from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint


def endpoint() -> DbEndpoint:
    return DbEndpoint(host="", port=None, database="", user="", password="")


def make_settings(name: str = "테스트 오토웨이 메일") -> RpaConfig:
    return RpaConfig(
        name=name,
        url="https://test-site.invalid",
        user_id="test_user",
        password="test_pw",
        otp="",
        use_otp=False,
        move_path="",
        exe_name="test_app.exe",
        source=endpoint(),
        target=endpoint(),
    )


@pytest.fixture
def rpa_settings() -> RpaConfig:
    return make_settings()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from autoway_mail import common

    monkeypatch.setenv(common.WORKSPACE_ENV, str(tmp_path / "work"))
    return common.workspace()
