from __future__ import annotations

from pathlib import Path

from gc_rpa_core import config
from gc_rpa_core.browser import resolve_dir
from gc_rpa_core.env import optional_env

DOWNLOAD_SUBDIR = "download"

POPPLER_ENV = "POPPLER_PATH"
POPPLER_BINARY = "pdftoppm"


class WorkspaceError(RuntimeError):
    pass


def workspace(settings: config.RpaConfig) -> Path:
    if not settings.move_path.strip():
        raise WorkspaceError(
            f"{config.PROCEDURE} 의 file_move_path 가 비어 있어 작업 폴더를 정할 수 없습니다"
        )
    return resolve_dir(settings.move_path)


def download_dir(settings: config.RpaConfig) -> Path:
    return resolve_dir(str(workspace(settings) / DOWNLOAD_SUBDIR))


def poppler_path() -> str:
    return optional_env(POPPLER_ENV)


def poppler_complaint() -> str:
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
