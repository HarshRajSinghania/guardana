from collections.abc import Iterable, Iterator

from guardana.core.report import Finding
from guardana.core.rule import RuleMeta
from guardana.core.rule.fixture import FixtureOutcome, RuleFixture, materialise
from guardana.core.safety import Detection
from guardana.core.severity import Severity
from guardana.core.target import Capability, TargetKind
from guardana.core.taxonomy import OWASP_ASI03_2026, OWASP_ASI07_2026, OWASP_LLM03_2026
from guardana.core.trace import AgentRef, Delegation, Handoff, Span, SpanKind, Trace
from guardana.rules.trace import _samples
from guardana.rules.trace._base import TraceRule


class HandoffAuthorityExpansionRule(TraceRule):
    """An agent used more authority after a handoff than the handoff carried to it.

    The trust boundary in a multi-agent system is the handoff, and what makes it a
    boundary is that the receiving agent treats what arrives as its own task. So the
    scopes that cross are a ceiling: an agent that received `orders:read` and then
    delegates `payments:write` gained privilege by being handed work, which is the
    inter-agent half of the escalation `consent_scope_exceeded` grades for a client.

    This is the check `Span.agent` exists for. A handoff says *B received the work*;
    without an actor on the later spans, nothing in the model says B ever did
    anything, so what B went on to use is unattributable and the rule says so rather
    than guessing.
    """

    meta = RuleMeta(
        id="guardana.trace.handoff_authority_expansion",
        title="An agent exercised more authority than the handoff carried to it",
        severity=Severity.HIGH,
        target_kind=TargetKind.TRACE,
        taxonomy=(OWASP_ASI07_2026, OWASP_ASI03_2026, OWASP_LLM03_2026),
        required_capabilities=frozenset(
            {Capability.READ_TRACE, Capability.READ_HANDOFFS, Capability.READ_DELEGATION}
        ),
        detection=Detection.INVARIANT,
    )

    claim = "whether an agent gained authority across a handoff is not established"

    def fixtures(self) -> Iterable[RuleFixture]:
        """Sample a receiver exceeding the handoff, one within it, and a handoff silent on scope."""
        return materialise(
            (
                _samples.sample(
                    "a writer handed read access to documents, then writing to the CRM",
                    FixtureOutcome.FINDING,
                    lambda: _samples.target(_handoff(("docs:read",)), _writer("crm:write")),
                ),
                _samples.sample(
                    "a writer handed read access to documents, then reading documents",
                    FixtureOutcome.CLEAN,
                    lambda: _samples.target(_handoff(("docs:read",)), _writer("docs:read")),
                ),
                _samples.sample(
                    "a handoff that does not record which scopes crossed",
                    FixtureOutcome.INCONCLUSIVE,
                    lambda: _samples.target(_handoff(None), _writer("docs:read")),
                ),
            )
        )

    def examine(self, trace: Trace) -> Iterator[Finding]:
        """Compare what crossed each handoff against what the receiving agent then used.

        Four ways this declines, and each is a different unknown. A handoff whose
        `carried_scopes` is `None` did not record what crossed, which is not a record
        that nothing did. A trace whose spans carry no actor cannot attribute later
        work to the receiver at all — the common shape of an OpenTelemetry export that
        never set `gen_ai.agent.name`. A receiver's delegation whose `scopes` is `None`
        did not record what it used. And a receiver that performed no recorded
        delegation used no authority this build can see, which is silence rather than a
        pass only because there is genuinely nothing to compare.
        """
        handoffs = [s for s in trace.spans if s.handoff is not None]
        if not handoffs:
            return
        if not any(s.agent is not None for s in trace.spans):
            yield self.unverified(
                trace,
                f"this trace records {len(handoffs)} handoff(s) but no span says which agent "
                f"performed it, so what a receiving agent did with the work cannot be "
                f"attributed to it and {self.claim}",
            )
            return
        silent = [s for s in handoffs if s.handoff is not None and s.handoff.carried_scopes is None]
        if silent:
            yield self.unverified(
                trace,
                f"{len(silent)} handoff(s) do not record which scopes crossed, so {self.claim} "
                f"for them — an unrecorded handover of authority is not a handover of none",
            )
        unattributed = 0
        for span in handoffs:
            if span.handoff is None or span.handoff.carried_scopes is None:
                continue
            if not any(s.agent is not None for s in trace.after(span.span_id)):
                # A trace can name the actor on its handoffs and on nothing after them.
                # Staying silent then would read "the receiver stayed inside what it was
                # given" off a trace that never said the receiver did anything.
                unattributed += 1
                continue
            yield from self._after(trace, span)
        if unattributed:
            yield self.unverified(
                trace,
                f"no step recorded after {unattributed} handoff(s) says which agent performed "
                f"it, so what the receiving agent went on to use is not attributable and "
                f"{self.claim} for them",
            )

    def _after(self, trace: Trace, handoff_span: Span) -> Iterator[Finding]:
        """Grade every delegation the receiving agent made once the work reached it.

        A delegation that did not record its scopes may have used any of them, so it
        declines by name rather than counting as one that stayed inside the ceiling.
        """
        handoff = handoff_span.handoff
        if handoff is None or handoff.carried_scopes is None:
            return
        carried = set(handoff.carried_scopes)
        unrecorded: list[str] = []
        for span in trace.after(handoff_span.span_id):
            if span.agent is None or span.agent.name != handoff.to_agent:
                continue
            for hop in span.delegations:
                if hop.scopes is None:
                    unrecorded.append(f"{hop.boundary!r} in span {span.span_id}")
                    continue
                gained = sorted(set(hop.scopes) - carried)
                if not gained:
                    continue
                yield self.finding(
                    trace,
                    f"{handoff.to_agent} received work from {handoff.from_agent} carrying "
                    f"{', '.join(sorted(carried)) if carried else 'no scopes'}, then exercised "
                    f"{', '.join(gained)} across {hop.boundary!r} in span {span.span_id}",
                    span=span,
                )
        if unrecorded:
            yield self.unverified(
                trace,
                f"{handoff.to_agent} received work from {handoff.from_agent} and then "
                f"delegated across {'; '.join(unrecorded)} without recording which scopes it "
                f"used, so {self.claim} for those hops",
            )


def _handoff(carried: tuple[str, ...] | None) -> Span:
    """Build the researcher handing work to the writer with `carried`, or unsaid."""
    return Span(
        span_id="h1",
        kind=SpanKind.HANDOFF,
        name="handoff",
        agent=AgentRef(name="researcher"),
        handoff=Handoff(from_agent="researcher", to_agent="writer", carried_scopes=carried),
    )


def _writer(scope: str) -> Span:
    """Build the writer, after the handoff, delegating with `scope`."""
    return Span(
        span_id="s2",
        kind=SpanKind.TOOL_EXECUTION,
        name="delegate",
        agent=AgentRef(name="writer"),
        delegations=(Delegation(actor="writer", boundary="writer->service", scopes=(scope,)),),
    )
