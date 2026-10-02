from collections.abc import Callable, Collection
from enum import StrEnum
from http.client import HTTPException
from typing import TypeVar
from urllib.error import HTTPError, URLError

import typer
from guardana.cli.exit_codes import ExitCode
from guardana.core.evaluator.config import JudgeUnavailableError, http_status_problem, safe_url
from guardana.core.redaction import EvidenceRedactor
from guardana.core.target import EndpointError, display_url

T = TypeVar("T")

_AUTH_STATUSES = frozenset({401, 403, 407})
_RATE_LIMITED = 429
_CLIENT_ERROR = range(400, 500)
_BODY_READ_BYTES = 4096
_BODY_SHOWN_CHARS = 200


class EndpointFlag(StrEnum):
    """A flag that some endpoint command offers as a remedy for a failed request."""

    ADAPTER = "--adapter"
    API_KEY_ENV = "--api-key-env"
    CONCURRENCY = "--concurrency"


def _auth_advice(accepts: Collection[EndpointFlag]) -> str:
    """Spell the auth remedies for a rejected request, naming only accepted flags."""
    knobs = [flag for flag in (EndpointFlag.ADAPTER, EndpointFlag.API_KEY_ENV) if flag in accepts]
    if knobs == [EndpointFlag.ADAPTER, EndpointFlag.API_KEY_ENV]:
        return " (an --adapter's headers, or --api-key-env)"
    if knobs == [EndpointFlag.ADAPTER]:
        return " (an --adapter's headers)"
    if knobs == [EndpointFlag.API_KEY_ENV]:
        return " (--api-key-env names the variable holding the key)"
    return ""


def _rate_limit_advice(accepts: Collection[EndpointFlag]) -> str:
    """Spell the remedies for a sustained rate limit, naming only accepted flags."""
    if EndpointFlag.CONCURRENCY in accepts:
        return "lower --concurrency, or wait for the quota to reset"
    return "wait for the quota to reset"


def _status_message(exc: HTTPError, shown: str, accepts: Collection[EndpointFlag]) -> str:
    """Say what an endpoint's error status means, quoting its body when the status is not auth.

    Only 401, 403 and 407 are about credentials; any other status is answered by what the
    endpoint said, so that is shown instead of advice about a header that may be fine.
    """
    if exc.code in _AUTH_STATUSES or exc.code == _RATE_LIMITED:
        return http_status_problem(
            exc.code,
            where=f"endpoint {shown}",
            sender="the probe",
            rate_limited_remedy=_rate_limit_advice(accepts),
            rejected_remedy=f"check the auth header / body{_auth_advice(accepts)}",
        )
    if exc.code in _CLIENT_ERROR:
        return f"endpoint {shown} rejected the request (HTTP {exc.code}); {_body_snippet(exc)}"
    return f"endpoint {shown} returned HTTP {exc.code}; {_body_snippet(exc)}"


def _body_snippet(exc: HTTPError) -> str:
    """Quote the start of an error response, secrets redacted and control characters escaped."""
    try:
        raw = exc.read(_BODY_READ_BYTES)
    except (OSError, ValueError, HTTPException):
        return "its body could not be read"
    text = EvidenceRedactor().redact_spans(raw.decode("utf-8", errors="replace")).strip()
    if not text:
        return "its body was empty"
    shown = "".join(
        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")
        for char in text
    )
    if len(shown) > _BODY_SHOWN_CHARS:
        shown = f"{shown[:_BODY_SHOWN_CHARS]}…"
    return f"its body begins: {shown}"


def run_judged(action: Callable[[], T]) -> T:
    """Run `action`, ending a run whose configured judge failed with exit `4`, in the judge's words.

    For a target that reports its own failures inside the run, such as an MCP server, the
    judge is the one connection whose failure still ends it.
    """
    try:
        return action()
    except JudgeUnavailableError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc


def run_against_endpoint(
    url: str,
    action: Callable[[], T],
    *,
    accepts: Collection[EndpointFlag] = (),
) -> T:
    """Run `action`, turning endpoint connection/response failures into a clean CLI error.

    Catches network failures (`URLError`/`OSError`) and malformed responses
    (`EndpointError`), prints a one-line message to stderr, and exits with
    `TARGET_UNAVAILABLE` — the user's environment, kept apart from the gate's
    "ran, found blocking issues" and from our own defects. An error status is
    reported distinctly from an unreachable host: 401, 403 and 407 point at the
    credentials, and any other status quotes the start of the response body,
    redacted, because that is where the endpoint says what it refused. A judge's
    failure keeps the same exit code and is reported in its own words, never as
    the target's.

    `accepts` is the set of flags the calling command actually takes; the message
    names no other one, because advice that the command would reject costs the
    reader a second failed run. `url` is shown without its userinfo, query or fragment.
    """
    shown = display_url(url)
    try:
        return run_judged(action)
    except HTTPError as exc:
        typer.echo(f"error: {_status_message(exc, shown, accepts)}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc
    except (URLError, OSError, EndpointError) as exc:
        typer.echo(f"error: could not reach endpoint {shown}: {exc}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc


__all__ = [
    "EndpointFlag",
    "JudgeUnavailableError",
    "http_status_problem",
    "run_against_endpoint",
    "run_judged",
    "safe_url",
]
