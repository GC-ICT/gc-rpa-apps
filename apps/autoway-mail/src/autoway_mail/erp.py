from __future__ import annotations

import logging
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from gc_rpa_core.db import DbEndpoint, cursor

HEADER_PROCEDURE = "dbo.HRA700_Work"
HEADER_CALL = f"""
EXEC {HEADER_PROCEDURE}
     @_fac_cd = %s,
     @_acpt_dt = %s,
     @_acpt_bc = %s,
     @_send_cust = %s,
     @_mail_sub = %s,
     @_save_ty = 'INSERT'
"""
HEADER_OK = "OK"

FACTORY = "P01"
ACCEPT_CODE = "HR61401"

FILE_TABLE = "[ERPFileDB].[dbo].[HRA700_File]"
FILE_INSERT = f"""
INSERT INTO {FILE_TABLE}
  (ID, mail_no, file_sq, file_byte, file_nm, file_sz, cid, cdt, mid, mdt)
VALUES (NEWID(), %s, %s, %s, %s, %s, 1, GETDATE(), 1, GETDATE())
"""

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
PDF_SUFFIX = ".pdf"
ARCHIVE_SUFFIX = ".zip"
EXCLUDED_NAMES = ("docinfo.xlsx", "docinfo.xls")

FIRST_IMAGE_SLOT = 1
FIRST_PDF_SLOT = 3
FIRST_OTHER_SLOT = 11
NAME_LIMIT = 200

logger = logging.getLogger(__name__)


class ErpError(RuntimeError):
    pass


def clean_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣\[\]\(\)\{\}\-_.\s]+", "", value).strip()[:NAME_LIMIT]


def unpack_archives(folder: Path) -> None:
    for archive in sorted(folder.rglob(f"*{ARCHIVE_SUFFIX}")):
        target = archive.with_suffix("")
        try:
            with zipfile.ZipFile(archive) as opened:
                opened.extractall(target)
        except Exception as exc:
            logger.warning("      압축을 풀지 못해 그대로 올립니다: %s (%s)", archive.name, exc)
            continue
        archive.unlink()


def wanted(path: Path) -> bool:
    return path.is_file() and path.name.lower() not in EXCLUDED_NAMES


def sorted_files(folder: Path) -> list[Path]:
    return sorted((path for path in folder.rglob("*") if wanted(path)), key=lambda p: str(p))


def classify(folder: Path) -> tuple[list[Path], list[Path], list[Path]]:
    images, pdfs, others = [], [], []
    for path in sorted_files(folder):
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            images.append(path)
        elif suffix == PDF_SUFFIX:
            pdfs.append(path)
        else:
            others.append(path)
    return images, pdfs, others


def dropped(kind: str, files: list[Path], kept: int) -> None:
    if len(files) > kept:
        names = ", ".join(path.name for path in files[kept:])
        logger.warning("      %s 슬롯이 %d개뿐이라 올리지 않습니다: %s", kind, kept, names)


def slotted(folder: Path) -> list[tuple[int, Path]]:
    images, pdfs, others = classify(folder)
    image_slots = FIRST_PDF_SLOT - FIRST_IMAGE_SLOT
    pdf_slots = FIRST_OTHER_SLOT - FIRST_PDF_SLOT

    dropped("이미지", images, image_slots)
    dropped("PDF", pdfs, pdf_slots)

    placed = [(FIRST_IMAGE_SLOT + offset, path) for offset, path in enumerate(images[:image_slots])]
    placed += [(FIRST_PDF_SLOT + offset, path) for offset, path in enumerate(pdfs[:pdf_slots])]
    placed += [(FIRST_OTHER_SLOT + offset, path) for offset, path in enumerate(others)]
    return placed


def file_row(document_no: str, slot: int, path: Path) -> tuple[Any, ...]:
    content = path.read_bytes()
    return (document_no, slot, content, clean_name(path.name), len(content))


def answered(row: Any) -> tuple[str, str]:
    values = list(row.values()) if isinstance(row, dict) else list(row)
    return str(values[0] or "").strip().upper(), str(values[1] or "").strip()


def call_header(opened: Any, *, sender: str, subject: str, accepted_on: date) -> str:
    opened.execute(HEADER_CALL, (FACTORY, accepted_on, ACCEPT_CODE, sender, subject))
    row = opened.fetchone()
    if not row:
        raise ErpError(f"{HEADER_PROCEDURE} 가 응답하지 않았습니다")

    result, message = answered(row)
    if result != HEADER_OK:
        raise ErpError(f"{HEADER_PROCEDURE} 등록 실패: {message or '사유 없음'}")
    if not message:
        raise ErpError(f"{HEADER_PROCEDURE} 응답에 mail_no 가 없습니다")
    return message


def register(
    folder: Path,
    *,
    sender: str,
    subject: str,
    accepted_on: date | None = None,
    endpoint: DbEndpoint | None = None,
) -> str:
    unpack_archives(folder)
    placed = slotted(folder)
    if not placed:
        raise ErpError(f"등록할 파일이 없습니다: {folder}")

    with cursor(endpoint, autocommit=False) as opened:
        document_no = call_header(
            opened,
            sender=sender,
            subject=subject or folder.name,
            accepted_on=accepted_on or date.today(),
        )
        for slot, path in placed:
            opened.execute(FILE_INSERT, file_row(document_no, slot, path))

    logger.info("      ERP 등록 mail_no=%s (파일 %d건)", document_no, len(placed))
    return document_no
