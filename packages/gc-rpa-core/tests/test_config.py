from contextlib import contextmanager
from typing import Any

import pytest

from gc_rpa_core import config
from gc_rpa_core.db import DbEndpoint

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
    def __init__(
        self, row: dict[str, Any] | None, rows: list[dict[str, Any]] | None = None
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[str, ...]]] = []

    def execute(self, query: str, params: tuple[str, ...]) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


@pytest.fixture
def fake_cursor(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(row: dict[str, Any] | None, rows: list[dict[str, Any]] | None = None) -> FakeCursor:
        opened = FakeCursor(row, rows)

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


def database_row(host: str, name: str) -> dict[str, Any]:
    return {
        **ROW,
        "source_db": name,
        "source_host": host,
        "source_db_nm": "IT_Info",
        "target_host": None,
        "target_db_nm": None,
        "temp_table": " Z_API_001_TEMP, Z_API_0031_TEMP ,",
        "act_query": "EXEC FIRST_PROC; EXEC SECOND_PROC ;",
    }


def test_load_reads_actprg_id(fake_cursor: Any) -> None:
    fake_cursor(dict(ROW))

    assert config.load("1").actprg_id == "3"


def test_load_databases_calls_the_procedure_with_actprg_id(fake_cursor: Any) -> None:
    opened = fake_cursor(None, [database_row("svr-a", "운영")])

    databases = config.load_databases("3")

    query, params = opened.executed[0]
    assert "ITM250_Schedule" in query
    assert "@_actprg_id" in query
    assert params == ("GetActDatabase", "3")
    assert [database.name for database in databases] == ["운영"]


def test_load_databases_returns_every_row(fake_cursor: Any) -> None:
    fake_cursor(None, [database_row("svr-a", "운영"), database_row("svr-b", "백업")])

    databases = config.load_databases("3")

    assert [database.source.host for database in databases] == ["svr-a", "svr-b"]
    assert all(database.source.database == "IT_Info" for database in databases)
    assert all(database.source.configured for database in databases)


def test_load_databases_falls_back_to_the_database_name(fake_cursor: Any) -> None:
    fake_cursor(None, [{**database_row("svr-a", ""), "source_db_nm": "IT_Info"}])

    assert config.load_databases("3")[0].name == "IT_Info"


def test_load_databases_rejects_an_empty_answer(fake_cursor: Any) -> None:
    fake_cursor(None, [])

    with pytest.raises(LookupError, match="actprg_id='99'"):
        config.load_databases("99")


def test_load_databases_splits_the_table_list(fake_cursor: Any) -> None:
    fake_cursor(None, [database_row("svr-a", "운영")])

    assert config.load_databases("3")[0].tables == ("Z_API_001_TEMP", "Z_API_0031_TEMP")


def test_load_databases_splits_the_query_list(fake_cursor: Any) -> None:
    fake_cursor(None, [database_row("svr-a", "운영")])

    assert config.load_databases("3")[0].queries == ("EXEC FIRST_PROC", "EXEC SECOND_PROC")


def test_load_databases_leaves_empty_columns_empty(fake_cursor: Any) -> None:
    fake_cursor(None, [{**database_row("svr-a", "운영"), "temp_table": None, "act_query": ""}])

    database = config.load_databases("3")[0]

    assert database.tables == ()
    assert database.queries == ()


def rpa_database(**fields: Any) -> config.RpaDatabase:
    defaults: dict[str, Any] = {
        "name": "운영",
        "source": DbEndpoint("svr-a", None, "IT_Info", "rpa", "pw"),
        "target": DbEndpoint("", None, "", "", ""),
        "tables": ("Z_API_001_TEMP",),
        "queries": ("EXEC A_PROC",),
    }
    return config.RpaDatabase(**{**defaults, **fields})


def test_a_database_is_labelled_by_its_name() -> None:
    assert rpa_database().label == "운영"


def test_a_nameless_database_is_labelled_by_its_endpoint() -> None:
    assert rpa_database(name="").label == "svr-a/IT_Info"


def test_a_filled_in_database_has_nothing_to_complain_about() -> None:
    assert rpa_database().complaint == ""


def test_a_database_complains_about_its_empty_endpoint() -> None:
    empty = DbEndpoint("", None, "", "", "")

    assert "접속정보" in rpa_database(source=empty).complaint


def test_a_database_complains_about_its_missing_tables() -> None:
    assert "temp_table" in rpa_database(tables=()).complaint


def test_a_database_complains_about_its_missing_queries() -> None:
    assert "act_query" in rpa_database(queries=()).complaint
