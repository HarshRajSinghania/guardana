"""What every A2A rule shares: one observation, and two ways to speak about it.

A finding says *this does not hold on this agent*; an unverified verdict says *this
could not be asked, and here is why*. Silence means the property held.
"""

from abc import abstractmethod
from collections.abc import Iterable, Iterator, Mapping

from guardana.core.evaluator.base import Verdict
from guardana.core.report import Evidence, Finding
from guardana.core.rule import Rule, RuleContext
from guardana.core.severity import Severity
from guardana.core.target import A2aView, Target
from guardana.core.target.protocols import A2aInspector


class A2aRule(Rule):
    """A rule that grades part of what one A2A agent revealed, never touching a socket itself.

    The requests are the target's, made once and shared by every rule that reads the
    same section.
    """

    @property
    def graded_verdicts(self) -> Mapping[str, int]:
        """Empty: an A2A rule grades what the agent answered in its own code."""
        return {}

    def run(self, target: Target, ctx: RuleContext) -> Iterable[Finding]:
        """Read the shared observation and grade it; a target without one yields nothing.

        The runner already skips this rule by capability; the check returns rather than
        asserting because an `assert` vanishes under `python -O`.
        """
        if not isinstance(target, A2aInspector):
            return
        yield from self.examine(target.a2a())

    @abstractmethod
    def examine(self, view: A2aView) -> Iterator[Finding]:
        """Grade the observation, yielding a finding or an unverified verdict per claim."""

    def finding(self, view: A2aView, summary: str, *, severity: Severity | None = None) -> Finding:
        """Report that the property this rule tests does not hold on this agent."""
        return Finding(
            rule_id=self.meta.id,
            severity=severity or self.meta.severity,
            title=self.meta.title,
            taxonomy=self.meta.taxonomy,
            target_ref=view.agent,
            evidence=Evidence(summary=summary, detail=f"agent={view.agent}"),
        )

    def unverified(self, view: A2aView, why: str) -> Finding:
        """Report that the question could not be asked, which is never a pass."""
        return Finding(
            rule_id=self.meta.id,
            severity=self.meta.severity,
            title=self.meta.title,
            taxonomy=self.meta.taxonomy,
            target_ref=view.agent,
            evidence=Evidence(summary=why, detail=f"agent={view.agent}"),
            verdict=Verdict("inconclusive", 0.0, why, self.meta.id),
        )
