from __future__ import annotations

from pathlib import Path

from gc_rpa_core import config
from gc_rpa_core.browser import resolve_dir

DOWNLOAD_SUBDIR = "download"


class WorkspaceError(RuntimeError):
    pass


def usable_dir(path: str, what: str) -> Path:
    try:
        return resolve_dir(path)
    except OSError as exc:
        raise WorkspaceError(f"{what} 를 쓸 수 없습니다: {path} ({exc.strerror or exc})") from exc


def workspace(settings: config.RpaConfig) -> Path:
    if not settings.move_path.strip():
        raise WorkspaceError(
            f"{config.PROCEDURE} 의 file_move_path 가 비어 있어 작업 폴더를 정할 수 없습니다"
        )
    return usable_dir(settings.move_path, f"{config.PROCEDURE} 의 file_move_path")


def download_dir(settings: config.RpaConfig) -> Path:
    return usable_dir(str(workspace(settings) / DOWNLOAD_SUBDIR), "다운로드 폴더")
