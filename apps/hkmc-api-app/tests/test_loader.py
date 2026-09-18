import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from typing import Any

import pytest

from gc_rpa_core.config import RpaDatabase
from gc_rpa_core.db import DbEndpoint
from hkmc_api_app import loader, registry


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.many: list[tuple[str, list[Any]]] = []
        self.last: tuple[Any, ...] | None = None

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))

    def executemany(self, query: str, rows: list[Any]) -> None:
        self.many.append((query, rows))

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.last

    def close(self) -> None:
        return None


class FakeConnection:
    def __init__(self, opened: FakeCursor) -> None:
        self.opened = opened
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, as_dict: bool = True) -> FakeCursor:
        return self.opened

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def tables(*keys: str) -> dict[str, str]:
    return {key: f"[IT_Info].[dbo].[Z_API_{key}_TEMP]" for key in keys}


@pytest.fixture
def fake_writer() -> Any:
    def install(
        name: str = "",
        known: dict[str, str] | None = None,
        queries: tuple[str, ...] = (),
    ) -> tuple[FakeCursor, loader.Writer]:
        opened = FakeCursor()
        connection = FakeConnection(opened)
        writer = loader.Writer(
            rows=connection,
            procedures=connection,
            name=name,
            tables=tables("001", "002", "0031", "0032") if known is None else known,
            queries=queries,
        )
        return opened, writer

    return install


def envelope(payload: dict[str, Any], *, result: str = "Z") -> dict[str, Any]:
    return {
        "outData": {
            "E_IFRESULT": result,
            "E_IFMSG": "SUCCESS" if result == "Z" else "실패",
            "OUTDATA_JSON": json.dumps(payload, ensure_ascii=False),
        }
    }


def test_table_key_reads_the_api_number() -> None:
    assert loader.table_key("Z_API_001_TEMP") == "001"
    assert loader.table_key("IT_Info.dbo.Z_API_0031_TEMP") == "0031"
    assert loader.table_key("[IT_Info].[dbo].[z_api_0072_temp]") == "0072"


def test_table_key_is_empty_for_an_unreadable_name() -> None:
    assert loader.table_key("TEMP_INBOX") == ""


def test_keys_follow_the_list_count() -> None:
    assert loader.keys(registry.BY_INDEX["001"]) == ("001",)
    assert loader.keys(registry.BY_INDEX["003"]) == ("0031", "0032")


def test_ordinals_depend_on_list_count() -> None:
    assert loader.ordinals(registry.BY_INDEX["001"]) == ("",)
    assert loader.ordinals(registry.BY_INDEX["003"]) == ("1", "2")
    assert loader.ordinals(registry.BY_INDEX["007"]) == ("1", "2")


def test_qualified_name_is_bracketed() -> None:
    assert loader.qualified("Z_API_001_TEMP") == "[IT_Info].[dbo].[Z_API_001_TEMP]"


def test_qualified_name_uses_the_database_of_the_endpoint() -> None:
    assert loader.qualified("Z_API_001_TEMP", "RPA") == "[RPA].[dbo].[Z_API_001_TEMP]"
    assert loader.qualified("staging.Z_API_001_TEMP", "RPA") == "[RPA].[staging].[Z_API_001_TEMP]"


def test_qualified_name_keeps_what_the_procedure_spelled_out() -> None:
    assert loader.qualified("OTHER.staging.Z_API_001_TEMP", "RPA") == (
        "[OTHER].[staging].[Z_API_001_TEMP]"
    )
    assert loader.qualified("[OTHER].[dbo].[Z_API_001_TEMP]") == "[OTHER].[dbo].[Z_API_001_TEMP]"


def test_unwrap_parses_the_inner_json() -> None:
    api = registry.BY_INDEX["001"]
    result = envelope({"OUT_LIST": [{"MATNR": "M1"}, {"MATNR": "M2"}]})

    assert loader.unwrap(api, result) == {"OUT_LIST": [{"MATNR": "M1"}, {"MATNR": "M2"}]}


