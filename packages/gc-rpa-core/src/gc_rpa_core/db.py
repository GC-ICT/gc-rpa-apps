from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from gc_rpa_core.env import optional_env, require_env

SERVER_ENV = "ERP_DB_SERVER_ADDRESS"
PORT_ENV = "ERP_DB_PORT"
DATABASE_ENV = "ERP_DB_NAME"
USER_ENV = "ERP_DB_USERNAME"
PASSWORD_ENV = "ERP_DB_PASSWORD"
CHARSET_ENV = "ERP_DB_CHARSET"

DEFAULT_CHARSET = "UTF-8"
DEFAULT_TIMEOUT = 30
DEFAULT_LOGIN_TIMEOUT = 30


@dataclass(frozen=True)
class DbEndpoint:
    host: str
    port: int | None
    database: str
    user: str
    password: str
    charset: str = DEFAULT_CHARSET

    @property
    def configured(self) -> bool:
        return bool(self.host and self.database)

    @property
    def label(self) -> str:
        return f"{self.host}/{self.database}" if self.host else self.database


def split_host(value: str) -> tuple[str, int | None]:
    host, _, trailing = value.partition(",")
    return host.strip(), int(trailing) if trailing.strip() else None


def server_and_port() -> tuple[str, int | None]:
    host, trailing = split_host(require_env(SERVER_ENV))
    port = optional_env(PORT_ENV)
    return host, int(port) if port.strip() else trailing


def from_env() -> DbEndpoint:
    host, port = server_and_port()
    return DbEndpoint(
        host=host,
        port=port,
        database=require_env(DATABASE_ENV),
        user=require_env(USER_ENV),
        password=require_env(PASSWORD_ENV),
        charset=optional_env(CHARSET_ENV, DEFAULT_CHARSET),
    )


def connect_kwargs(
    endpoint: DbEndpoint, *, timeout: int = DEFAULT_TIMEOUT, autocommit: bool = False
) -> dict[str, Any]:
    built: dict[str, Any] = {
        "server": endpoint.host,
        "database": endpoint.database,
        "user": endpoint.user,
        "password": endpoint.password,
        "charset": endpoint.charset or DEFAULT_CHARSET,
        "timeout": timeout,
        "login_timeout": DEFAULT_LOGIN_TIMEOUT,
        "autocommit": autocommit,
    }
    if endpoint.port is not None:
        built["port"] = endpoint.port
    return built


@contextmanager
def connect(
    endpoint: DbEndpoint | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    autocommit: bool = False,
) -> Iterator[Any]:
    import pymssql

    target = endpoint or from_env()
    connection = pymssql.connect(**connect_kwargs(target, timeout=timeout, autocommit=autocommit))
    try:
        yield connection
        if not autocommit:
            connection.commit()
    except BaseException:
        if not autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def cursor(
    endpoint: DbEndpoint | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    autocommit: bool = False,
    as_dict: bool = True,
) -> Iterator[Any]:
    with connect(endpoint, timeout=timeout, autocommit=autocommit) as connection:
        opened = connection.cursor(as_dict=as_dict)
        try:
            yield opened
        finally:
            opened.close()
