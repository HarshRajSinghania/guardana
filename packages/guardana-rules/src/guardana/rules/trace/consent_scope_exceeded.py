from collections.abc import Iterable, Iterator

from guardana.core.report import Finding
from guardana.core.rule import RuleMeta
from guardana.core.rule.fixture import FixtureOutcome, RuleFixture, materialise
from guardana.core.safety import Detection
from guardana.core.severity import Severity
from guardana.core.target import Capability, TargetKind
from guardana.core.taxonomy import OWASP_ASI03_2026, OWASP_LLM03_2026, OWASP_MCP02_2025
from guardana.core.trace import Consent, Delegation, Span, SpanKind, Trace
from guardana.rules.trace import _samples
from guardana.rules.trace._base import TraceRule


class ConsentScopeExceededRule(TraceRule):
    """A hop exercised a scope the client was never granted.

    Consent is recorded **per client**, not per user, and that is the distinction the
    MCP work paid for: the confused deputy works because a decision recorded against a
    user gets read as a decision about a client. A model keyed on the subject cannot
    express the bug, so this reads the grant by client and the exercise by hop.

    A scope in use with no matching grant is privilege nobody agreed to — the escalation
    OWASP calls scope creep, seen from the inside rather than inferred from what a
    server advertises.
    """

    meta = RuleMeta(
        id="guardana.trace.consent_scope_exceeded",
        title="A scope was exercised that no consent record granted",
        severity=Severity.HIGH,
        target_kind=TargetKind.TRACE,
        taxonomy=(OWASP_MCP02_2025, OWASP_ASI03_2026, OWASP_LLM03_2026),
        required_capabilities=frozenset({Capability.READ_TRACE, Capability.READ_CONSENT}),
        detection=Detection.INVARIANT,
    )

    claim = "whether an ungranted scope was exercised is not established"

    def fixtures(self) -> Iterable[RuleFixture]:
        """Sample a scope beyond the grant, one within it, and a hop that kept its scopes quiet."""
        return materialise(
            (
                _samples.sample(
                    "a client granted read access calling with read and write",
                    FixtureOutcome.FINDING,
                    lambda: _samples.target(_granted(), _used(("docs:read", "docs:write"))),
                ),
                _samples.sample(
                    "a client calling with the one scope it was granted",
                    FixtureOutcome.CLEAN,
                    lambda: _samples.target(_granted(), _used(("docs:read",))),
                ),
                _samples.sample(
                    "a client whose call does not record which scopes it used",
                    FixtureOutcome.INCONCLUSIVE,
                    lambda: _samples.target(_granted(), _used(None)),
                ),
            )
        )

    def examine(self, trace: Trace) -> Iterator[Finding]:
        """Compare exercised scopes against granted ones, declining where either is silent.

        A consent that says nothing about its scopes makes "this scope was never granted"
        unprovable for that client, and a hop that says nothing about the scopes it used
        makes "nothing ungranted was used" unprovable for that hop; the rule declines by
        name for both. A grant of `()` is different and is believed, and so is the
        absence of any consent for a client in a trace that records consent: either
        way the client was granted nothing, and a hop exercising a scope is a finding.
        """
        granted, silent = self._grants(trace)
        if silent:
            yield self.unverified(
                trace,
                f"the consent record(s) for {', '.join(sorted(silent))} do not say which "
                f"scopes were granted, so {self.claim} for them",
            )
        unrecorded: list[str] = []
        for span in trace.spans:
            for hop in span.delegations:
                if hop.actor in silent:
                    continue
                if hop.scopes is None:
                    unrecorded.append(f"{hop.actor} across {hop.boundary!r} in span {span.span_id}")
                    continue
                allowed = granted.get(hop.actor)
                exceeded = sorted(set(hop.scopes) - (allowed or set()))
                if not exceeded:
                    continue
                if allowed is None:
                    grant = "no consent is recorded for that client"
                else:
                    grant = (
                        f"the consent recorded for that client grants "
                        f"{', '.join(sorted(allowed)) if allowed else 'nothing'}"
                    )
                yield self.finding(
                    trace,
                    f"{hop.actor} exercised scope(s) {', '.join(exceeded)} across "
                    f"{hop.boundary!r} in span {span.span_id}, and {grant}",
                    span=span,
                )
        if unrecorded:
            yield self.unverified(
                trace,
                f"the delegation(s) by {'; '.join(unrecorded)} do not say which scopes were "
                f"used, so {self.claim} for them",
            )

    def _grants(self, trace: Trace) -> tuple[dict[str, set[str]], set[str]]:
        """Collect what each client was granted, and which clients' grants stayed silent.

        A refused consent contributes no scopes but still registers the client, so a hop
        by a client whose only consent was a refusal is compared against nothing —
        which is what makes the refusal mean something. One silent record poisons that
        client for the whole trace, because it is enough to make the absence unprovable.
        """
        granted: dict[str, set[str]] = {}
        silent: set[str] = set()
        for span in trace.spans:
            for consent in span.consents:
                granted.setdefault(consent.client, set())
                if not consent.granted:
                    continue
                if consent.scopes is None:
                    silent.add(consent.client)
                else:
                    granted[consent.client].update(consent.scopes)
        return granted, silent


def _granted() -> Span:
    """Build the consent screen granting the client `docs:read` and nothing else."""
    return Span(
        span_id="s1",
        kind=SpanKind.TOOL_EXECUTION,
        name="consent",
        consents=(Consent(client="client-1", granted=True, scopes=("docs:read",)),),
    )


def _used(scopes: tuple[str, ...] | None) -> Span:
    """Build the client calling the documents service with `scopes`, or without saying which."""
    return Span(
        span_id="s2",
        kind=SpanKind.TOOL_EXECUTION,
        name="docs",
        delegations=(Delegation(actor="client-1", boundary="client->docs", scopes=scopes),),
    )
