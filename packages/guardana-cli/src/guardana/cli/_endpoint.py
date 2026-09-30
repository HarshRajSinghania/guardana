from collections.abc import Callable
from urllib.parse import urlsplit

import typer
from guardana.core.target import ChatTransport, EndpointTarget, private_url_parts
from guardana.core.usage import UsageMeter

transport_factory: Callable[[], ChatTransport] | None = None
"""The single transport seam: when set, its product backs every endpoint the CLI builds.

Tests substitute a fake transport here; production leaves it None so `EndpointTarget`
uses its real network transport.
"""

_USABLE_SCHEMES = frozenset({"http", "https"})


def unusable_url(url: str) -> str | None:
    """Say why the built-in transports cannot use `url` as a base URL, or None when they can.

    The reason never repeats the URL: a value that is not an http(s) URL can hold
    its credential where no scrubber looks for one.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "is not a URL"
    if parts.scheme not in _USABLE_SCHEMES:
        return "must be an http or https URL"
    try:
        _ = parts.port
    except ValueError:
        # A password holding `/`, `?` or `#` ends the host early and lands here too.
        return "has a port that is not a number from 0 to 65535"
    carried = private_url_parts(url)
    if carried:
        # The transports append their API path to the base URL, so a query or a
        # fragment ends up before it, and urllib fails on userinfo instead of
        # sending it; nothing that could have worked is refused here.
        return (
            f"carries {_listed(carried)}, which the built-in endpoint transports cannot "
            f"send; a key belongs in an environment variable, never in the URL"
        )
    return None


def build_endpoint(  # noqa: PLR0913 — each is a distinct endpoint config knob, keyword-only
    url: str,
    model: str,
    *,
    api_key: str | None = None,
    system_prompt: str | None = None,
    provider: str = "openai",
    transport: ChatTransport | None = None,
    meter: UsageMeter | None = None,
) -> EndpointTarget:
    """Construct the `EndpointTarget` a probe or monitor run talks to.

    An explicit `transport` (e.g. a custom-endpoint adapter) wins; otherwise the
    test seam `transport_factory` is used if set; otherwise `EndpointTarget` builds
    its real network transport for the named provider.

    Without an explicit `transport`, a URL the built-in transports cannot use is
    refused as `--url` invalid usage, decided before the test seam substitutes one
    so a test sees the refusal a user would.

    `meter` is how a caller that builds several targets for one run keeps one bill
    across them — `probe` needs a target per planted canary, and a ceiling that
    reset on each would not be a ceiling on the run.
    """
    if transport is None:
        problem = unusable_url(url)
        if problem is not None:
            raise typer.BadParameter(f"the endpoint URL {problem}", param_hint="'--url'")
        if transport_factory is not None:
            transport = transport_factory()
    return EndpointTarget(
        url,
        model,
        api_key=api_key,
        system_prompt=system_prompt,
        provider=provider,
        transport=transport,
        meter=meter,
    )


def _listed(names: tuple[str, ...]) -> str:
    """Spell part names as prose: `a query`, `userinfo and a query`."""
    spelled = [name if name == "userinfo" else f"a {name}" for name in names]
    if len(spelled) == 1:
        return spelled[0]
    return f"{', '.join(spelled[:-1])} and {spelled[-1]}"
