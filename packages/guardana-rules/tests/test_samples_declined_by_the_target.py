"""An inconclusive sample the target declines, not the rule, says so and stays small."""

from pathlib import Path

import pytest
from guardana.core.rule import Rule, RuleContext
from guardana.core.rule.fixture import FixtureOutcome, RuleFixture
from guardana.core.target import FileReader
from guardana.rules import provide_rules

_SMALL = 64 * 1024


def _declined_by_the_target(rule: Rule, fixture: RuleFixture) -> bool:
    """Whether the sample declines only because its target left a file unread."""
    target = fixture.target
    if fixture.outcome is not FixtureOutcome.INCONCLUSIVE or not isinstance(target, FileReader):
        return False
    ctx = RuleContext()
    reported = list((fixture.rule or rule).run(target, ctx))
    return not reported and not ctx.shortfalls() and bool(target.unread_sources())


_SAMPLES = [
    (rule, fixture)
    for rule in provide_rules()
    for fixture in rule.fixtures()
    if _declined_by_the_target(rule, fixture)
]


def test_the_samples_declined_by_the_target_are_found() -> None:
    assert {rule.meta.id for rule, _ in _SAMPLES} >= {
        "guardana.supply_chain.code_execution",
        "guardana.training.dataset_integrity",
    }


@pytest.mark.parametrize(
    ("rule", "fixture"),
    _SAMPLES,
    ids=[f"{rule.meta.id}:{fixture.name}" for rule, fixture in _SAMPLES],
)
def test_the_sample_says_the_decline_is_the_target_s(rule: Rule, fixture: RuleFixture) -> None:
    assert "target" in fixture.note, rule.meta.id


@pytest.mark.parametrize(
    ("rule", "fixture"),
    _SAMPLES,
    ids=[f"{rule.meta.id}:{fixture.name}" for rule, fixture in _SAMPLES],
)
def test_the_sample_writes_no_large_file(rule: Rule, fixture: RuleFixture) -> None:
    root = Path(fixture.target.ref)
    written = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())

    assert written <= _SMALL, rule.meta.id
