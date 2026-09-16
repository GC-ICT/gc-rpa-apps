from contextlib import contextmanager
from typing import Any

import pytest

from gc_rpa_core import config

ROW = {
    "actprg_id": 3,
    "actprg_nm": "test_actprg_nm",
    "actprg_bc": "test_actprg_bc",
    "rpa_site": " https://test-site.invalid ",
    "rpa_id": "test_rpa_id",
    "rpa_pw": "test_rpa_pw ",
    "opt_yn": "1",
    "rpa_opt": "test_rpa_otp",
    "fold_path": "test_exe_dir",
    "file_nm": "test_app.exe",
    "file_move_path": "test_move_dir",
    "source_host": "test-source.invalid",
    "source_port": 1805,
    "source_db_nm": "test_source_db",
    "source_id": "test_source_id",
    "source_pw": "test_source_pw",
    "target_host": None,
    "target_port": None,
    "target_db_nm": None,
    "target_id": "",
    "target_pw": "",
    "temp_table": None,
    "act_query": None,
}


class FakeCursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.executed: list[tuple[str, tuple[str, ...]]] = []

    def execute(self, query: str, params: tuple[str, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


@pytest.fixture
def fake_cursor(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(row: dict[str, Any] | None) -> FakeCursor:
        opened = FakeCursor(row)

        @contextmanager
        def fake(*_a: Any, **_k: Any) -> Any:
            yield opened

        monkeypatch.setattr(config, "cursor", fake)
        return opened

    return install


def test_load_calls_stored_procedure(fake_cursor: Any) -> None:
    opened = fake_cursor(dict(ROW))

    settings = config.load("1")

    query, params = opened.executed[0]
    assert "ITM250_Schedule" in query
    assert params == ("GetActProgram", "1")
    assert settings.name == "test_actprg_nm"
    assert settings.url == "https://test-site.invalid"
    assert settings.user_id == "test_rpa_id"
    assert settings.password == "test_rpa_pw"
    assert settings.otp == "test_rpa_otp"
    assert settings.use_otp is True
    assert settings.move_path == "test_move_dir"


@pytest.mark.parametrize("value", ["Y", "1", "y", " 1 ", "T"])
def test_opt_yn_truthy_values(fake_cursor: Any, value: str) -> None:
    fake_cursor({**ROW, "opt_yn": value})

    assert config.load("1").use_otp is True


@pytest.mark.parametrize("value", ["N", "0", "", None])
def test_opt_yn_falsy_values(fake_cursor: Any, value: str | None) -> None:
    fake_cursor({**ROW, "opt_yn": value})

    assert config.load("1").use_otp is False


def test_load_tolerates_null_columns(fake_cursor: Any) -> None:
    fake_cursor({**ROW, "file_move_path": None, "rpa_opt": None, "file_nm": None})

    settings = config.load("1")

    assert settings.move_path == ""
    assert settings.otp == ""
    assert settings.exe_name == ""


def test_load_rejects_missing_row(fake_cursor: Any) -> None:
    fake_cursor(None)

    with pytest.raises(LookupError, match="schedule_id='99'"):
        config.load("99")


def test_load_reads_source_endpoint(fake_cursor: Any) -> None:
    fake_cursor(dict(ROW))

    source = config.load("1").source

    assert source.host == "test-source.invalid"
    assert source.port == 1805
    assert source.database == "test_source_db"
    assert source.configured is True


def test_load_target_endpoint_is_unconfigured(fake_cursor: Any) -> None:
    fake_cursor(dict(ROW))

    assert config.load("1").target.configured is False
