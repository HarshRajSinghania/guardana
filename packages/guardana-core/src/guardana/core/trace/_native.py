"""The dialect Guardana defines: OpenTelemetry's message shape plus the named extensions.

Strict about keys at every level, unlike the OpenTelemetry reader, and
`reject_unknown_keys` carries the reason. Messages and parts reach the shared
OpenTelemetry helpers only after their keys are checked here, so that dialect stays
tolerant. This is also the only dialect that can *declare* what it records, which is
why converting an OTel export into it is how an operator adds the authorization
dimensions their framework does not emit.
"""

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, TypeVar

from guardana.core.trace._parse import (
    TraceLoadError,
    mapping_of,
    message_from,
    optional_bool,
    optional_float,
    optional_int,
    optional_text,
    optional_time,
    parts_from,
    reject_unknown_keys,
    string_map,
    text_of,
)
from guardana.core.trace.agent import AgentRef
from guardana.core.trace.authorization import (
    Approval,
    ApprovalOutcome,
    ApproverKind,
    Consent,
    PolicyDecision,
    PolicyOutcome,
)
from guardana.core.trace.content import ContentPart
from guardana.core.trace.effect import EffectStatus, SideEffect, SinkKind
from guardana.core.trace.handoff import Handoff
from guardana.core.trace.identity import (
    CredentialKind,
    CredentialRef,
    Delegation,
    Identity,
    SessionRef,
)
from guardana.core.trace.memory import MemoryAction, MemoryOperation
from guardana.core.trace.message import Message
from guardana.core.trace.model import TRACE_SCHEMA_VERSION, Dimension, TraceTruncation
from guardana.core.trace.retrieval import Retrieval, RetrievedDocument
from guardana.core.trace.span import ModelCall, Span, SpanKind
from guardana.core.trace.tool import ToolDeclaration, ToolExecution, ToolStatus

VERSION_KEY = "guardana_trace"
"""The key that makes a native trace identifiable and versioned in one field."""

_E = TypeVar("_E", bound=StrEnum)

FOOTER_KEY = "guardana_trace_end"
"""The key that makes the last record a sign-off rather than a span.

A file being appended to by a live agent cannot go back and amend its header, so
"this session ended" has to arrive at the end. It is opt-in from the header, because
reading every footerless file as truncated would turn every trace written before this
existed into a decline.
"""

_HEADER_KEYS = frozenset(
    {VERSION_KEY, "trace_id", "producer", "instrumented", "truncated", "attributes", "terminated"}
)
_FOOTER_KEYS = frozenset({FOOTER_KEY, "spans"})
_SPAN_KEYS = frozenset(
    {
        "span_id",
        "kind",
        "name",
        "agent",
        "parent_span_id",
        "started_at",
        "ended_at",
        "error",
        "model",
        "messages",
        "system_instructions",
        "tool_offers",
        "tool",
        "retrieval",
        "memory",
        "handoff",
        "conversation_id",
        "identity",
        "delegations",
        "consents",
        "policy_decisions",
        "approvals",
        "effects",
    }
)
OBJECT_KEYS: Mapping[str, frozenset[str]] = {
    "header": _HEADER_KEYS,
    "header.producer": frozenset({"name", "version", "recorded_at"}),
    "footer": _FOOTER_KEYS,
    "span": _SPAN_KEYS,
    "span.agent": frozenset({"name", "id"}),
    "span.model": frozenset(
        {
            "provider",
            "request_model",
            "response_model",
            "input_tokens",
            "output_tokens",
            "finish_reasons",
        }
    ),
    "span.tool_offers[]": frozenset({"name", "description", "schema", "tool_type"}),
    "span.tool": frozenset(
        {"name", "call_id", "arguments", "result", "status", "mutates", "server"}
    ),
    "span.retrieval": frozenset({"query", "source", "tenant", "documents"}),
    "span.retrieval.documents[]": frozenset(
        {"id", "content", "source", "tenant", "score", "metadata"}
    ),
    "span.memory": frozenset({"action", "store", "key", "content", "origin_span_id"}),
    "span.handoff": frozenset({"from_agent", "to_agent", "payload", "carried_scopes"}),
    "span.identity": frozenset({"actor", "credential", "claimed_resource", "session"}),
    "span.delegations[]": frozenset({"actor", "boundary", "on_behalf_of", "credential", "scopes"}),
    "span.consents[]": frozenset({"client", "granted", "scopes", "subject", "recorded_at"}),
    "span.policy_decisions[]": frozenset({"outcome", "action", "policy", "rationale"}),
    "span.approvals[]": frozenset(
        {"action", "outcome", "approver", "approver_kind", "requested_at", "decided_at"}
    ),
    "span.effects[]": frozenset({"sink", "action", "target", "status", "reversible", "detail"}),
    "session": frozenset({"id", "protocol"}),
    "credential": frozenset({"kind", "digest", "value", "audience", "issuer", "subject", "scopes"}),
    "message": frozenset({"role", "parts", "finish_reason"}),
    "part": frozenset(
        {
            "type",
            "content",
            "id",
            "name",
            "arguments",
            "response",
            "media_type",
            "mime_type",
            "uri",
            "url",
            "digest",
            "size_bytes",
            "data",
        }
    ),
}
"""The keys each object of this dialect allows, by its place in the published schema.

One table rather than a set beside each parser, so a test can hold it equal to
`schemas/trace-v3.schema.json` and the reader cannot accept what the schema refuses.
"""


