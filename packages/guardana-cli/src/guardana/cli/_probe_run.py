from collections.abc import Mapping
from dataclasses import dataclass, replace

from guardana.cli._endpoint import build_endpoint
from guardana.core.manifest.records import CalibrationRecord
from guardana.core.probe import ProbeOutcome, run_target_probe
from guardana.core.profile import Profile
from guardana.core.registry import Registry
from guardana.core.runner import DEFAULT_ENDPOINT_CONCURRENCY
from guardana.core.target import (
    ChatTransport,
    EndpointTarget,
)
from guardana.core.usage import UsageMeter


@dataclass(frozen=True, slots=True)
class Connection:
    """Where and how to reach the model under test."""

    url: str
    model: str
    api_key: str | None = None
    system_prompt: str | None = None
    provider: str = "openai"
    transport: ChatTransport | None = None


def run_probe(
    registry: Registry,
    profile: Profile,
    connection: Connection,
    *,
    concurrency: int = DEFAULT_ENDPOINT_CONCURRENCY,
    calibrations: Mapping[str, CalibrationRecord] | None = None,
) -> ProbeOutcome:
    """Run every endpoint-kind rule in `registry` against a live model.

    Canary rules (those requiring `PLANT_SYSTEM_PROMPT` with a declared canary) are run
    in their own pass, each against a dedicated target whose system prompt embeds that
    rule's canary marker — otherwise the rule could never observe a leak. All other
    rules run together against a single target built from `connection.system_prompt`
    (if any).

    `concurrency` bounds how many rules may be in flight at once. It applies to the
    shared pass; each canary rule keeps its own target and runs on its own, because
    a canary planted for one rule must never be visible to another.

    **Every pass shares one meter**, so the profile's budgets bound the probe rather
    than each pass of it. A target owns the meter that enforces a ceiling, and one
    target per canary meant one ceiling per canary: `--max-requests 200` bought two
    hundred requests as many times as there were canary rules installed, which is
    the number a plan had already promised was the whole run.
    """
    meter = UsageMeter(profile.budgets)
    target = _target(connection, connection.system_prompt, meter)
    probed = run_target_probe(
        registry, profile, target, concurrency=concurrency, calibrations=calibrations
    )
    # Every planted EndpointTarget shares this meter. Taking the one snapshot
    # after all passes avoids summing cumulative snapshots once per canary.
    return ProbeOutcome(replace(probed.result, usage=meter.snapshot()), probed.identity)


def _target(connection: Connection, system_prompt: str | None, meter: UsageMeter) -> EndpointTarget:
    return build_endpoint(
        connection.url,
        connection.model,
        api_key=connection.api_key,
        system_prompt=system_prompt,
        provider=connection.provider,
        transport=connection.transport,
        meter=meter,
    )


__all__ = ["Connection", "ProbeOutcome", "run_probe", "run_target_probe"]
