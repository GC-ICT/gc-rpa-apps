from pathlib import Path

import pytest

from gc_rpa_core.config import RpaConfig
from gc_rpa_core.db import DbEndpoint


def endpoint() -> DbEndpoint:
    return DbEndpoint(host="", port=None, database="", user="", password="")


@pytest.fixture
def rpa_settings(tmp_path: Path) -> RpaConfig:
    return RpaConfig(
        name="테스트 오토웨이",
        url="https://test-site.invalid",
        user_id="test_user",
        password="test_pw",
        otp="",
        use_otp=False,
        move_path=str(tmp_path / "work"),
        exe_name="test_app.exe",
        source=endpoint(),
        target=endpoint(),
    )
