from __future__ import annotations

import logging
from pathlib import Path

from pdf2image import convert_from_path

from gc_rpa_core.env import optional_env

POPPLER_ENV = "POPPLER_PATH"
POPPLER_BINARY = "pdftoppm"

logger = logging.getLogger(__name__)


def poppler_path() -> str:
    return optional_env(POPPLER_ENV)


def complaint() -> str:
    configured = poppler_path()
    if not configured:
        return ""
    folder = Path(configured)
    if not folder.is_dir():
        return f"{POPPLER_ENV} 폴더가 없습니다: {folder}"
    if any(folder.glob(f"{POPPLER_BINARY}*")):
        return ""
    found = next(iter(folder.rglob(f"{POPPLER_BINARY}*")), None)
    if found is not None:
        return f"{POPPLER_ENV} 를 {found.parent} 로 고쳐야 합니다 (지금은 {folder})"
    return f"{POPPLER_ENV} 폴더에 {POPPLER_BINARY} 가 없습니다: {folder}"


def to_images(pdf: Path) -> list[Path]:
    folder = poppler_path()
    try:
        pages = (
            convert_from_path(str(pdf), poppler_path=folder)
            if folder
            else convert_from_path(str(pdf))
        )
    except Exception as exc:
        logger.warning("      본문 이미지 변환을 건너뜁니다: %s", exc)
        return []

    written = []
    for number, page in enumerate(pages, start=1):
        image = pdf.with_name(f"{pdf.stem}_{number}.jpg")
        page.save(image, "JPEG")
        written.append(image)
    return written
