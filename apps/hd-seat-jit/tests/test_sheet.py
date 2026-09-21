from collections.abc import Callable
from pathlib import Path

import pytest

from hd_seat_jit import sheet


def test_the_fields_match_the_row_the_parser_builds(
    tmp_path: Path, workbook: Callable[..., Path]
) -> None:
    read = sheet.read(workbook(tmp_path / "a.xlsx"), customer_code="1001")

    assert len(sheet.FIELDS) == len(read.rows[0])


def test_a_row_carries_the_body_then_the_common_values(
    tmp_path: Path, workbook: Callable[..., Path]
) -> None:
    read = sheet.read(workbook(tmp_path / "a.xlsx"), customer_code="1001")

    assert read.rows == [
        (
            "20260921-001",
            "2026-09-21",
            1.0,
            "3",
            1.0,
            "ALC-A",
            10.0,
            120.0,
            "2026-09-21 08:00",
            "조립1라인",
            "07:50",
            "42",
            "1001",
        )
    ]


def test_the_common_cells_are_reported_on_their_own(
    tmp_path: Path, workbook: Callable[..., Path]
) -> None:
    read = sheet.read(workbook(tmp_path / "a.xlsx"), customer_code="1001")

    assert read.common == {
        "wo_down_tm": "2026-09-21 08:00",
        "wo_line_nm": "조립1라인",
        "crate_tm": "07:50",
        "wo_cnt": "42",
    }


def test_rows_without_an_order_number_are_skipped(
    tmp_path: Path, workbook: Callable[..., Path]
) -> None:
    filled = ("20260921-001", "2026-09-21", 1, 3, 1, "ALC-A", 10, 120)
    empty = ("", "2026-09-21", 1, 3, 2, "ALC-B", 5, 125)
    path = workbook(tmp_path / "a.xlsx", rows=(filled, empty, filled))

    assert len(sheet.read(path, customer_code="1001").rows) == 2


def test_the_line_is_read_as_a_plain_number(tmp_path: Path, workbook: Callable[..., Path]) -> None:
    path = workbook(tmp_path / "a.xlsx", rows=(("W1", "d", 1, 12.0, 1, "A", 1, 1),))

    assert sheet.read(path, customer_code="1001").rows[0][3] == "12"


def test_a_missing_quantity_counts_as_zero(tmp_path: Path, workbook: Callable[..., Path]) -> None:
    path = workbook(tmp_path / "a.xlsx", rows=(("W1", "d", 1, 3, 1, "A", None, "-"),))

    row = sheet.read(path, customer_code="1001").rows[0]
    assert row[6] == 0.0
    assert row[7] == 0.0


def test_header_spacing_does_not_matter(tmp_path: Path, workbook: Callable[..., Path]) -> None:
    spaced = ("작업 지시 번호", "일자", "공장", "라   인", "순번", "완성품사양", "수량", "누계")
    path = workbook(tmp_path / "a.xlsx", labels=spaced)

    assert sheet.read(path, customer_code="1001").rows[0][0] == "20260921-001"


def test_a_missing_header_is_refused(tmp_path: Path, workbook: Callable[..., Path]) -> None:
    lacking = ("작업지시번호", "일 자", "공 장", "라 인", "순 번", "완성품사양", "수 량", "뭐지")
    path = workbook(tmp_path / "a.xlsx", labels=lacking)

    with pytest.raises(sheet.SheetError, match="누 계"):
        sheet.read(path, customer_code="1001")


def test_the_source_path_comes_back_with_the_rows(
    tmp_path: Path, workbook: Callable[..., Path]
) -> None:
    path = workbook(tmp_path / "a.xlsx")

    assert sheet.read(path, customer_code="1001").source == path
