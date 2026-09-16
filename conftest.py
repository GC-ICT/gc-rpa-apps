import pytest

from gc_rpa_core import env

ABSENT_ENV_FILENAME = ".env.pytest-absent"


@pytest.fixture(autouse=True)
def isolate_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env, "ENV_FILENAME", ABSENT_ENV_FILENAME)
