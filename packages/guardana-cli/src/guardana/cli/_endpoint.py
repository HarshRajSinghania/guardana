from collections.abc import Callable

import typer
from guardana.core.evaluator.config import unusable_url
from guardana.core.target import ChatTransport, EndpointTarget
from guardana.core.usage import UsageMeter

transport_factory: Callable[[], ChatTransport] | None = None
"""The single transport seam: when set, its product backs every endpoint the CLI builds.

Tests substitute a fake transport here; production leaves it None so `EndpointTarget`
uses its real network transport.
"""


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


__all__ = ["build_endpoint", "transport_factory", "unusable_url"]
