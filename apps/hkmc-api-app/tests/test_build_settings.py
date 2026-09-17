import json
from pathlib import Path
from typing import Any

import pytest

from hkmc_api_app import build_settings

DOCUMENT = {
    "builds": {
        "hkmc-api-001": {"scheduleId": "4"},
        "hkmc-api-002": {"scheduleId": "6"},
    },
    "apis": {
        "001": {"output": {"include": True, "fileName": "hkmc-api-001"}},
        "002": {"output": {"include": True, "fileName": "hkmc-api-001"}},
        "009": {"output": {"include": False}},
        "012": {"output": {"include": True, "fileName": "hkmc-api-002"}},
    },
}


@pytest.fixture
def document(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(parsed: dict[str, Any] = DOCUMENT) -> None:
        monkeypatch.setattr(build_settings, "document", lambda: parsed)

    return install


@pytest.fixture(autouse=True)
def no_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(build_settings.TARGET_ENV, raising=False)


def test_builds_group_apis_by_file_name(document: Any) -> None:
    document()

    assert build_settings.builds() == (
        build_settings.Build("hkmc-api-001", "4", ("001", "002")),
        build_settings.Build("hkmc-api-002", "6", ("012",)),
    )


def test_excluded_apis_join_no_build(document: Any) -> None:
    document()

    assert all("009" not in build.indexes for build in build_settings.builds())


def test_current_needs_a_target_when_several_builds_exist(document: Any) -> None:
    document()

    with pytest.raises(build_settings.BuildSettingsError, match="hkmc-api-001, hkmc-api-002"):
        build_settings.current()


def test_current_follows_the_target_env(document: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    document()
    monkeypatch.setenv(build_settings.TARGET_ENV, "hkmc-api-002")

    assert build_settings.current().schedule_id == "6"


def test_current_rejects_an_unknown_target(document: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    document()
    monkeypatch.setenv(build_settings.TARGET_ENV, "hkmc-api-009")

    with pytest.raises(build_settings.BuildSettingsError, match="없습니다"):
        build_settings.current()


def test_single_build_needs_no_target(document: Any) -> None:
    document({"builds": {"only": {"scheduleId": "4"}}, "apis": DOCUMENT["apis"]})

    assert build_settings.current().name == "only"


def test_shipped_file_matches_the_registry() -> None:
    from hkmc_api_app import registry

    parsed = json.loads(Path(build_settings.path()).read_text(encoding="utf-8"))

    assert set(parsed["apis"]) == set(registry.BY_INDEX)
    for build in build_settings.builds():
        assert build.indexes
        assert str(parsed["builds"][build.name]["scheduleId"]) == build.schedule_id


def test_frozen_exe_picks_the_build_from_its_own_name(
    document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    document()
    monkeypatch.setattr(build_settings, "frozen", lambda: True)
    monkeypatch.setattr(build_settings.sys, "executable", "/opt/rpa/hkmc-api-002.exe")

    assert build_settings.current() == build_settings.Build("hkmc-api-002", "6", ("012",))


def test_target_env_wins_over_the_exe_name(document: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    document()
    monkeypatch.setattr(build_settings, "frozen", lambda: True)
    monkeypatch.setattr(build_settings.sys, "executable", "/opt/rpa/hkmc-api-002.exe")
    monkeypatch.setenv(build_settings.TARGET_ENV, "hkmc-api-001")

    assert build_settings.current().name == "hkmc-api-001"