class NativeHeader:
    """What the first line of a native trace declares about the whole file."""

    def __init__(self, raw: Mapping[str, Any]) -> None:
        """Read and validate the header, refusing a version this build cannot read."""
        reject_unknown_keys(raw, _HEADER_KEYS, "trace header")
        self.version = version_of(raw)
        self.trace_id = text_of(raw, "trace_id", "trace header")
        producer = mapping_of(raw.get("producer", {}), "trace header.producer")
        _closed(producer, "header.producer", "trace header.producer")
        self.producer = optional_text(producer, "name") or "unknown"
        self.producer_version = optional_text(producer, "version")
        self.recorded_at = optional_time(producer, "recorded_at")
        self.instrumented = _dimensions(raw)
        self.truncated = _truncation(raw)
        self.attributes = _map(raw, "attributes", "trace header")
        self.terminated = optional_bool(raw, "terminated") is True
        """Whether this producer promised a footer, so its absence means truncation."""


class NativeFooter:
    """The last record of a file whose header promised one.

    It carries a count rather than only a full stop. A footer saying nothing but "I
    finished" would certify a file whose middle a log shipper had eaten — a fresh
    false green produced by the mechanism installed to remove one.
    """

    def __init__(self, raw: Mapping[str, Any], declared_version: int) -> None:
        """Read the footer, refusing one that does not describe this file."""
        reject_unknown_keys(raw, _FOOTER_KEYS, "trace footer")
        declared = raw.get(FOOTER_KEY)
        if declared != declared_version:
            raise TraceLoadError(
                f"the trace footer declares {FOOTER_KEY} {declared!r} while the header declares "
                f"schema version {declared_version} — one file cannot be two versions"
            )
        spans = raw.get("spans")
        if isinstance(spans, bool) or not isinstance(spans, int) or spans < 0:
            raise TraceLoadError(
                f"the trace footer must carry 'spans' as the number of span records the "
                f"producer wrote, and carries {spans!r} — without it the footer is a full "
                f"stop rather than a claim that nothing went missing"
            )
        self.spans = spans


def version_of(raw: Mapping[str, Any]) -> int:
    """Read the schema version, refusing both an absent one and one from the future.

    A missing version is an error rather than a default of 1: guessing is how an
    unversioned format acquires a version in name only. A *newer* version is refused
    because reading it as this one would drop the fields this build does not know and
    grade what was left — a partial trace reported as a whole one.
    """
    version = raw.get(VERSION_KEY)
    if isinstance(version, bool) or not isinstance(version, int):
        raise TraceLoadError(
            f"a native trace must open with a header carrying {VERSION_KEY!r} as an integer "
            f"(pass --dialect otel for an OpenTelemetry export)"
        )
    if version > TRACE_SCHEMA_VERSION:
        raise TraceLoadError(
            f"this trace is schema version {version} and this build reads up to "
            f"{TRACE_SCHEMA_VERSION} — reading it anyway would drop the fields this build "
            f"does not know and grade what was left. Upgrade Guardana."
        )
    if version < 1:
        raise TraceLoadError(f"{VERSION_KEY} must be 1 or greater, got {version}")
    return version


