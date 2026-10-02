"""A plan prices a target the way `run_target_probe` runs it: canary rules on a planted view."""

from pathlib import Path

import yaml
from _fixtures_file import fixtures_document
from guardana.core.fixtures import parse_fixtures
from guardana.core.plan import build_plan
from guardana.core.plugins import PluginMode, PluginTrust
from guardana.core.probe import planned_view
from guardana.core.profile import default_profile
from guardana.core.registry import Registry
from guardana.core.target import Capability, EndpointTarget
from guardana.core.testing import RefusingTransport
from guardana.core.testing.seeded import SeededApplication, seeded_target

_CANARY = "guardana.prompt.system_prompt_leak.canary"


def _endpoint(system_prompt: str | None = None) -> EndpointTarget:
    return EndpointTarget(
        "http://app.test", "m", system_prompt=system_prompt, transport=RefusingTransport()
    )


def test_a_planter_without_a_prompt_is_planned_with_its_canary_rules() -> None:
    registry = Registry.discover(PluginTrust(mode=PluginMode.BUILTINS))
    target = _endpoint()

    plain = build_plan(registry, default_profile(), target)
    planned = build_plan(registry, default_profile(), planned_view(target))

    assert _CANARY in plain.skipped_rule_ids
    assert _CANARY in planned.rules
    assert target.usage().requests == 0


def test_a_target_that_already_plants_a_prompt_is_planned_as_it_is() -> None:
    target = _endpoint("You are a support assistant.")

    assert planned_view(target) is target


def test_a_view_that_would_drop_a_capability_is_not_taken() -> None:
    written = fixtures_document()
    fixtures = parse_fixtures(yaml.safe_dump(written).encode("utf-8"), Path("f.yaml"))
    target = seeded_target(fixtures, SeededApplication(fixtures))

    view = planned_view(target)

    assert Capability.SEEDED_DATA in view.capabilities()
