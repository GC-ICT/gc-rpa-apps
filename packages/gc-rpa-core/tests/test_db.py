import pytest

from gc_rpa_core import MissingConfigError, db


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_DB_SERVER_ADDRESS", "test-host.invalid,1801")
    monkeypatch.setenv("ERP_DB_NAME", "test_db_name")
    monkeypatch.setenv("ERP_DB_USERNAME", "test_db_user")
    monkeypatch.setenv("ERP_DB_PASSWORD", "test_db_pw")
    for name in ("ERP_DB_PORT", "ERP_DB_CHARSET"):
        monkeypatch.delenv(name, raising=False)


def test_server_and_port_splits_comma_form() -> None:
    assert db.server_and_port() == ("test-host.invalid", 1801)


def test_server_and_port_without_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_DB_SERVER_ADDRESS", "test-host.invalid")

    assert db.server_and_port() == ("test-host.invalid", None)


def test_explicit_port_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_DB_SERVER_ADDRESS", "test-host.invalid,1433")
    monkeypatch.setenv("ERP_DB_PORT", "1801")

    assert db.server_and_port() == ("test-host.invalid", 1801)


def test_connect_kwargs_defaults() -> None:
    built = db.connect_kwargs(db.from_env())

    assert built == {
        "server": "test-host.invalid",
        "port": 1801,
        "database": "test_db_name",
        "user": "test_db_user",
        "password": "test_db_pw",
        "charset": "UTF-8",
        "timeout": 30,
        "login_timeout": 30,
        "autocommit": False,
    }


def test_connect_kwargs_omits_port_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_DB_SERVER_ADDRESS", "test-host.invalid")

    assert "port" not in db.connect_kwargs(db.from_env())


def test_connect_kwargs_honours_charset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_DB_CHARSET", "CP949")

    assert db.connect_kwargs(db.from_env())["charset"] == "CP949"


def test_connect_kwargs_uses_an_explicit_endpoint() -> None:
    endpoint = db.DbEndpoint(
        host="test-other.invalid",
        port=1433,
        database="test_other_db",
        user="test_other_user",
        password="test_other_pw",
    )

    built = db.connect_kwargs(endpoint)

    assert built["server"] == "test-other.invalid"
    assert built["database"] == "test_other_db"
    assert built["port"] == 1433


def test_endpoint_is_configured_only_with_host_and_database() -> None:
    assert db.DbEndpoint("h", None, "d", "u", "p").configured is True
    assert db.DbEndpoint("", None, "d", "u", "p").configured is False
    assert db.DbEndpoint("h", None, "", "u", "p").configured is False


@pytest.mark.parametrize(
    "name", ["ERP_DB_SERVER_ADDRESS", "ERP_DB_NAME", "ERP_DB_USERNAME", "ERP_DB_PASSWORD"]
)
def test_connect_kwargs_requires_env(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.delenv(name)

    with pytest.raises(MissingConfigError, match=name):
        db.from_env()
