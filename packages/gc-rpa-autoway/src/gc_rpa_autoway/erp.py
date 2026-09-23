from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from gc_rpa_core.config import RpaDatabase
from gc_rpa_core.db import DbEndpoint, cursor
from gc_rpa_core.statement import bind

HEADER_OK = "OK"

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
ARCHIVE_SUFFIX = ".zip"
EXCLUDED_NAMES = ("docinfo.xlsx", "docinfo.xls")

FIRST_PREVIEW_SLOT = 1
PREVIEW_SLOTS = 2
FIRST_LISTED_SLOT = 11
NAME_LIMIT = 200

logger = logging.getLogger(__name__)


class ErpError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    endpoint: DbEndpoint
    header: str
    file_table: str
    key_column: str


def target(database: RpaDatabase, *, key_column: str) -> Target:
    if database.complaint:
        raise ErpError(database.complaint)

    return Target(
        endpoint=database.source,
        header=database.queries[0],
        file_table=database.tables[0],
        key_column=key_column,
    )


def file_insert(table: str, key_column: str) -> str:
    return (
        f"INSERT INTO {table}"
        f"\n  (ID, {key_column}, file_sq, file_byte, file_nm, file_sz, cid, cdt, mid, mdt)"
        "\nVALUES (NEWID(), %s, %s, %s, %s, %s, 1, GETDATE(), 1, GETDATE())"
    )


def clean_name(value: str) -> str:
    joined = unicodedata.normalize("NFC", value)
    return re.sub(r"[^0-9A-Za-z가-힣\[\]\(\)\{\}\-_.\s]+", "", joined).strip()[:NAME_LIMIT]


def unpack_archives(folder: Path) -> None:
    for archive in sorted(folder.rglob(f"*{ARCHIVE_SUFFIX}")):
        unpacked = archive.with_suffix("")
        try:
            with zipfile.ZipFile(archive) as opened:
                opened.extractall(unpacked)
        except Exception as exc:
            logger.warning("      압축을 풀지 못해 그대로 올립니다: %s (%s)", archive.name, exc)
            continue
        archive.unlink()


def wanted(path: Path) -> bool:
    return path.is_file() and path.name.lower() not in EXCLUDED_NAMES


def sorted_files(folder: Path) -> list[Path]:
    return sorted((path for path in folder.rglob("*") if wanted(path)), key=lambda p: str(p))


def preview_of(body: Path | None, path: Path) -> bool:
    if body is None or path.suffix.lower() not in IMAGE_SUFFIXES:
        return False
    return path.parent == body.parent and path.stem.startswith(f"{body.stem}_")


def classify(folder: Path, body: Path | None) -> tuple[list[Path], list[Path]]:
    previews, attachments = [], []
    for path in sorted_files(folder):
        if path == body:
            continue
        if preview_of(body, path):
            previews.append(path)
        else:
            attachments.append(path)
    return previews, attachments


def dropped(kind: str, files: list[Path], kept: int) -> None:
    if len(files) > kept:
        names = ", ".join(path.name for path in files[kept:])
        logger.warning("      %s 슬롯이 %d개뿐이라 올리지 않습니다: %s", kind, kept, names)


def slotted(folder: Path, *, body: Path | None = None) -> list[tuple[int, Path]]:
    previews, attachments = classify(folder, body)
    dropped("본문 이미지", previews, PREVIEW_SLOTS)

    listed = attachments if body is None or not body.is_file() else [body, *attachments]
    placed = [
        (FIRST_PREVIEW_SLOT + offset, path) for offset, path in enumerate(previews[:PREVIEW_SLOTS])
    ]
    placed += [(FIRST_LISTED_SLOT + offset, path) for offset, path in enumerate(listed)]
    return placed


def file_row(document_no: str, slot: int, path: Path) -> tuple[Any, ...]:
    content = path.read_bytes()
    return (document_no, slot, bytearray(content), clean_name(path.name), len(content))


def answered(row: Any) -> tuple[str, str]:
    values = [str(value or "").strip() for value in row]
    if len(values) == 1:
        return HEADER_OK, values[0]
    return values[0].upper(), values[1]


def call_header(opened: Any, header: str, *, sender: str, subject: str, accepted_on: date) -> str:
    statement, params = bind(header, {"acpt_dt": accepted_on, "sender": sender, "subject": subject})
    opened.execute(statement, params)
    row = opened.fetchone()
    if not row:
        raise ErpError("등록 프로시저가 응답하지 않았습니다")

    result, message = answered(row)
    if result != HEADER_OK:
        raise ErpError(f"ERP 등록 실패: {message or '사유 없음'}")
    if not message:
        raise ErpError("ERP 등록 응답에 문서번호가 없습니다")
    return message


def register(
    folder: Path,
    *,
    sender: str,
    subject: str,
    target: Target,
    body: Path | None = None,
    accepted_on: date | None = None,
) -> str:
    unpack_archives(folder)
    placed = slotted(folder, body=body)
    if not placed:
        raise ErpError(f"등록할 파일이 없습니다: {folder}")

    with cursor(target.endpoint, autocommit=False, as_dict=False) as opened:
        document_no = call_header(
            opened,
            target.header,
            sender=sender,
            subject=subject or folder.name,
            accepted_on=accepted_on or date.today(),
        )
        insert = file_insert(target.file_table, target.key_column)
        for slot, path in placed:
            opened.execute(insert, file_row(document_no, slot, path))

    logger.info("      ERP 등록 %s=%s (파일 %d건)", target.key_column, document_no, len(placed))
    return document_no
