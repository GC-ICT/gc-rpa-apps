from __future__ import annotations

from pathlib import Path

from gc_rpa_core.env import optional_env

POPPLER_ENV = "POPPLER_PATH"
POPPLER_BINARY = "pdftoppm"


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
