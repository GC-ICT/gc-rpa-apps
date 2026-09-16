import sys
from pathlib import Path

import pytest

from gc_rpa_core import MissingConfigError, env, load_env, optional_env, require_env
from gc_rpa_core.env import bundle_dir, env_candidates


def test_require_env_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GC_RPA_PROBE", "v")

    assert require_env("GC_RPA_PROBE") == "v"


def test_require_env_rejects_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GC_RPA_PROBE", raising=False)

    with pytest.raises(MissingConfigError, match="GC_RPA_PROBE"):
        require_env("GC_RPA_PROBE")


def test_require_env_rejects_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GC_RPA_PROBE", "")

    with pytest.raises(MissingConfigError):
        require_env("GC_RPA_PROBE")


def test_optional_env_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GC_RPA_PROBE", raising=False)

    assert optional_env("GC_RPA_PROBE", "기본값") == "기본값"
    assert optional_env("GC_RPA_PROBE") == ""


def test_load_env_reads_file_from_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / env.ENV_FILENAME).write_text("GC_RPA_PROBE = 'from-file'\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GC_RPA_PROBE", raising=False)

    assert load_env() == tmp_path / env.ENV_FILENAME
    assert require_env("GC_RPA_PROBE") == "from-file"


def test_require_env_falls_back_to_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / env.ENV_FILENAME).write_text("GC_RPA_PROBE=lazy\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GC_RPA_PROBE", raising=False)

    assert require_env("GC_RPA_PROBE") == "lazy"


def test_real_environment_wins_over_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / env.ENV_FILENAME).write_text("GC_RPA_PROBE=from-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GC_RPA_PROBE", "from-shell")

    assert require_env("GC_RPA_PROBE") == "from-shell"


def test_bundle_dir_is_executable_dir_when_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/app/mobis-as.exe")

    assert bundle_dir() == Path("/opt/app")


def test_bundle_dir_is_cwd_when_not_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)

    assert bundle_dir() == Path.cwd()


def test_env_candidates_include_packed_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app" / "mobisAS"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "packed"), raising=False)

    candidates = env_candidates()

    assert tmp_path / "app" / env.ENV_FILENAME in candidates
    assert tmp_path / "packed" / env.ENV_FILENAME in candidates


def test_external_env_file_wins_over_packed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beside = tmp_path / "app"
    packed = tmp_path / "packed"
    beside.mkdir()
    packed.mkdir()
    (beside / env.ENV_FILENAME).write_text("GC_RPA_PROBE=beside\n")
    (packed / env.ENV_FILENAME).write_text("GC_RPA_PROBE=packed\n")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(beside / "mobisAS"))
    monkeypatch.setattr(sys, "_MEIPASS", str(packed), raising=False)
    monkeypatch.delenv("GC_RPA_PROBE", raising=False)

    assert require_env("GC_RPA_PROBE") == "beside"


def test_packed_env_file_is_used_when_nothing_beside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    beside = tmp_path / "app"
    packed = tmp_path / "packed"
    beside.mkdir()
    packed.mkdir()
    (packed / env.ENV_FILENAME).write_text("GC_RPA_PROBE=packed\n")

    monkeypatch.chdir(beside)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(beside / "mobisAS"))
    monkeypatch.setattr(sys, "_MEIPASS", str(packed), raising=False)
    monkeypatch.delenv("GC_RPA_PROBE", raising=False)

    assert require_env("GC_RPA_PROBE") == "packed"
