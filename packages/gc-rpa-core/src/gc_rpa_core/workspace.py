from __future__ import annotations

from pathlib import Path

from gc_rpa_core import config
from gc_rpa_core.browser import resolve_dir

DOWNLOAD_SUBDIR = "download"


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
