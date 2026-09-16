from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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


def server_and_port() -> tuple[str, int | None]:
    host, _, trailing = require_env(SERVER_ENV).partition(",")
    port = optional_env(PORT_ENV) or trailing
    return host.strip(), int(port) if port.strip() else None


def connect_kwargs(*, timeout: int = DEFAULT_TIMEOUT, autocommit: bool = False) -> dict[str, Any]:
    host, port = server_and_port()
    built: dict[str, Any] = {
        "server": host,
        "database": require_env(DATABASE_ENV),
        "user": require_env(USER_ENV),
        "password": require_env(PASSWORD_ENV),
        "charset": optional_env(CHARSET_ENV, DEFAULT_CHARSET),
        "timeout": timeout,
        "login_timeout": DEFAULT_LOGIN_TIMEOUT,
        "autocommit": autocommit,
    }
    if port is not None:
        built["port"] = port
    return built


@contextmanager
def connect(*, timeout: int = DEFAULT_TIMEOUT, autocommit: bool = False) -> Iterator[Any]:
    import pymssql

    connection = pymssql.connect(**connect_kwargs(timeout=timeout, autocommit=autocommit))
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
    *, timeout: int = DEFAULT_TIMEOUT, autocommit: bool = False, as_dict: bool = True
) -> Iterator[Any]:
    with connect(timeout=timeout, autocommit=autocommit) as connection:
        opened = connection.cursor(as_dict=as_dict)
        try:
            yield opened
        finally:
            opened.close()
