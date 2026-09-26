from collections.abc import Callable, Collection
from enum import StrEnum
from typing import TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit

import typer
from guardana.cli.exit_codes import ExitCode
from guardana.core.target import EndpointError

_HTTP_CLIENT_ERROR = 400
_HTTP_RATE_LIMITED = 429
_HTTP_SERVER_ERROR = 500

T = TypeVar("T")


class EndpointFlag(StrEnum):
    """A flag that some endpoint command offers as a remedy for a failed request."""

    ADAPTER = "--adapter"
    API_KEY_ENV = "--api-key-env"
    CONCURRENCY = "--concurrency"


def safe_url(url: str) -> str:
    """Return `url` with its userinfo, query and fragment removed, for a message a reader sees.

    A configured endpoint can carry a credential in any of those three places.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


class JudgeUnavailableError(EndpointError):
    """A grading call failed at a config-built judge's endpoint, not at the target's.

    An `EndpointError`, so the runner ends the run as it does for any unreachable
    endpoint; the message names the `evaluators:` block and the judge's URL, without
    credentials, so the CLI never blames the target for it.
    """

    def __init__(self, block: str, endpoint: str, problem: str) -> None:
        self.block = block
        self.endpoint = endpoint
        super().__init__(problem)


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
    "ran, found blocking issues" and from our own defects. A 4xx is
    reported distinctly from an unreachable host: a rejected request usually means
    a wrong auth header or body, not a down endpoint. A judge's failure keeps the
    same exit code and is reported in its own words, never as the target's.

    `accepts` is the set of flags the calling command actually takes; the message
    names no other one, because advice that the command would reject costs the
    reader a second failed run.
    """
    try:
        return action()
    except JudgeUnavailableError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc
    except HTTPError as exc:
        if exc.code == _HTTP_RATE_LIMITED:
            # Reaching here means the retries were already exhausted, so this is a
            # sustained limit rather than a blip. Naming the knob beats the generic
            # 4xx advice, which would send someone to check an auth header that is
            # working fine.
            message = (
                f"endpoint {url} kept rate-limiting the probe (HTTP 429) even after retries — "
                f"{_rate_limit_advice(accepts)}"
            )
        elif _HTTP_CLIENT_ERROR <= exc.code < _HTTP_SERVER_ERROR:
            message = (
                f"endpoint {url} rejected the request (HTTP {exc.code}) — "
                f"check the auth header / body{_auth_advice(accepts)}"
            )
        else:
            message = f"endpoint {url} returned HTTP {exc.code}"
        typer.echo(f"error: {message}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc
    except (URLError, OSError, EndpointError) as exc:
        typer.echo(f"error: could not reach endpoint {url}: {exc}", err=True)
        raise typer.Exit(code=ExitCode.TARGET_UNAVAILABLE) from exc
