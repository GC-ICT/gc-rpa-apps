from datetime import date
from pathlib import Path
from typing import Any

import pytest

from gc_rpa_autoway import erp
from gc_rpa_core.config import RpaDatabase
from gc_rpa_core.db import DbEndpoint

FILE_TABLE = "[ERPFileDB].[dbo].[HRA700_File]"
HEADER = (
    "EXEC [ERP].[dbo].[HRA700_Work] @_fac_cd = 'P01', @_acpt_dt = {acpt_dt}, "
    "@_acpt_bc = 'HR61401', @_send_cust = {sender}, @_mail_sub = {subject}, "
    "@_save_ty = 'INSERT'"
)
TARGET = erp.Target(
    endpoint=DbEndpoint("test-erp.invalid", None, "ERP", "user", "pw"),
    header=HEADER,
    file_table=FILE_TABLE,
    key_column="mail_no",
)


class FakeCursor:
    def __init__(self, header: Any) -> None:
        self.header = header
        self.statements: list[tuple[str, Any]] = []

    def execute(self, statement: str, params: Any = None) -> None:
        self.statements.append((statement, params))

    def fetchone(self) -> Any:
        return self.header


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> Any:
    from contextlib import contextmanager

    def install(header: Any) -> FakeCursor:
        cursor = FakeCursor(header)

        @contextmanager
        def fake(*_a: Any, **_k: Any) -> Any:
            yield cursor

        monkeypatch.setattr(erp, "cursor", fake)
        return cursor

    return install


def folder_with(tmp_path: Path, *names: str) -> Path:
    folder = tmp_path / "mail"
    folder.mkdir()
    for name in names:
        (folder / name).write_bytes(b"content")
    return folder


def test_register_returns_the_document_number(tmp_path: Path, opened: Any) -> None:
    opened(("OK", "HR-9"))

    assert (
        erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)
        == "HR-9"
    )


def slots(cursor: FakeCursor) -> dict[str, int]:
    inserts = [params for statement, params in cursor.statements if FILE_TABLE in statement]
    return {row[3]: row[1] for row in inserts}


def test_images_take_the_first_two_slots(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    folder = folder_with(tmp_path, "document_1.jpg", "document_2.jpg", "document.pdf", "mail.eml")

    erp.register(folder, sender="보낸이", subject="제목", target=TARGET)

    assert slots(cursor) == {
        "document_1.jpg": 1,
        "document_2.jpg": 2,
        "document.pdf": 3,
        "mail.eml": 11,
    }


def test_a_third_image_is_left_out(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    folder = folder_with(tmp_path, "a_1.jpg", "a_2.jpg", "a_3.jpg", "a.pdf")

    erp.register(folder, sender="보낸이", subject="제목", target=TARGET)

    assert "a_3.jpg" not in slots(cursor)


def test_pdfs_start_at_the_third_slot_even_without_images(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))

    erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)

    assert slots(cursor) == {"a.pdf": 3}


def test_the_ninth_pdf_is_left_out(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    names = [f"p{index}.pdf" for index in range(1, 10)]

    erp.register(folder_with(tmp_path, *names), sender="보낸이", subject="제목", target=TARGET)

    placed = slots(cursor)
    assert len(placed) == 8
    assert max(placed.values()) == 10
    assert "p9.pdf" not in placed


def test_other_attachments_start_at_the_eleventh_slot(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))

    erp.register(
        folder_with(tmp_path, "b.xlsx", "a.eml"), sender="보낸이", subject="제목", target=TARGET
    )

    assert slots(cursor) == {"a.eml": 11, "b.xlsx": 12}


def test_docinfo_files_are_never_uploaded(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))

    erp.register(
        folder_with(tmp_path, "DocInfo.xlsx", "a.pdf"),
        sender="보낸이",
        subject="제목",
        target=TARGET,
    )

    assert "DocInfo.xlsx" not in slots(cursor)


def test_a_zip_attachment_is_unpacked_and_uploaded(tmp_path: Path, opened: Any) -> None:
    import zipfile

    cursor = opened(("OK", "HR-9"))
    folder = folder_with(tmp_path, "a.pdf")
    archive = folder / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as packed:
        packed.writestr("inner.txt", "속 내용")

    erp.register(folder, sender="보낸이", subject="제목", target=TARGET)

    placed = slots(cursor)
    assert "inner.txt" in placed
    assert "bundle.zip" not in placed
    assert not archive.exists()


