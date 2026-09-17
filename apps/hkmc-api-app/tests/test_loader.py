import json
from datetime import date, datetime
from typing import Any

import pytest

from hkmc_api_app import loader, registry


class FakeCursor:
    def __init__(self, procedure_ids: dict[str, Any] | None = None) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.many: list[tuple[str, list[Any]]] = []
        self.procedure_ids = procedure_ids or {}
        self.last: tuple[Any, ...] | None = None

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, params))
        if "OBJECT_ID" in query:
            name = params[0]
            found = self.procedure_ids.get(name)
            self.last = None if found is None else (found,)

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


@pytest.fixture
def fake_writer() -> Any:
    def install(procedure_ids: dict[str, Any] | None = None) -> tuple[FakeCursor, loader.Writer]:
        opened = FakeCursor(procedure_ids)
        connection = FakeConnection(opened)
        return opened, loader.Writer(rows=connection, procedures=connection)

    return install


def envelope(payload: dict[str, Any], *, result: str = "Z") -> dict[str, Any]:
    return {
        "outData": {
            "E_IFRESULT": result,
            "E_IFMSG": "SUCCESS" if result == "Z" else "실패",
            "OUTDATA_JSON": json.dumps(payload, ensure_ascii=False),
        }
    }


def test_table_names_follow_the_index_rule() -> None:
    assert loader.temp_table("001") == "Z_API_001_TEMP"
    assert loader.procedure("016") == "Z_API_016_PROC"


def test_two_list_apis_get_numbered_tables() -> None:
    assert loader.temp_table("003", "1") == "Z_API_0031_TEMP"
    assert loader.temp_table("003", "2") == "Z_API_0032_TEMP"
    assert loader.procedure("007", "2") == "Z_API_0072_PROC"


def test_ordinals_depend_on_list_count() -> None:
    assert loader.ordinals(registry.BY_INDEX["001"]) == ("",)
    assert loader.ordinals(registry.BY_INDEX["003"]) == ("1", "2")
    assert loader.ordinals(registry.BY_INDEX["007"]) == ("1", "2")


def test_qualified_name_is_bracketed() -> None:
    assert loader.qualified("Z_API_001_TEMP") == "[IT_Info].[dbo].[Z_API_001_TEMP]"


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
    statement = loader.insert_statement("Z_API_001_TEMP", spmon=False)

    assert "(api_dt, api_idx, api_value, api_company)" in statement
    assert statement.count("%s") == 4
    assert "[IT_Info].[dbo].[Z_API_001_TEMP]" in statement


def test_insert_statement_adds_spmon_for_monthly_apis() -> None:
    statement = loader.insert_statement("Z_API_014_TEMP", spmon=True)

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


def test_load_inserts_rows_then_runs_procedure(fake_writer: Any) -> None:
    opened, writer = fake_writer({"[IT_Info].[dbo].[Z_API_001_PROC]": 12345})
    api = registry.BY_INDEX["001"]

    counts = loader.load(
        api, envelope({"OUT_LIST": [{"A": "1"}, {"A": "2"}]}), company="HMC", writer=writer
    )

    assert counts == {"Z_API_001_TEMP": 2}
    assert len(opened.many[0][1]) == 2
    assert any("EXEC [IT_Info].[dbo].[Z_API_001_PROC]" in query for query, _ in opened.executed)


def test_load_splits_two_lists_into_two_tables(fake_writer: Any) -> None:
    opened, writer = fake_writer()
    api = registry.BY_INDEX["003"]
    result = envelope({"ET_EXPORT1": [{"A": "1"}], "ET_EXPORT2": [{"B": "1"}, {"B": "2"}]})

    counts = loader.load(api, result, company="HMC", writer=writer)

    assert counts == {"Z_API_0031_TEMP": 1, "Z_API_0032_TEMP": 2}
    assert "Z_API_0031_TEMP" in opened.many[0][0]
    assert "Z_API_0032_TEMP" in opened.many[1][0]


def test_load_skips_insert_for_empty_list(fake_writer: Any) -> None:
    opened, writer = fake_writer()

    counts = loader.load(
        registry.BY_INDEX["001"], envelope({"OUT_LIST": []}), company="HMC", writer=writer
    )

    assert counts == {"Z_API_001_TEMP": 0}
    assert opened.many == []


def test_run_procedure_skips_when_missing(fake_writer: Any) -> None:
    opened, writer = fake_writer({})

    assert loader.run_procedure("Z_API_002_PROC", date(2026, 9, 16), writer=writer) is False
    assert not any("EXEC" in query for query, _ in opened.executed)


def test_run_procedure_passes_run_dt(fake_writer: Any) -> None:
    opened, writer = fake_writer({"[IT_Info].[dbo].[Z_API_002_PROC]": 999})

    assert loader.run_procedure("Z_API_002_PROC", date(2026, 9, 16), writer=writer) is True

    executed = [(query, params) for query, params in opened.executed if "EXEC" in query]
    assert "@run_dt = %s" in executed[0][0]
    assert executed[0][1] == (date(2026, 9, 16),)


def test_load_passes_collection_date_to_procedure(fake_writer: Any) -> None:
    opened, writer = fake_writer({"[IT_Info].[dbo].[Z_API_001_PROC]": 1})

    loader.load(
        registry.BY_INDEX["001"], envelope({"OUT_LIST": [{"A": "1"}]}), company="HMC", writer=writer
    )

    executed = [(query, params) for query, params in opened.executed if "EXEC" in query]
    inserted_at = opened.many[0][1][0][0]
    assert executed[0][1] == (inserted_at.date(),)


def test_failed_response_stops_before_insert(fake_writer: Any) -> None:
    opened, writer = fake_writer()

    with pytest.raises(loader.ResponseError):
        loader.load(
            registry.BY_INDEX["001"], envelope({}, result="E"), company="HMC", writer=writer
        )

    assert opened.many == []


def test_each_api_commits_on_its_own(fake_writer: Any) -> None:
    _, writer = fake_writer()

    loader.load(
        registry.BY_INDEX["001"], envelope({"OUT_LIST": [{"A": "1"}]}), company="HMC", writer=writer
    )
    loader.load(
        registry.BY_INDEX["002"], envelope({"OUT_LIST": [{"A": "2"}]}), company="HMC", writer=writer
    )

    assert writer.rows.commits == 2
    assert writer.rows.rollbacks == 0