def migrate_header(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """Carry a header forward to the current schema, inventing nothing.

    Returns the migrated mapping, and the caller parses *that* — the v1 version of
    this took the already-parsed header's version and threw its own result away, so
    a migration that needed to change a field could not have. A seam whose output
    nothing consumes is a seam nobody would notice was broken.

    Two steps so far, and neither touches the header: v2 added a per-span field and v3
    added a per-approval one, so a header carries forward unchanged apart from the
    version it now declares. The spans need no step because an added field is absent in
    the older file and absent is what it means — except `approver`, where the older
    spelling carries a meaning, and `_approver` reads it in both files rather than
    rewriting one into the other.
    """
    version = version_of(raw)
    migrated = dict(raw)
    for step in range(version, TRACE_SCHEMA_VERSION):
        migrate = _MIGRATIONS.get(step)
        if migrate is None:
            raise TraceLoadError(f"no migration path from trace schema version {step}")
        migrated = migrate(migrated)
        migrated[VERSION_KEY] = step + 1
    return migrated


def _migrate_1_to_2(raw: dict[str, Any]) -> dict[str, Any]:
    """v2 added `Span.agent`. The header is unchanged; every span gains an absent field."""
    return raw


def _migrate_2_to_3(raw: dict[str, Any]) -> dict[str, Any]:
    """v3 added `Approval.approver_kind`, which is per-approval. The header is unchanged."""
    return raw


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _migrate_1_to_2,
    2: _migrate_2_to_3,
}


def _dimensions(raw: Mapping[str, Any]) -> frozenset[Dimension]:
    """Read the declared dimensions, refusing a name this build does not know.

    Refused rather than ignored: a producer that declares `aprovals` believes it is
    recording approvals, and silently reading that as "does not record approvals"
    would turn their typo into missing coverage nobody is told about.
    """
    declared = _strings(raw, "instrumented", "trace header") or ()
    known = {str(d): d for d in Dimension}
    unknown = sorted(set(declared) - set(known))
    if unknown:
        raise TraceLoadError(
            f"trace header.instrumented names unknown dimension(s) {', '.join(unknown)}; "
            f"known dimensions are {', '.join(sorted(known))}"
        )
    return frozenset(known[name] for name in declared)


def _truncation(raw: Mapping[str, Any]) -> TraceTruncation | None:
    value = optional_text(raw, "truncated")
    if value is None:
        return None
    try:
        return TraceTruncation(value)
    except ValueError as exc:
        raise TraceLoadError(f"trace header.truncated is not a known reason: {value}") from exc


def span_from(raw: Mapping[str, Any]) -> Span:
    """Read one native span record, refusing an unknown key at any level of it."""
    reject_unknown_keys(raw, _SPAN_KEYS, "span")
    span_id = text_of(raw, "span_id", "span")
    try:
        return _span(raw, span_id)
    except TraceLoadError as exc:
        raise TraceLoadError(f"span {span_id!r}: {exc}") from exc


def _span(raw: Mapping[str, Any], span_id: str) -> Span:
    return Span(
        span_id=span_id,
        kind=_enum(raw, "kind", SpanKind, SpanKind.OTHER),
        name=optional_text(raw, "name") or span_id,
        agent=_agent(raw.get("agent")),
        parent_span_id=optional_text(raw, "parent_span_id"),
        started_at=optional_time(raw, "started_at"),
        ended_at=optional_time(raw, "ended_at"),
        error=optional_text(raw, "error"),
        model=_model(raw.get("model")),
        messages=tuple(_message(m) for m in _items(raw.get("messages"), "messages")),
        system_instructions=_parts(raw.get("system_instructions"), "system_instructions"),
        tool_offers=tuple(_offer(o) for o in _items(raw.get("tool_offers"), "tool_offers")),
        tool=_tool(raw.get("tool")),
        retrieval=_retrieval(raw.get("retrieval")),
        memory=_memory(raw.get("memory")),
        handoff=_handoff(raw.get("handoff")),
        conversation_id=optional_text(raw, "conversation_id"),
        identity=_identity(raw.get("identity")),
        delegations=tuple(_delegation(d) for d in _items(raw.get("delegations"), "delegations")),
        consents=tuple(_consent(c) for c in _items(raw.get("consents"), "consents")),
        policy_decisions=tuple(
            _policy(p) for p in _items(raw.get("policy_decisions"), "policy_decisions")
        ),
        approvals=tuple(_approval(a) for a in _items(raw.get("approvals"), "approvals")),
        effects=tuple(_effect(e) for e in _items(raw.get("effects"), "effects")),
    )