def test_unwrap_returns_empty_list_for_missing_key() -> None:
    api = registry.BY_INDEX["003"]
    result = envelope({"ET_EXPORT1": [{"A": "1"}]})

    assert loader.unwrap(api, result) == {"ET_EXPORT1": [{"A": "1"}], "ET_EXPORT2": []}


def test_unwrap_rejects_failed_response() -> None:
    api = registry.BY_INDEX["001"]

    with pytest.raises(loader.ResponseError, match="응답이 실패했습니다"):
        loader.unwrap(api, envelope({}, result="E"))


def test_unwrap_labels_broken_envelope() -> None:
    api = registry.BY_INDEX["001"]
    broken = {"outData": {"E_IFRESULT": "Z", "OUTDATA_JSON": "{not json"}}

    with pytest.raises(loader.ResponseError, match="응답 본문"):
        loader.unwrap(api, broken)


def test_insert_statement_has_four_columns() -> None:
    statement = loader.insert_statement("[IT_Info].[dbo].[Z_API_001_TEMP]", spmon=False)

    assert "(api_dt, api_idx, api_value, api_company)" in statement
    assert statement.count("%s") == 4
    assert "[IT_Info].[dbo].[Z_API_001_TEMP]" in statement


def test_insert_statement_adds_spmon_for_monthly_apis() -> None:
    statement = loader.insert_statement("[IT_Info].[dbo].[Z_API_014_TEMP]", spmon=True)

    assert "(api_dt, api_idx, api_value, api_company, I_SPMON)" in statement
    assert statement.count("%s") == 5


def test_only_014_and_015_use_spmon() -> None:
    using = [api.index for api in registry.APIS if loader.uses_spmon(api)]

    assert using == ["014", "015"]


def test_parameters_keep_order_and_share_one_timestamp() -> None:
    moment = datetime(2026, 9, 16, 12, 0, 0)
    rows = loader.parameters(
        [{"MATNR": "M1"}, {"MATNR": "M2"}], moment=moment, company="HMC", spmon=""
    )

    assert [row[1] for row in rows] == [0, 1]
    assert {row[0] for row in rows} == {moment}
    assert {row[3] for row in rows} == {"HMC"}
    assert json.loads(rows[0][2]) == {"MATNR": "M1"}


def test_parameters_append_spmon_when_given() -> None:
    rows = loader.parameters(
        [{"A": "1"}], moment=datetime(2026, 9, 16), company="KIA", spmon="202608"
    )

    assert rows[0][4] == "202608"
    assert len(rows[0]) == 5


def test_load_inserts_into_the_table_the_procedure_named(fake_writer: Any) -> None:
    opened, writer = fake_writer(known={"001": "[RPA].[dbo].[MY_INBOX]"})
    api = registry.BY_INDEX["001"]

    counts = loader.load(
        api, envelope({"OUT_LIST": [{"A": "1"}, {"A": "2"}]}), company="HMC", targets=[writer]
    )

    assert counts == {"001": 2}
    assert len(opened.many[0][1]) == 2
    assert "[RPA].[dbo].[MY_INBOX]" in opened.many[0][0]


def test_load_skips_an_api_the_database_has_no_table_for(fake_writer: Any) -> None:
    opened, writer = fake_writer(known={"002": "[IT_Info].[dbo].[Z_API_002_TEMP]"})

    counts = loader.load(
        registry.BY_INDEX["001"],
        envelope({"OUT_LIST": [{"A": "1"}]}),
        company="HMC",
        targets=[writer],
    )

    assert counts == {}
    assert opened.many == []


def test_load_splits_two_lists_into_two_tables(fake_writer: Any) -> None:
    opened, writer = fake_writer()
    api = registry.BY_INDEX["003"]
    result = envelope({"ET_EXPORT1": [{"A": "1"}], "ET_EXPORT2": [{"B": "1"}, {"B": "2"}]})

    counts = loader.load(api, result, company="HMC", targets=[writer])

    assert counts == {"0031": 1, "0032": 2}
    assert "Z_API_0031_TEMP" in opened.many[0][0]
    assert "Z_API_0032_TEMP" in opened.many[1][0]


