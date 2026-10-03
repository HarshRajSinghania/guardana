"""The one way the collector opens a database connection.

libpq quotes a connection string it cannot parse back in its error, password
included, and that error reaches a log, a traceback or a terminal. Every connection
opens here, so no failure to open one carries the password anywhere.
"""

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote

if TYPE_CHECKING:
    from psycopg import Connection
    from psycopg.rows import TupleRow

_KEYWORD_PASSWORD = re.compile(r"\bpassword\s*=\s*('(?:[^'\\]|\\.)*'?|\S+)")
_REDACTED = "***"


class DatabaseUnreachableError(Exception):
    """A connection could not be opened; the message holds no password from the URL."""


def without_password(message: str, url: str) -> str:
    """Remove every form of the connection string's password from `message`."""
    secrets: set[str] = set()
    _, scheme, rest = url.partition("://")
    if scheme:
        authority = re.split(r"[/?#]", rest, maxsplit=1)[0]
        userinfo, at, _ = authority.rpartition("@")
        _, colon, password = userinfo.partition(":")
        if at and colon and password:
            secrets.add(password)
    for match in _KEYWORD_PASSWORD.finditer(url):
        value = match.group(1)
        secrets.update({value, value.strip("'")})
    secrets.update({unquote(secret) for secret in secrets})
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        message = message.replace(secret, _REDACTED)
    return message


def connect(url: str) -> "Connection[TupleRow]":
    """Open a connection to `url`, raising `DatabaseUnreachableError` when it cannot.

    Raised outside the handler, so the original error is neither its cause nor its
    context: a framework that re-raises with the context attached would print the
    message that quotes the password.
    """
    import psycopg  # noqa: PLC0415 — imported here so a command's --help needs no driver

    try:
        return psycopg.connect(url)
    except Exception as exc:
        reason = without_password(str(exc), url)
    raise DatabaseUnreachableError(reason)


__all__ = ["DatabaseUnreachableError", "connect", "without_password"]
