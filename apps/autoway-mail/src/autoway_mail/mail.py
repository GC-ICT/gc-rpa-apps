from __future__ import annotations

import logging
from pathlib import Path

from autoway_mail import common
from gc_rpa_core import config
from gc_rpa_core.browser import move_to

TASK_CODE = "MAIL"

logger = logging.getLogger(__name__)


class CollectError(RuntimeError):
    pass


def schedule_id() -> str:
    return common.schedule_id()


def load() -> config.RpaConfig:
    return common.load()


def collect(settings: config.RpaConfig, target: Path) -> Path:
    raise NotImplementedError("오토웨이 메일 수집 방식이 아직 정해지지 않았습니다")


def run(settings: config.RpaConfig | None = None) -> Path:
    settings = settings or load()
    logger.info("[1/3] 설정 조회   %s (schedule_id=%s)", settings.name, schedule_id())
    target = common.download_dir()

    logger.info("[2/3] 메일 수집")
    downloaded = collect(settings, target)
    logger.info("      받았습니다: %s (%s)", downloaded.name, common.size_text(downloaded))

    moved = move_to(downloaded, settings.move_path)
    logger.info("[3/3] 파일 이동   %s", moved.parent)
    return moved
