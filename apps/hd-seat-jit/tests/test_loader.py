from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from gc_rpa_core.config import RpaConfig, RpaDatabase
from gc_rpa_core.db import DbEndpoint
from hd_seat_jit import loader, sheet

ENDPOINT = DbEndpoint("test-erp.invalid", None, "MES01", "rpa", "pw")
TARGET = loader.Target(endpoint=ENDPOINT, temp_table="SDB500_Temp", queries=("EXEC SDB500_WORK",))


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append((statement, params))

    def executemany(self, statement: str, rows: Any) -> None:
        self.statements.append((statement, list(rows)))


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> FakeCursor:
    cursor = FakeCursor()

    @contextmanager
    def fake(*_a: Any, **_k: Any) -> Iterator[FakeCursor]:
        yield cursor

    monkeypatch.setattr(loader, "cursor", fake)
    return cursor


def test_the_target_comes_from_the_procedure(monkeypatch: pytest.MonkeyPatch) -> None:
    database = RpaDatabase(
        name="MES",
        source=ENDPOINT,
        target=DbEndpoint("", None, "", "", ""),
        tables=("SDB500_Temp",),
        queries=("EXEC SDB500_WORK", "EXEC SDB500_AFTER"),
    )
    monkeypatch.setattr(loader.config, "usable_database", lambda _settings: database)

    built = loader.target(RpaConfig("", "", "", "", "", False, "", "", ENDPOINT, ENDPOINT))

    assert built.temp_table == "SDB500_Temp"
    assert built.queries == ("EXEC SDB500_WORK", "EXEC SDB500_AFTER")


def test_workbooks_come_back_oldest_first(tmp_path: Path) -> None:
    import os

    first, second = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    first.write_bytes(b"")
    second.write_bytes(b"")
    os.utime(first, (1, 1))
    os.utime(second, (2, 2))

    assert loader.workbooks(tmp_path) == [first, second]


def test_an_empty_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(loader.LoaderError, match="받은 엑셀이 없습니다"):
        loader.workbooks(tmp_path)


def test_an_old_format_workbook_stops_the_run(tmp_path: Path) -> None:
    (tmp_path / "a.xlsx").write_bytes(b"")
    (tmp_path / "old.xls").write_bytes(b"")

    with pytest.raises(loader.LoaderError, match=r"old\.xls"):
        loader.workbooks(tmp_path)


def test_every_workbook_is_parsed_into_one_pile(
    tmp_path: Path, workbook: Callable[..., Path]
) -> None:
    workbook(tmp_path / "a.xlsx")
    workbook(tmp_path / "b.xlsx")

    pages = loader.parsed(tmp_path, customer_code="1001")

    assert len(loader.rows_of(pages)) == 2


def test_a_broken_workbook_stops_the_run(tmp_path: Path, workbook: Callable[..., Path]) -> None:
    workbook(tmp_path / "a.xlsx")
    (tmp_path / "b.xlsx").write_bytes(b"not a workbook")

    with pytest.raises(loader.LoaderError, match=r"b\.xlsx"):
        loader.parsed(tmp_path, customer_code="1001")


def test_the_insert_names_every_field(opened: FakeCursor) -> None:
    statement = loader.insert_statement("SDB500_Temp")

    assert statement.count("%s") == len(sheet.FIELDS)
    assert "cust_cd" in statement


def test_the_temp_table_is_emptied_before_the_insert(opened: FakeCursor) -> None:
    loader.write(TARGET, [tuple(range(len(sheet.FIELDS)))])

    assert opened.statements[0][0] == "TRUNCATE TABLE SDB500_Temp"
    assert "INSERT INTO SDB500_Temp" in opened.statements[1][0]


def test_writing_nothing_is_refused(opened: FakeCursor) -> None:
    with pytest.raises(loader.LoaderError, match="적재할 행이 없습니다"):
        loader.write(TARGET, [])

    assert opened.statements == []


def test_a_failed_insert_names_the_table(
    monkeypatch: pytest.MonkeyPatch, opened: FakeCursor
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("권한이 없습니다")

    monkeypatch.setattr(opened, "executemany", boom)

    with pytest.raises(loader.LoaderError, match="SDB500_Temp"):
        loader.write(TARGET, [tuple(range(len(sheet.FIELDS)))])


def test_the_closing_queries_run_in_order(opened: FakeCursor) -> None:
    target = loader.Target(endpoint=ENDPOINT, temp_table="t", queries=("EXEC A", "EXEC B"))

    assert loader.finish(target) == 2
    assert [statement for statement, _ in opened.statements] == ["EXEC A", "EXEC B"]


def test_a_failed_closing_query_says_which_one(
    monkeypatch: pytest.MonkeyPatch, opened: FakeCursor
) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("프로시저가 없습니다")

    monkeypatch.setattr(opened, "execute", boom)

    with pytest.raises(loader.LoaderError, match="1번째"):
        loader.finish(TARGET)


def test_the_uploaded_workbooks_are_thrown_away(tmp_path: Path) -> None:
    paths = [tmp_path / "a.xlsx", tmp_path / "b.xlsx"]
    for path in paths:
        path.write_bytes(b"")

    assert loader.discard(paths) == 2
    assert not any(path.exists() for path in paths)
