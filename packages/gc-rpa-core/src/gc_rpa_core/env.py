from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_FILENAME = ".env"


class MissingConfigError(RuntimeError):
    pass


def bundle_dir() -> Path:
    frozen = getattr(sys, "frozen", False)
    return Path(sys.executable).parent if frozen else Path.cwd()


def env_candidates() -> list[Path]:
    seen: list[Path] = []
    for base in (bundle_dir(), *bundle_dir().parents, Path.cwd(), *Path.cwd().parents):
        candidate = base / ENV_FILENAME
        if candidate not in seen:
            seen.append(candidate)
    return seen


def load_env() -> Path | None:
    for candidate in env_candidates():
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    return None


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        load_env()
        value = os.getenv(name)
    if not value:
        raise MissingConfigError(f"환경변수 {name} 가 설정되지 않았다")
    return value


def optional_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        load_env()
        value = os.getenv(name)
    return value or default
