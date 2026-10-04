from collections.abc import Iterable, Iterator

from guardana.core.report import Finding
from guardana.core.rule import RuleMeta
from guardana.core.rule.fixture import FixtureOutcome, RuleFixture, materialise
from guardana.core.safety import Detection
from guardana.core.severity import Severity
from guardana.core.target import Capability, TargetKind
from guardana.core.taxonomy import OWASP_ASI03_2026, OWASP_LLM03_2026, OWASP_MCP01_2025
from guardana.core.trace import (
    CredentialKind,
    CredentialRef,
    Delegation,
    Span,
    SpanKind,
    Trace,
    TraceTruncation,
)
from guardana.rules.trace import _samples
from guardana.rules.trace._base import TraceRule

_HOPS_NEEDED_TO_COMPARE = 2
"""One hop cannot cross two boundaries, so a single credentialed hop is not evidence."""


class CredentialPassthroughRule(TraceRule):
    """One credential crossing two trust boundaries — the confused deputy, proven.

    The token a service receives and the token it presents upstream must be different
    tokens. When they are the same one, the upstream service reads the caller's
    credential as its own client's, which is what the MCP specification forbids as
    token passthrough and what OAuth calls a confused deputy.

    Step two deferred this check with a stated reason: it happens between a server and
    a service Guardana is not talking to, and no sequence of client requests makes it
    observable. In a trace it *is* observable, which is the point of the trace work —
    and it needs exactly the field a naive schema would have flattened, because a
    model with one credential per call cannot say that two hops carried the same one.
    """

    meta = RuleMeta(
        id="guardana.trace.credential_passthrough",
        title="A credential was presented across two different trust boundaries",
        severity=Severity.HIGH,
        target_kind=TargetKind.TRACE,
        taxonomy=(OWASP_MCP01_2025, OWASP_ASI03_2026, OWASP_LLM03_2026),
        required_capabilities=frozenset({Capability.READ_TRACE, Capability.READ_DELEGATION}),
        detection=Detection.INVARIANT,
    )

    claim = "whether one credential crossed two boundaries is not established"

    def fixtures(self) -> Iterable[RuleFixture]:
        """Sample a forwarded token, an exchanged one, and a trace cut after the first hop."""
        return materialise(
            (
                _samples.sample(
                    "a gateway presenting its caller's token to the service behind it",
                    FixtureOutcome.FINDING,
                    lambda: _samples.target(_hop("s1", "caller"), _onward("s2", "caller")),
                ),
                _samples.sample(
                    "a gateway exchanging its caller's token before calling onward",
                    FixtureOutcome.CLEAN,
                    lambda: _samples.target(_hop("s1", "caller"), _onward("s2", "exchanged")),
                ),
                _samples.sample(
                    "a trace whose producer stopped writing after the first credentialed hop",
                    FixtureOutcome.INCONCLUSIVE,
                    lambda: _samples.target(
                        _hop("s1", "caller"), truncated=TraceTruncation.UNTERMINATED
                    ),
                    "the onward hop that would carry the same token may be in the missing part",
                ),
            )
        )

    def examine(self, trace: Trace) -> Iterator[Finding]:
        """Compare every credentialed hop against every other, by digest.

        Only digests are compared, never values — `CredentialRef` has no field for a
        value. A hop whose credential nobody digested is not evidence of reuse and is
        skipped, which is the fail-closed direction: the alternative turns every
        two-hop trace into a finding.
        """
        hops: list[tuple[str, Delegation]] = [
            (span.span_id, delegation)
            for span in trace.spans
            for delegation in span.credentialed_delegations()
        ]
        if len(hops) < _HOPS_NEEDED_TO_COMPARE:
            return
        reported: set[tuple[str, ...]] = set()
        for index, (span_id, hop) in enumerate(hops):
            for other_span, other in hops[index + 1 :]:
                if not self._is_passthrough(hop, other):
                    continue
                key = (self._digest(hop), *sorted((hop.boundary, other.boundary)))
                if key in reported:
                    continue
                reported.add(key)
                yield self.finding(
                    trace,
                    f"the same credential ({hop.credential.kind if hop.credential else '?'}, "
                    f"digest {self._digest(hop)}) was presented across two trust boundaries: "
                    f"{hop.boundary!r} by {hop.actor} in span {span_id}, then "
                    f"{other.boundary!r} by {other.actor} in span {other_span} — the upstream "
                    f"service reads the caller's credential as its own client's",
                    span=trace.span(other_span),
                )

    def _is_passthrough(self, hop: Delegation, other: Delegation) -> bool:
        """Whether these two hops are the same credential across different boundaries.

        Different boundaries is the whole condition. The same credential used twice
        *within* one boundary is one client talking to one service twice, which is
        ordinary; carrying it across is the defect.
        """
        return (
            hop.credential is not None
            and other.credential is not None
            and hop.credential.is_same_as(other.credential)
            and hop.boundary != other.boundary
        )

    def _digest(self, hop: Delegation) -> str:
        return hop.credential.digest or "" if hop.credential is not None else ""


def _hop(span_id: str, token: str) -> Span:
    """Build the agent calling its gateway with a token whose digest names `token`."""
    return _delegating(span_id, "agent", "agent->gateway", token)


def _onward(span_id: str, token: str) -> Span:
    """Build the gateway calling billing with a token whose digest names `token`."""
    return _delegating(span_id, "gateway", "gateway->billing", token)


def _delegating(span_id: str, actor: str, boundary: str, token: str) -> Span:
    credential = CredentialRef(kind=CredentialKind.BEARER, digest=f"sha256:{token}")
    return Span(
        span_id=span_id,
        kind=SpanKind.TOOL_EXECUTION,
        name=boundary,
        delegations=(Delegation(actor=actor, boundary=boundary, credential=credential),),
    )