def _closed(raw: Mapping[str, Any], location: str, what: str) -> None:
    """Refuse a key the schema object at `location` does not define."""
    reject_unknown_keys(raw, OBJECT_KEYS[location], what)


def _object(raw: object, what: str) -> dict[str, Any] | None:
    """Read an object the schema defines, None when absent; refuse any other value.

    The shared parsers read a string or a number in its place as an empty record or as
    text, which is a record the producer never wrote.
    """
    return None if raw is None else mapping_of(raw, what)


def _items(raw: object, what: str) -> list[dict[str, Any]]:
    """Read a list of objects the schema defines, empty when absent; refuse anything else."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TraceLoadError(f"{what} must be a JSON array")
    return [mapping_of(item, f"an item of {what}") for item in raw]


def _strings(raw: Mapping[str, Any], key: str, what: str) -> tuple[str, ...] | None:
    """Read a list of strings the schema defines, None when absent; refuse anything else.

    Absence and an empty list stay different facts, which a scope list needs.
    """
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TraceLoadError(f"{what}.{key} must be a JSON array of strings")
    return tuple(value)


def _map(raw: Mapping[str, Any], key: str, what: str) -> dict[str, str]:
    """Read a string map the schema defines, empty when absent; refuse a value that is not one."""
    _object(raw.get(key), f"{what}.{key}")
    return string_map(raw, key)


def _parts(raw: object, what: str) -> tuple[ContentPart, ...]:
    """Check every part's keys and `type` here, then read them with the shared OTel parser.

    The shared parser reads only the keys it knows, which is right for OpenTelemetry
    and the fail-open here: a part written `{"type": "text", "text": ...}` would carry
    no text and grade as an empty message.
    """
    parts = _items(raw, f"the parts of {what}")
    for part in parts:
        _closed(part, "part", f"a part in {what}")
        if not isinstance(part.get("type"), str):
            raise TraceLoadError(f"a part in {what} must name its `type` as a string")
    return parts_from(parts)


def _message(raw: dict[str, Any]) -> Message:
    """Check a message's keys and its parts', then read it with the shared OTel parser.

    Only `parts` is a native message's list: the shared parser's fallback to
    `content` serves OpenTelemetry producers and would let a native typo through.
    """
    _closed(raw, "message", "a message")
    _parts(raw.get("parts"), "a message")
    return message_from(raw)


def _enum(raw: Mapping[str, Any], key: str, enum: type[_E], fallback: _E) -> _E:
    """Read an enum member, falling back where the model has an honest `other`.

    Falling back rather than refusing, because every enum used here has a member for
    "this build does not recognise it" and keeping the record is the point. The
    dimensions list is the exception and refuses, because there is no honest fallback
    for a dimension somebody believes they declared.
    """
    value = raw.get(key)
    if not isinstance(value, str):
        return fallback
    try:
        return enum(value)
    except ValueError:
        return fallback


def _model(value: object) -> ModelCall | None:
    raw = _object(value, "model")
    if raw is None:
        return None
    _closed(raw, "span.model", "model")
    return ModelCall(
        provider=optional_text(raw, "provider"),
        request_model=optional_text(raw, "request_model"),
        response_model=optional_text(raw, "response_model"),
        input_tokens=optional_int(raw, "input_tokens"),
        output_tokens=optional_int(raw, "output_tokens"),
        finish_reasons=_strings(raw, "finish_reasons", "model") or (),
    )


def _offer(raw: dict[str, Any]) -> ToolDeclaration:
    _closed(raw, "span.tool_offers[]", "a tool offer")
    return ToolDeclaration(
        name=optional_text(raw, "name") or "unknown",
        description=optional_text(raw, "description"),
        schema=optional_text(raw, "schema"),
        tool_type=optional_text(raw, "tool_type"),
    )


def _tool(value: object) -> ToolExecution | None:
    raw = _object(value, "tool")
    if raw is None:
        return None
    _closed(raw, "span.tool", "tool")
    return ToolExecution(
        name=optional_text(raw, "name") or "unknown",
        call_id=optional_text(raw, "call_id"),
        arguments=optional_text(raw, "arguments"),
        result=_parts(raw.get("result"), "a tool result"),
        status=_enum(raw, "status", ToolStatus, ToolStatus.UNKNOWN),
        mutates=optional_bool(raw, "mutates"),
        server=optional_text(raw, "server"),
    )


def _retrieval(value: object) -> Retrieval | None:
    raw = _object(value, "retrieval")
    if raw is None:
        return None
    _closed(raw, "span.retrieval", "retrieval")
    return Retrieval(
        query=optional_text(raw, "query"),
        source=optional_text(raw, "source"),
        tenant=optional_text(raw, "tenant"),
        documents=tuple(_document(d) for d in _items(raw.get("documents"), "retrieval.documents")),
    )


def _document(raw: dict[str, Any]) -> RetrievedDocument:
    _closed(raw, "span.retrieval.documents[]", "a retrieved document")
    return RetrievedDocument(
        id=optional_text(raw, "id") or "unknown",
        content=_parts(raw.get("content"), "a retrieved document"),
        source=optional_text(raw, "source"),
        tenant=optional_text(raw, "tenant"),
        score=optional_float(raw, "score"),
        metadata=_map(raw, "metadata", "a retrieved document"),
    )


def _memory(value: object) -> MemoryOperation | None:
    raw = _object(value, "memory")
    if raw is None:
        return None
    _closed(raw, "span.memory", "memory")
    return MemoryOperation(
        action=_enum(raw, "action", MemoryAction, MemoryAction.READ),
        store=optional_text(raw, "store"),
        key=optional_text(raw, "key"),
        content=_parts(raw.get("content"), "a memory operation"),
        origin_span_id=optional_text(raw, "origin_span_id"),
    )


def _agent(raw: object) -> AgentRef | None:
    """Read which agent performed this step, refusing a record with no name in it.

    A nameless actor is dropped rather than recorded as `"unknown"`: the point of the
    field is to tell two agents apart, and a trace whose every span is performed by
    `unknown` would let a rule compare two different agents and find them equal.
    """
    block = _object(raw, "agent")
    if block is None:
        return None
    _closed(block, "span.agent", "agent")
    name = optional_text(block, "name")
    if name is None:
        return None
    return AgentRef(name=name, id=optional_text(block, "id"))


def _handoff(value: object) -> Handoff | None:
    raw = _object(value, "handoff")
    if raw is None:
        return None
    _closed(raw, "span.handoff", "handoff")
    return Handoff(
        from_agent=optional_text(raw, "from_agent") or "unknown",
        to_agent=optional_text(raw, "to_agent") or "unknown",
        payload=_parts(raw.get("payload"), "a handoff payload"),
        carried_scopes=_strings(raw, "carried_scopes", "handoff"),
    )


def credential_from(raw: object) -> CredentialRef | None:
    """Read a credential reference, digesting a value the trace recorded in the clear.

    A trace that carries the raw token gets it hashed here and nowhere kept, because
    `CredentialRef` has no field to put it in. That is the seam: a producer's
    carelessness stops at the reader rather than travelling into a report.
    """
    block = _object(raw, "credential")
    if block is None:
        return None
    _closed(block, "credential", "credential")
    digest = optional_text(block, "digest")
    value = optional_text(block, "value")
    kind = _enum(block, "kind", CredentialKind, CredentialKind.OTHER)
    if digest is None and value is not None:
        digest = CredentialRef.of_value(value, kind).digest
    return CredentialRef(
        kind=kind,
        digest=digest,
        audience=_strings(block, "audience", "credential") or (),
        issuer=optional_text(block, "issuer"),
        subject=optional_text(block, "subject"),
        scopes=_strings(block, "scopes", "credential"),
    )


def _identity(value: object) -> Identity | None:
    raw = _object(value, "identity")
    if raw is None:
        return None
    _closed(raw, "span.identity", "identity")
    session = raw.get("session")
    return Identity(
        actor=optional_text(raw, "actor"),
        credential=credential_from(raw.get("credential")),
        claimed_resource=optional_text(raw, "claimed_resource"),
        session=_session(session),
    )


def _session(raw: object) -> SessionRef | None:
    if isinstance(raw, str):
        return SessionRef(id=raw)
    block = _object(raw, "identity.session, unless a bare id,")
    if block is None:
        return None
    _closed(block, "session", "identity.session")
    identifier = optional_text(block, "id")
    return (
        SessionRef(id=identifier, protocol=optional_text(block, "protocol"))
        if identifier is not None
        else None
    )


def _delegation(raw: dict[str, Any]) -> Delegation:
    _closed(raw, "span.delegations[]", "a delegation")
    return Delegation(
        actor=optional_text(raw, "actor") or "unknown",
        boundary=optional_text(raw, "boundary") or "unknown",
        on_behalf_of=optional_text(raw, "on_behalf_of"),
        credential=credential_from(raw.get("credential")),
        scopes=_strings(raw, "scopes", "a delegation"),
    )


def _consent(raw: dict[str, Any]) -> Consent:
    _closed(raw, "span.consents[]", "a consent")
    granted = optional_bool(raw, "granted")
    return Consent(
        client=optional_text(raw, "client") or "unknown",
        granted=granted if granted is not None else False,
        scopes=_strings(raw, "scopes", "a consent"),
        subject=optional_text(raw, "subject"),
        recorded_at=optional_time(raw, "recorded_at"),
    )


def _policy(raw: dict[str, Any]) -> PolicyDecision:
    _closed(raw, "span.policy_decisions[]", "a policy decision")
    return PolicyDecision(
        outcome=_enum(raw, "outcome", PolicyOutcome, PolicyOutcome.ERROR),
        action=optional_text(raw, "action") or "unknown",
        policy=optional_text(raw, "policy"),
        rationale=optional_text(raw, "rationale"),
    )


_APPROVER_KINDS = {str(kind): kind for kind in ApproverKind}


def _approver(raw: Mapping[str, Any]) -> tuple[str | None, ApproverKind | None]:
    """Read who granted an approval, and whether they are a person.

    Refused rather than fallen back on, unlike every other enum here, for the reason
    `instrumented` refuses: there is no honest default for "is this human oversight".
    A misspelled `persson` read as an unrecorded kind would quietly turn a contract
    demanding a human into one satisfied by the agent's own gate.

    An older file spells the kind into the name — `human:alice`, the convention
    `docs/usage-contracts.md` has documented since contracts shipped — so that prefix
    is read as the structure it always stood for. An explicit `approver_kind` wins,
    and a name whose prefix names nothing known is just a name.
    """
    approver = optional_text(raw, "approver")
    declared = raw.get("approver_kind")
    if declared is not None:
        if not isinstance(declared, str) or declared not in _APPROVER_KINDS:
            raise TraceLoadError(
                f"an approval's approver_kind is {declared!r}; known kinds are "
                f"{', '.join(sorted(_APPROVER_KINDS))}"
            )
        if approver is None:
            raise TraceLoadError(
                f"an approval records approver_kind {declared!r} and no approver — a claim "
                f"that somebody approved, minus the somebody"
            )
        return approver, _APPROVER_KINDS[declared]
    if approver is None:
        return None, None
    prefix, separator, name = approver.partition(":")
    if separator and name and prefix in _APPROVER_KINDS:
        return name, _APPROVER_KINDS[prefix]
    return approver, None


def _approval(raw: dict[str, Any]) -> Approval:
    _closed(raw, "span.approvals[]", "an approval")
    approver, approver_kind = _approver(raw)
    return Approval(
        action=optional_text(raw, "action") or "unknown",
        outcome=_enum(raw, "outcome", ApprovalOutcome, ApprovalOutcome.UNKNOWN),
        approver=approver,
        approver_kind=approver_kind,
        requested_at=optional_time(raw, "requested_at"),
        decided_at=optional_time(raw, "decided_at"),
    )


def _effect(raw: dict[str, Any]) -> SideEffect:
    _closed(raw, "span.effects[]", "an effect")
    return SideEffect(
        sink=_enum(raw, "sink", SinkKind, SinkKind.OTHER),
        action=optional_text(raw, "action") or "unknown",
        target=optional_text(raw, "target"),
        status=_enum(raw, "status", EffectStatus, EffectStatus.ATTEMPTED),
        reversible=optional_bool(raw, "reversible"),
        detail=optional_text(raw, "detail"),
    )


def parts_of(raw: object) -> tuple[ContentPart, ...]:
    """Read content parts — re-exported so the serializer and reader share one shape."""
    return parts_from(raw)