def test_a_broken_zip_is_uploaded_as_is(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    folder = folder_with(tmp_path, "a.pdf")
    (folder / "broken.zip").write_bytes(b"not a zip")

    erp.register(folder, sender="보낸이", subject="제목", target=TARGET)

    assert "broken.zip" in slots(cursor)


def test_the_file_name_is_cleaned_and_capped(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    folder = folder_with(tmp_path, "보고서%%%(9월).pdf")

    erp.register(folder, sender="보낸이", subject="제목", target=TARGET)

    assert "보고서(9월).pdf" in slots(cursor)


def test_a_very_long_name_is_trimmed() -> None:
    assert len(erp.clean_name("가" * 400 + ".pdf")) == erp.NAME_LIMIT


def test_uploaded_rows_carry_the_mail_no_and_size(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)

    row = next(params for statement, params in cursor.statements if FILE_TABLE in statement)
    assert row[0] == "HR-9"
    assert row[2] == bytearray(b"content")
    assert row[4] == len(b"content")


def test_the_blob_is_a_bytearray_so_pymssql_sends_it_as_binary(tmp_path: Path, opened: Any) -> None:
    from pymssql import _mssql

    cursor = opened(("OK", "HR-9"))
    folder = tmp_path / "mail"
    folder.mkdir()
    (folder / "plain.txt").write_bytes(b"ascii only")

    erp.register(folder, sender="보낸이", subject="제목", target=TARGET)

    row = next(params for statement, params in cursor.statements if FILE_TABLE in statement)
    assert isinstance(row[2], bytearray)
    assert b"0x" in _mssql.substitute_params(b"VALUES (%s)", (row[2],))


def test_the_file_insert_fills_the_audit_columns_itself(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)

    statement = next(s for s, _ in cursor.statements if FILE_TABLE in s)
    assert "NEWID()" in statement
    assert statement.count("GETDATE()") == 2
    assert statement.count("%s") == 5


def test_register_refuses_an_empty_folder(tmp_path: Path, opened: Any) -> None:
    opened(("OK", "HR-9"))
    empty = tmp_path / "mail"
    empty.mkdir()

    with pytest.raises(erp.ErpError, match="등록할 파일이 없습니다"):
        erp.register(empty, sender="보낸이", subject="제목", target=TARGET)


def test_a_failed_header_stops_before_any_upload(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("NG", "권한이 없습니다"))

    with pytest.raises(erp.ErpError, match="권한이 없습니다"):
        erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)

    assert not [s for s, _ in cursor.statements if FILE_TABLE in s]


def test_a_silent_procedure_is_an_error(tmp_path: Path, opened: Any) -> None:
    opened(None)

    with pytest.raises(erp.ErpError, match="응답하지 않았습니다"):
        erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)


def test_a_missing_document_number_is_an_error(tmp_path: Path, opened: Any) -> None:
    opened(("OK", ""))

    with pytest.raises(erp.ErpError, match="문서번호가 없습니다"):
        erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)


def test_a_dict_row_is_read_the_same_way(tmp_path: Path, opened: Any) -> None:
    opened({"result": "OK", "message": "HR-9"})

    assert (
        erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="제목", target=TARGET)
        == "HR-9"
    )


def test_the_header_call_passes_the_fixed_codes(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    erp.register(
        folder_with(tmp_path, "a.pdf"),
        sender="보낸이",
        subject="제목",
        target=TARGET,
        accepted_on=date(2026, 9, 17),
    )

    statement, params = cursor.statements[0]
    assert "[ERP].[dbo].[HRA700_Work]" in statement
    assert "@_fac_cd = 'P01'" in statement
    assert "@_acpt_bc = 'HR61401'" in statement
    assert params == (date(2026, 9, 17), "보낸이", "제목")


def test_an_empty_subject_falls_back_to_the_folder_name(tmp_path: Path, opened: Any) -> None:
    cursor = opened(("OK", "HR-9"))
    erp.register(folder_with(tmp_path, "a.pdf"), sender="보낸이", subject="", target=TARGET)

    assert cursor.statements[0][1][2] == "mail"


def test_decomposed_korean_survives_cleaning() -> None:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", "제작계획 배포.xlsx")

    assert decomposed != "제작계획 배포.xlsx"
    assert erp.clean_name(decomposed) == "제작계획 배포.xlsx"


def test_composed_korean_is_untouched() -> None:
    assert erp.clean_name("회의록_260917.pptx") == "회의록_260917.pptx"


def rpa_database(**fields: Any) -> RpaDatabase:
    defaults: dict[str, Any] = {
        "name": "ERP",
        "source": DbEndpoint("test-erp.invalid", None, "ERP", "user", "pw"),
        "target": DbEndpoint("", None, "", "", ""),
        "tables": (FILE_TABLE,),
        "queries": (HEADER,),
    }
    return RpaDatabase(**{**defaults, **fields})


def test_target_reads_the_statement_and_table_from_the_procedure() -> None:
    built = erp.target(rpa_database(), key_column="docu_no")

    assert built.endpoint.database == "ERP"
    assert built.header == HEADER
    assert built.file_table == FILE_TABLE
    assert built.key_column == "docu_no"


def test_target_complains_when_the_statement_is_missing() -> None:
    with pytest.raises(erp.ErpError, match="act_query"):
        erp.target(rpa_database(queries=()), key_column="mail_no")


def test_target_complains_when_the_file_table_is_missing() -> None:
    with pytest.raises(erp.ErpError, match="temp_table"):
        erp.target(rpa_database(tables=()), key_column="mail_no")


def test_the_file_insert_names_the_key_column_of_the_target() -> None:
    assert "(ID, docu_no, file_sq" in erp.file_insert(FILE_TABLE, "docu_no")


def test_usable_database_picks_the_first_filled_in_row(
    monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    rows = (rpa_database(name="빈 DB", queries=()), rpa_database(name="쓸 수 있는 DB"))
    monkeypatch.setattr(erp.config, "load_databases", lambda _: rows)

    assert erp.usable_database(rpa_settings).name == "쓸 수 있는 DB"


def test_usable_database_complains_when_every_row_is_short(
    monkeypatch: pytest.MonkeyPatch, rpa_settings: Any
) -> None:
    monkeypatch.setattr(erp.config, "load_databases", lambda _: (rpa_database(queries=()),))

    with pytest.raises(LookupError, match="act_query"):
        erp.usable_database(rpa_settings)
