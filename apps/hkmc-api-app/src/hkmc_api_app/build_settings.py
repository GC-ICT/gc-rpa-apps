from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gc_rpa_core.env import bundle_dir, frozen, optional_env, resource_dir

FILE_NAME = "build-settings.json"
TARGET_ENV = "HKMC_BUILD"


class BuildSettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Build:
    name: str
    schedule_id: str
    indexes: tuple[str, ...]
    signalr_system: str = ""


def candidates() -> list[Path]:
    packed = resource_dir()
    found = [] if packed is None else [packed / FILE_NAME]
    found.append(bundle_dir() / FILE_NAME)
    found.append(Path(__file__).resolve().parents[2] / FILE_NAME)
    return found


def path() -> Path:
    for candidate in candidates():
        if candidate.is_file():
            return candidate
    raise BuildSettingsError(f"{FILE_NAME} 을 찾지 못했습니다")


def document() -> dict[str, Any]:
    try:
        parsed: dict[str, Any] = json.loads(path().read_text(encoding="utf-8"))
        return parsed
    except json.JSONDecodeError as exc:
        raise BuildSettingsError(f"{FILE_NAME} 을 해석하지 못했습니다: {exc}") from exc


def indexes_for(apis: dict[str, Any], name: str) -> tuple[str, ...]:
    return tuple(
        index
        for index, entry in sorted(apis.items())
        if entry["output"]["include"] and entry["output"].get("fileName") == name
    )


def builds() -> tuple[Build, ...]:
    parsed = document()
    apis = parsed["apis"]
    return tuple(
        Build(
            name=name,
            schedule_id=str(entry["scheduleId"]),
            indexes=indexes_for(apis, name),
            signalr_system=str(entry.get("signalrSystem", "")),
        )
        for name, entry in parsed["builds"].items()
    )


def target_name() -> str:
    configured = optional_env(TARGET_ENV)
    if configured:
        return configured
    return Path(sys.executable).stem if frozen() else ""


def current() -> Build:
    available = builds()
    if not available:
        raise BuildSettingsError(f"{FILE_NAME} 에 builds 가 비어 있습니다")

    wanted = target_name()
    if not wanted and len(available) == 1:
        return available[0]
    if not wanted:
        names = ", ".join(build.name for build in available)
        raise BuildSettingsError(f"{TARGET_ENV} 로 빌드를 지정해야 합니다: {names}")

    for build in available:
        if build.name == wanted:
            return build

    names = ", ".join(build.name for build in available)
    raise BuildSettingsError(f"{wanted!r} 빌드가 {FILE_NAME} 에 없습니다: {names}")
