"""Every MCP rule proves itself on its own samples, offline and within its declared cost."""

from contextlib import suppress

import pytest
from _offline import refuse_name_lookups
from guardana.core.rule import NotOffered, Rule, RuleContext
from guardana.core.rule.fixture import DEMANDED_OUTCOMES
from guardana.core.rule.verify import FixtureVerdict, verify_rule
from guardana.core.target import McpServerTarget
from guardana.rules.mcp import (
    McpAuthorizationDiscoveryRule,
    McpCacheScopeRule,
    McpDiscoveryTargetRule,
    McpIssuerIdentificationRule,
    McpRegistryEntryRule,
    McpScopeBreadthRule,
    McpSessionBindingRule,
    McpTaskIdentityRule,
    McpTokenAudienceRule,
    McpUnauthenticatedAccessRule,
)

pytestmark = pytest.mark.usefixtures(refuse_name_lookups.__name__)

RULES: tuple[Rule, ...] = (
    McpAuthorizationDiscoveryRule(),
    McpCacheScopeRule(),
    McpDiscoveryTargetRule(),
    McpIssuerIdentificationRule(),
    McpRegistryEntryRule(),
    McpScopeBreadthRule(),
    McpSessionBindingRule(),
    McpTaskIdentityRule(),
    McpTokenAudienceRule(),
    McpUnauthenticatedAccessRule(),
)


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.meta.id)
def test_the_rule_classifies_a_sample_of_every_demanded_outcome(rule: Rule) -> None:
    verified = verify_rule(rule, RuleContext())

    assert verified.is_proven, verified
    passed = {r.expected for r in verified.results if r.verdict is FixtureVerdict.PASSED}
    assert set(DEMANDED_OUTCOMES) <= passed


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.meta.id)
def test_no_sample_spends_more_than_the_rule_declares(rule: Rule) -> None:
    declared = rule.estimated_requests
    assert declared is not None
    for fixture in rule.fixtures():
        target = fixture.target
        if not isinstance(target, McpServerTarget):
            pytest.fail(f"{fixture.name} is not an MCP server")
        with suppress(NotOffered):
            list(rule.run(target, RuleContext()))
        assert target.usage().requests <= declared, fixture.name