def test_load_skips_insert_for_empty_list(fake_writer: Any) -> None:
    opened, writer = fake_writer()

    counts = loader.load(
        registry.BY_INDEX["001"], envelope({"OUT_LIST": []}), company="HMC", targets=[writer]
    )

    assert counts == {"001": 0}
    assert opened.many == []


def test_run_queries_runs_them_in_order(fake_writer: Any) -> None:
    opened, writer = fake_writer(queries=("EXEC FIRST_PROC", "EXEC SECOND_PROC"))

    assert loader.run_queries(writer, date(2026, 9, 16)) == 2
    assert [query for query, _ in opened.executed] == ["EXEC FIRST_PROC", "EXEC SECOND_PROC"]
    assert [params for _, params in opened.executed] == [None, None]


def test_run_queries_binds_the_run_date(fake_writer: Any) -> None:
    opened, writer = fake_writer(queries=("EXEC A_PROC @run_dt = {run_dt}",))

    loader.run_queries(writer, date(2026, 9, 16))

    assert opened.executed == [("EXEC A_PROC @run_dt = %s", (date(2026, 9, 16),))]


def test_run_queries_binds_every_mention_of_the_run_date() -> None:
    statement, params = loader.bound("SELECT {run_dt}, {run_dt}", date(2026, 9, 16))

    assert statement == "SELECT %s, %s"
    assert params == (date(2026, 9, 16), date(2026, 9, 16))


def test_run_queries_names_the_database_that_failed(fake_writer: Any) -> None:
    opened, writer = fake_writer(name="db-a", queries=("EXEC A_PROC",))

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("프로시저가 없습니다")

    opened.execute = boom  # type: ignore[method-assign]

    with pytest.raises(loader.DatabaseError, match="db-a"):
        loader.run_queries(writer, date(2026, 9, 16))


def test_failed_response_stops_before_insert(fake_writer: Any) -> None:
    opened, writer = fake_writer()

    with pytest.raises(loader.ResponseError):
        loader.load(
            registry.BY_INDEX["001"], envelope({}, result="E"), company="HMC", targets=[writer]
        )

    assert opened.many == []


def test_each_api_commits_on_its_own(fake_writer: Any) -> None:
    _, writer = fake_writer()

    loader.load(
        registry.BY_INDEX["001"],
        envelope({"OUT_LIST": [{"A": "1"}]}),
        company="HMC",
        targets=[writer],
    )
    loader.load(
        registry.BY_INDEX["002"],
        envelope({"OUT_LIST": [{"A": "2"}]}),
        company="HMC",
        targets=[writer],
    )

    assert writer.rows.commits == 2
    assert writer.rows.rollbacks == 0


def _endpoint(host: str) -> DbEndpoint:
    return DbEndpoint(host=host, port=None, database="IT_Info", user="rpa", password="pw")


def _database(name: str, host: str = "svr-a", *, names: tuple[str, ...] = ()) -> RpaDatabase:
    return RpaDatabase(
        name=name,
        source=_endpoint(host),
        target=DbEndpoint("", None, "", "", ""),
        tables=names or ("Z_API_001_TEMP",),
        queries=("EXEC A_PROC",),
    )


def test_load_writes_the_same_rows_to_every_database(fake_writer: Any) -> None:
    first, one = fake_writer("db-a", {"001": "[A].[dbo].[Z_API_001_TEMP]"})
    second, two = fake_writer("db-b", {"001": "[B].[dbo].[Z_API_001_TEMP]"})

    counts = loader.load(
        registry.BY_INDEX["001"],
        envelope({"OUT_LIST": [{"A": "1"}, {"A": "2"}]}),
        company="HMC",
        targets=[one, two],
    )

    assert counts == {"001": 2}
    assert len(first.many[0][1]) == 2
    assert len(second.many[0][1]) == 2
    assert "[A].[dbo].[Z_API_001_TEMP]" in first.many[0][0]
    assert "[B].[dbo].[Z_API_001_TEMP]" in second.many[0][0]


def test_a_broken_database_does_not_stop_the_others(fake_writer: Any) -> None:
    broken_cursor, broken = fake_writer("db-a")
    healthy_cursor, healthy = fake_writer("db-b")

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("연결이 끊겼습니다")

    broken_cursor.executemany = boom  # type: ignore[method-assign]

    with pytest.raises(loader.DatabaseError) as failure:
        loader.load(
            registry.BY_INDEX["001"],
            envelope({"OUT_LIST": [{"A": "1"}]}),
            company="HMC",
            targets=[broken, healthy],
        )

    assert "db-a" in str(failure.value)
    assert "db-b" not in str(failure.value)
    assert len(healthy_cursor.many[0][1]) == 1
    assert broken.rows.rollbacks == 1


def test_writers_skips_a_database_it_cannot_reach(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    @contextmanager
    def fake(database: RpaDatabase) -> Iterator[loader.Writer]:
        if database.source.host == "unreachable":
            raise RuntimeError("접속 시간이 지났습니다")
        yield loader.Writer(rows=None, procedures=None, name=database.name)

    monkeypatch.setattr(loader, "writer", fake)

    databases = [_database("db-a", "unreachable"), _database("db-b", "fine")]

    with (
        caplog.at_level("WARNING", logger=loader.__name__),
        loader.writers(databases) as opened,
    ):
        assert [writer.name for writer in opened] == ["db-b"]

    assert "db-a" in caplog.text


def test_writers_complains_when_no_database_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def fake(_database: RpaDatabase) -> Iterator[loader.Writer]:
        raise RuntimeError("접속 시간이 지났습니다")
        yield

    monkeypatch.setattr(loader, "writer", fake)

    with pytest.raises(loader.DatabaseError), loader.writers([_database("db-a", "unreachable")]):
        pass


def test_statements_of_turns_a_procedure_name_into_an_exec() -> None:
    database = _database("운영")

    assert loader.statements_of(replace(database, queries=("Z_API_001_PROC",))) == (
        "EXEC [IT_Info].[dbo].[Z_API_001_PROC] @run_dt = {run_dt}",
    )


def test_statements_of_keeps_a_written_out_query() -> None:
    database = replace(_database("운영"), queries=("UPDATE Z_API_001_TEMP SET api_idx = 0",))

    assert loader.statements_of(database) == ("UPDATE Z_API_001_TEMP SET api_idx = 0",)


def test_statements_of_qualifies_with_the_database_of_the_endpoint() -> None:
    database = RpaDatabase(
        name="운영",
        source=DbEndpoint("svr-a", None, "RPA", "rpa", "pw"),
        target=DbEndpoint("", None, "", "", ""),
        tables=("Z_API_001_TEMP",),
        queries=("staging.Z_API_001_PROC",),
    )

    assert loader.statements_of(database) == (
        "EXEC [RPA].[staging].[Z_API_001_PROC] @run_dt = {run_dt}",
    )


def test_a_named_procedure_runs_with_the_collection_date(fake_writer: Any) -> None:
    database = replace(_database("운영"), queries=("Z_API_001_PROC",))
    opened, writer = fake_writer(queries=loader.statements_of(database))

    loader.run_queries(writer, date(2026, 9, 16))

    assert opened.executed == [
        ("EXEC [IT_Info].[dbo].[Z_API_001_PROC] @run_dt = %s", (date(2026, 9, 16),))
    ]


def test_tables_of_maps_each_name_to_its_api(caplog: pytest.LogCaptureFixture) -> None:
    database = _database("운영", names=("Z_API_001_TEMP", "staging.Z_API_0031_TEMP", "TEMP_INBOX"))

    with caplog.at_level("WARNING", logger=loader.__name__):
        found = loader.tables_of(database)

    assert found == {
        "001": "[IT_Info].[dbo].[Z_API_001_TEMP]",
        "0031": "[IT_Info].[staging].[Z_API_0031_TEMP]",
    }
    assert "TEMP_INBOX" in caplog.text
