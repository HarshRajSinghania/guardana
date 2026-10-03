"""What one run observed about how an MCP server authorizes requests.

Observations, never conclusions. Nothing here is named after a vulnerability and
nothing here decides anything: it records what was sent, what came back, and — the
field that matters most — why a question could not be asked at all. The rules in
`guardana-rules` read these records and reach the verdicts.

The split is deliberate. Knowing that a Protected Resource Metadata document lives
at a well-known URI is a fact about MCP and belongs beside the client that speaks
it. Believing that `scopes_supported: ["*"]` is too broad is a security opinion,
and opinions belong in a rule a profile can exclude and a taxonomy can answer for.
"""

import base64
import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from guardana.core.target._mcp_client import (
    REFUSAL_STATUSES,
    Negotiation,
    Opening,
    carries_tools,
    changed,
    opening_in,
)
from guardana.core.target._mcp_http import (
    AddressRefusedError,
    DiscoveryScope,
    DiscoverySender,
    McpError,
    RawReply,
    RedirectRefusedError,
    Sender,
    refusal_for,
    server_is_local,
)
from guardana.core.target._mcp_wire import (
    INITIALIZED,
    LEGACY_WIRE,
    UNSUPPORTED_PROTOCOL_VERSION,
    Era,
    McpProtocolError,
    Wire,
    error_member,
    handshake_refusal,
    newest_legacy,
)
from guardana.core.target._url import display_url
from guardana.core.target.endpoint import EndpointUnreachable
from guardana.core.usage import UsageMeter

_CLIENT = {"name": "guardana", "version": "0"}
_CHALLENGE_PARAM = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_SESSION_SAMPLES = 3
_HTTP_ERROR = 400
_SUCCESS = range(200, 300)
_NOT_THE_ERA = frozenset({400, 404, 405})
"""Statuses a server gives a handshake it does not implement at all."""

# A token nobody could mistake for a credential, and nobody could mistake for
# valid: `alg: none`, an audience naming a domain reserved never to resolve, and a
# signature segment that says what it is in words. The expiry is far in the future
# and fixed, so a server that refuses it refuses it on audience or signature rather
# than on the clock — an expired probe would let a server look like it validates
# audiences when all it validated was a date.
_FOREIGN_AUDIENCE = "https://guardana.invalid/not-this-server"

_NO_CREDENTIAL = (
    "no credential was supplied, so there is none to strip; pass --mcp-token-env to "
    "settle whether the session authenticates by itself"
)


@dataclass(frozen=True, slots=True)
class Anonymous:
    """What the server did when asked for its tools with no credential at all."""

    status: int | None = None
    listed_tools: bool = False
    challenge: str | None = None
    error: str | None = None

    @property
    def open_to_anyone(self) -> bool:
        """Whether an anonymous caller actually received the tool manifest."""
        return self.listed_tools


@dataclass(frozen=True, slots=True)
class Document:
    """One metadata document: what was fetched, or why it was not.

    `refused` and `error` are different answers and are kept apart. Refused means a
    client must not go there — the address is link-local, or plain http, or a
    scheme a client may not open — and it is a finding in its own right. Error
    means Guardana went and could not read what came back, which is a gap in the
    evidence rather than a statement about the server's intent.
    """

    url: str
    status: int | None = None
    content: Mapping[str, object] | None = None
    refused: str | None = None
    error: str | None = None

    @property
    def readable(self) -> bool:
        """Whether this document was fetched and parsed."""
        return self.content is not None


@dataclass(frozen=True, slots=True)
class Discovery:
    """The authorization documents this run reached, and every address it would not.

    `refused` is a list rather than a flag on the documents because refusing an
    address and finding a usable document are not alternatives: a server can
    advertise the cloud metadata endpoint in its challenge and still serve a valid
    document at the well-known path, and the pointer is the part worth reporting.
    """

    resource: "Document | None" = None
    authorization: "Document | None" = None
    refused: tuple["Document", ...] = ()


@dataclass(frozen=True, slots=True)
class ForeignToken:
    """What the server did with a bearer token it could not possibly have issued."""

    attempted: bool = False
    status: int | None = None
    listed_tools: bool = False
    not_attempted_because: str | None = None

    @property
    def refused(self) -> bool:
        """Whether the server turned the token away with `401` or `403`, the only answers that do.

        Any other status — a server error, a rate limit, a `200` without a manifest —
        leaves open whether the token would have been accepted.
        """
        return self.attempted and not self.listed_tools and self.status in REFUSAL_STATUSES


@dataclass(frozen=True, slots=True)
class Sessions:
    """The session ids this run saw, and what the server did with one on its own.

    `no_protocol_sessions` names the revision when the server offers no era that has
    sessions at all. It is not a gap in the evidence and it is not a reason nobody
    could look: MCP `2026-07-28` removed protocol sessions, so a server offering
    only modern revisions has none to mint, none to guess, and none to authenticate
    with. The rule reading this stays silent, which here means what silence always
    means — the invariant holds.
    """

    ids: tuple[str, ...] = ()
    stripped_credential: bool = False
    stripped_status: int | None = None
    stripped_listed_tools: bool = False
    not_stripped_because: str | None = None
    no_protocol_sessions: str | None = None
    sampling_error: str | None = None
    """Why sampling stopped before any id was collected: an error or a status, not a result."""
    unsettled_offer: str | None = None
    """Why it is not known whether the server offers a revision with sessions at all."""


@dataclass(frozen=True, slots=True)
class LegacyOffer:
    """Whether the server still answers the handshake era, settled by asking rather than reading.

    `wire` is the `2025-11-25` wire when it does: negotiated, listed by `server/discover`,
    or answered by the legacy probe, whose answer is `opening`. `modern_only` is a server
    observed to refuse the handshake era. `unsettled` says why neither could be told: a
    legacy revision guardana does not speak, or a refusal that says who may ask rather
    than which era answers.
    """

    wire: Wire | None = None
    opening: Opening | None = None
    modern_only: bool = False
    unsettled: str | None = None


class McpAuthorizationView:
    """What a run can observe about a server's authorization, bought one section at a time.

    Each section is a separate purchase in requests, so it is made on first read
    and kept — a run that selected one rule pays for what that rule looks at and
    not for the rest, and a run that selected six pays once. The alternative, a
    record filled in eagerly, made every rule cost the whole probe and made every
    rule's declared cost a number no single run would ever spend.

    Reads are locked because `probe` may run rules at once, and two threads
    arriving together would otherwise buy the same section twice.
    """

    def __init__(self, probe: "_Probe") -> None:
        self._probe = probe
        self._lock = threading.RLock()
        self._anonymous: Anonymous | None = None
        self._discovery: Discovery | None = None
        self._foreign_token: ForeignToken | None = None
        self._sessions: Sessions | None = None
        self._legacy_offer: LegacyOffer | None = None

    @property
    def server(self) -> str:
        """The server these observations are about, as findings may show it."""
        return display_url(self._probe.url)

    @property
    def server_is_local(self) -> bool:
        """Whether the server is local, never decided by a new lookup of its name.

        The server answers lookups of its own name, so only the operator's URL and
        the addresses its own connections already reached count; unknown is not local.
        """
        self.anonymous  # noqa: B018 — the connections this decision reads are made here
        return self._probe.is_local()

    @property
    def credential_presented(self) -> bool:
        """Whether the operator supplied a credential for this server."""
        return self._probe.credential is not None

    @property
    def anonymous(self) -> Anonymous:
        """What the server did when asked for its tools with nothing presented."""
        with self._lock:
            if self._anonymous is None:
                self._anonymous = self._probe.anonymous()
            return self._anonymous

    @property
    def protected_resource(self) -> Document | None:
        """The Protected Resource Metadata document, or why there is none to read."""
        return self._discovered().resource

    @property
    def authorization_server(self) -> Document | None:
        """The authorization server's metadata document, or why there is none to read."""
        return self._discovered().authorization

    @property
    def refused_addresses(self) -> tuple[Document, ...]:
        """Every discovery address this client would not follow, and why."""
        return self._discovered().refused

    @property
    def foreign_token(self) -> ForeignToken:
        """What the server did with a bearer token it could not have issued."""
        anonymous = self.anonymous
        with self._lock:
            if self._foreign_token is None:
                self._foreign_token = self._probe.foreign_token(anonymous)
            return self._foreign_token

    @property
    def sessions(self) -> Sessions:
        """The session ids seen, and what one did on its own without the credential."""
        anonymous = self.anonymous
        with self._lock:
            if self._sessions is None:
                self._sessions = self._probe.sessions(anonymous, lambda: self.legacy_offer)
            return self._sessions

    @property
    def legacy_offer(self) -> LegacyOffer:
        """Whether the server still answers the handshake era, asked once when not yet known."""
        with self._lock:
            if self._legacy_offer is None:
                self._legacy_offer = self._probe.legacy_offer()
            return self._legacy_offer

    @property
    def opening(self) -> Opening | None:
        """What the conversation's `initialize` was answered with, opened on first read.

        None in a modern conversation, which has no handshake; its declarations and
        identity are on `server/discover`'s answer, in the target's negotiation.
        """
        return self._probe.opening()

    def _discovered(self) -> Discovery:
        anonymous = self.anonymous
        with self._lock:
            if self._discovery is None:
                self._discovery = self._probe.discovery(anonymous)
            return self._discovery


def observe(  # noqa: PLR0913 — the target's facts, and the live negotiation it shares
    url: str,
    *,
    credential: str | None,
    meter: UsageMeter,
    send: Sender,
    discovery_send: DiscoverySender,
    negotiation: Callable[[], Negotiation],
    resettle: Callable[[tuple[str, ...]], Negotiation],
    opening: Callable[[], Opening | None],
    learn: Callable[[str], None],
) -> McpAuthorizationView:
    """Open a view onto `url`, sending nothing until a section of it is read.

    Sections are ordered so each can decline on what an earlier one found: there is
    no protected resource to discover on a server that answered an anonymous
    caller, and no audience validation to demonstrate on one either.

    `negotiation` reads the target's one live negotiation rather than a copy, and
    `resettle` settles it again when a handshake is answered by a modern server
    before the era was settled: two copies would let the view grade one revision
    while the conversation spoke another. `opening` reads the conversation's
    handshake, and `learn` hands the target every session id a probe was issued.
    """
    return McpAuthorizationView(
        _Probe(
            url,
            credential=credential,
            meter=meter,
            send=send,
            discovery_send=discovery_send,
            negotiation=negotiation,
            resettle=resettle,
            opening=opening,
            learn=learn,
        )
    )


class _Probe:
    """One server, one credential, and the requests needed to observe it."""

    def __init__(  # noqa: PLR0913 — the arguments `observe` forwards
        self,
        url: str,
        *,
        credential: str | None,
        meter: UsageMeter,
        send: Sender,
        discovery_send: DiscoverySender,
        negotiation: Callable[[], Negotiation],
        resettle: Callable[[tuple[str, ...]], Negotiation],
        opening: Callable[[], Opening | None],
        learn: Callable[[str], None],
    ) -> None:
        self._url = url
        self._ref = display_url(url)
        self._credential = credential
        self._meter = meter
        self._send = send
        self._discovery_send = discovery_send
        self._negotiation = negotiation
        self._resettle = resettle
        self._opening_of = opening
        self._learn = learn

    @property
    def url(self) -> str:
        """The server under test."""
        return self._url

    @property
    def credential(self) -> str | None:
        """The credential the operator supplied, if any."""
        return self._credential

    def is_local(self) -> bool:
        """Whether the server is local, from its URL and the connections already made to it."""
        return server_is_local(self._url, self._send)

    def opening(self) -> Opening | None:
        """Return the conversation's handshake answer, as the target holds it."""
        return self._opening_of()

    def anonymous(self) -> Anonymous:  # noqa: PLR0911 — one return per answer recorded
        """Ask for the tool list presenting nothing, and record what came back.

        Three requests over the handshake era — the handshake, the notification that
        it was accepted, the listing — and one over the modern era, which has no
        handshake. The `WWW-Authenticate` challenge is read from whichever reply
        carried it. A handshake answered with a revision other than `2025-11-25` is
        no conversation to observe, and one refused as a modern server before the era
        was settled settles it again, once, and asks over the modern wire.
        """
        negotiation = self._negotiation()
        if negotiation.unsupported is not None:
            return Anonymous(error=negotiation.unsupported)
        challenge: str | None = None
        session: str | None = None
        if negotiation.era is Era.LEGACY:
            try:
                handshake = self._call("initialize", self._opening(), credential=None)
            except McpError as exc:
                return Anonymous(error=str(exc))
            if self._settles_again(handshake, negotiation):
                return self.anonymous()
            challenge = handshake.header("WWW-Authenticate")
            session = self._session_id_of(handshake)
            if handshake.status >= _HTTP_ERROR:
                return _refused_handshake(handshake.status, challenge)
            refusal = _answered_revision(handshake)
            if refusal is not None:
                return Anonymous(status=handshake.status, challenge=challenge, error=refusal)
            self._announce(credential=None, session=session)
        try:
            listing = self._call("tools/list", {}, credential=None, session=session)
        except McpError as exc:
            return Anonymous(challenge=challenge, error=str(exc))
        listed = carries_tools(listing)
        challenge = challenge or listing.header("WWW-Authenticate")
        if listed is None:
            return Anonymous(
                status=listing.status,
                challenge=challenge,
                error=(
                    f"the reply to tools/list (HTTP {listing.status}) could not be read as a "
                    f"manifest or as a refusal"
                ),
            )
        return Anonymous(status=listing.status, listed_tools=listed, challenge=challenge)

    def discovery(self, anonymous: Anonymous) -> "Discovery":
        """Follow the authorization discovery chain, refusing addresses a client must not.

        Whether the server under test is local is decided once, here, from the
        operator's URL and the addresses the server's own connections reached —
        never from a new lookup of its name, which the server itself answers.
        """
        if anonymous.open_to_anyone:
            return Discovery()
        scope = DiscoveryScope(local_target=server_is_local(self._url, self._send))
        resource, refused = self._first_readable(
            _resource_metadata_urls(self._url, anonymous.challenge), scope
        )
        issuer = _first_issuer(resource)
        if issuer is None:
            return Discovery(resource=resource, refused=tuple(refused))
        authorization, more = self._first_readable(_authorization_server_urls(issuer), scope)
        return Discovery(
            resource=resource, authorization=authorization, refused=tuple(refused + more)
        )

    def foreign_token(self, anonymous: Anonymous) -> ForeignToken:
        """Present a token this server cannot have issued, and see whether it is refused.

        Declined outright when an anonymous caller already got the manifest: a
        server that asks for nothing cannot demonstrate that it validates anything,
        and reading its `200` as a failure of audience validation would put a
        critical finding on every unauthenticated development server there is.
        """
        if anonymous.open_to_anyone:
            return ForeignToken(
                not_attempted_because=(
                    "the server answers an anonymous caller, so accepting a token proves "
                    "nothing about whether it validates one"
                )
            )
        if anonymous.error is not None:
            return ForeignToken(
                not_attempted_because=f"the server could not be reached: {anonymous.error}"
            )
        token = forged_token()
        session: str | None = None
        if self._negotiation().era is Era.LEGACY:
            try:
                handshake = self._call("initialize", self._opening(), credential=token)
            except McpError as exc:
                return ForeignToken(not_attempted_because=f"the probe could not be sent: {exc}")
            if handshake.status >= _HTTP_ERROR:
                return ForeignToken(attempted=True, status=handshake.status)
            session = self._session_id_of(handshake)
            self._announce(credential=token, session=session)
        try:
            listing = self._call("tools/list", {}, credential=token, session=session)
        except McpError as exc:
            return ForeignToken(not_attempted_because=f"the probe could not be completed: {exc}")
        listed = carries_tools(listing)
        return ForeignToken(attempted=True, status=listing.status, listed_tools=listed is True)

    def sessions(  # noqa: PLR0911 — one return per reason the sample ends
        self, anonymous: Anonymous, offer: Callable[[], "LegacyOffer"]
    ) -> Sessions:
        """Collect session ids, then try one on its own without the credential that made it.

        Bought over the *handshake* era, whichever era the run negotiated. A
        dual-era server settles as modern and has no session in that conversation,
        while still handing one to every legacy client it serves — so asking only
        over the negotiated era would leave a counter for session ids unseen on
        exactly the servers running through a migration. Whether the handshake era
        is still offered is asked, through `offer`, when discovery did not say.
        """
        negotiation = self._negotiation()
        legacy = negotiation.legacy_wire
        blocked = self._cannot_establish_a_session(anonymous)
        if legacy is None:
            if blocked is not None:
                return Sessions(not_stripped_because=blocked)
            offered = offer()
            if offered.modern_only:
                return Sessions(no_protocol_sessions=negotiation.wire.version)
            if offered.wire is None:
                return Sessions(unsettled_offer=offered.unsettled or "the server named no era")
            legacy = offered.wire
        if blocked is not None:
            return Sessions(not_stripped_because=blocked)
        ids, sampling_error = self._sample_session_ids(legacy)
        if not ids:
            if sampling_error is not None:
                return Sessions(sampling_error=sampling_error)
            return Sessions(not_stripped_because="the server issues no session id")
        declined = self._cannot_strip_the_credential(anonymous)
        if declined is not None:
            return Sessions(ids=ids, not_stripped_because=declined)
        return self._without_the_credential(ids, legacy)

    def legacy_offer(self) -> LegacyOffer:  # noqa: PLR0911 — one return per answer class
        """Settle whether the server still answers `initialize`, asking when discovery did not say.

        One handshake over the `2025-11-25` wire, with the operator's credential when
        one is configured: a result naming that revision is a dual-era server; a
        JSON-RPC error, `400`, `404` or `405` is a modern-only one; a refusal says who
        may ask, not which era answers, and leaves it unknown.
        """
        negotiation = self._negotiation()
        if negotiation.legacy_wire is not None:
            return LegacyOffer(wire=negotiation.legacy_wire)
        listed = newest_legacy(negotiation.supported_versions)
        if listed is not None:
            return LegacyOffer(
                unsettled=(
                    f"the server lists {listed} of the handshake era, a revision guardana "
                    f"does not speak"
                )
            )
        try:
            reply = self._call("initialize", self._opening(LEGACY_WIRE), wire=LEGACY_WIRE)
        except McpError as exc:
            return LegacyOffer(unsettled=f"the legacy handshake could not be sent: {exc}")
        if reply.status in REFUSAL_STATUSES:
            advice = "" if self._credential is not None else "; pass --mcp-token-env to settle it"
            return LegacyOffer(
                unsettled=f"the legacy handshake was refused with HTTP {reply.status}{advice}"
            )
        payload = reply.json_object()
        if error_member(payload) is not None or reply.status in _NOT_THE_ERA:
            return LegacyOffer(modern_only=True)
        result = payload.get("result") if payload is not None else None
        if reply.status in _SUCCESS and isinstance(result, dict):
            opening = opening_in(result)
            refusal = handshake_refusal(opening.version)
            if refusal is not None:
                return LegacyOffer(opening=opening, unsettled=refusal)
            return LegacyOffer(wire=LEGACY_WIRE, opening=opening)
        return LegacyOffer(
            unsettled=(
                f"the legacy handshake was answered with HTTP {reply.status}, which is neither "
                f"a result nor a refusal of the era"
            )
        )

    def _without_the_credential(self, ids: tuple[str, ...], wire: Wire) -> Sessions:
        """Send one request carrying the session and not the credential that made it.

        The session's own client announces the accepted handshake first, with the
        credential, as the `2025-11-25` lifecycle asks before any further request.
        """
        self._announce(wire=wire, session=ids[-1])
        try:
            listing = self._call("tools/list", {}, wire=wire, credential=None, session=ids[-1])
        except McpError as exc:
            return Sessions(ids=ids, not_stripped_because=f"the probe could not be sent: {exc}")
        listed = carries_tools(listing)
        if listed is None:
            return Sessions(
                ids=ids,
                not_stripped_because=(
                    "the reply to the credential-stripped request could not be read, so "
                    "whether the session authenticated it is unknown"
                ),
            )
        return Sessions(
            ids=ids,
            stripped_credential=True,
            stripped_status=listing.status,
            stripped_listed_tools=listed,
        )

    def _cannot_establish_a_session(self, anonymous: Anonymous) -> str | None:
        """Say why no session can be opened at all, or None when one can."""
        if anonymous.error is not None:
            return f"the server could not be reached: {anonymous.error}"
        if self._credential is None and not anonymous.open_to_anyone:
            # Reporting "the server issues no session id" here would blame the
            # server for the operator's missing credential — a true sentence about
            # the wrong thing.
            return _NO_CREDENTIAL
        return None

    def _cannot_strip_the_credential(self, anonymous: Anonymous) -> str | None:
        """Say why removing the credential would prove nothing, or None when it would."""
        if self._credential is None:
            return _NO_CREDENTIAL
        if anonymous.open_to_anyone:
            return (
                "the server answers an anonymous caller, so a request without a "
                "credential shows nothing about the session"
            )
        return None

    def _sample_session_ids(self, wire: Wire) -> tuple[tuple[str, ...], str | None]:
        """Handshake `_SESSION_SAMPLES` times; return the ids issued and why sampling stopped early.

        Its own handshakes, deliberately. The sample used to reuse ids recorded by
        the anonymous probe and the forged-token probe, which made the verdict
        depend on *which rules were selected*: on a server that issues one session
        per credential, `session_binding` alone saw three identical ids and reported
        a critical finding, while the same server with `token_audience` also
        selected saw a fourth id and reported nothing. A profile exclusion must not
        change what is true about the target.

        Bounded by attempts rather than by results, so a server that issues no
        session id ends the loop instead of handshaking until the budget stops it.
        The reason is kept only when the very first handshake was not a result: an
        error there is not a server that issues no session id.
        """
        sampled: list[str] = []
        for _ in range(_SESSION_SAMPLES):
            try:
                reply = self._call("initialize", self._opening(wire), wire=wire)
            except McpError:
                break
            problem = _sampling_problem(reply)
            if problem is not None:
                return tuple(sampled), (None if sampled else problem)
            issued = self._session_id_of(reply)
            if issued is None:
                break
            sampled.append(issued)
        return tuple(sampled), None

    def _opening(self, wire: Wire | None = None) -> Mapping[str, object]:
        """Build the `initialize` parameters for one era, naming the version that era carries.

        Built from the wire rather than from a constant, because the version in the
        body and the version in the `MCP-Protocol-Version` header have to be the
        same one.
        """
        used = wire if wire is not None else self._negotiation().wire
        return {"protocolVersion": used.version, "capabilities": {}, "clientInfo": _CLIENT}

    def _call(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        wire: Wire | None = None,
        credential: str | None = "",
        session: str | None = None,
    ) -> RawReply:
        """Send one probe request, written for the era this observation belongs to.

        `wire` defaults to the negotiated one; the session observations pass the
        handshake era explicitly, because that is the only era a session exists in.
        The body and the headers are built from the same `Wire`, so the version a
        modern server reads in `_meta` is the one it reads in the header — a
        disagreement is a `HeaderMismatch` and the probe would grade a rejection it
        caused itself.

        Every status is an observation, with two exceptions that stop the run: no
        reply at all, and a refusal of the revision the run settled on.
        """
        negotiation = self._negotiation()
        used = wire if wire is not None else negotiation.wire
        token = self._credential if credential == "" else credential
        return self._observed(
            negotiation,
            used,
            used.body(method, params),
            used.headers(method, credential=token, session=session),
        )

    def _announce(
        self, *, wire: Wire | None = None, credential: str | None = "", session: str | None
    ) -> None:
        """Tell the server its handshake was accepted, before the next request of that session."""
        negotiation = self._negotiation()
        used = wire if wire is not None else negotiation.wire
        token = self._credential if credential == "" else credential
        self._observed(
            negotiation,
            used,
            used.notification(INITIALIZED),
            used.headers(INITIALIZED, credential=token, session=session),
        )

    def _observed(
        self, negotiation: Negotiation, wire: Wire, body: bytes, headers: Mapping[str, str]
    ) -> RawReply:
        """Send one probe and return its reply, raising only for no reply or a dropped revision."""
        try:
            reply = self._spend(lambda: self._send(self._url, body=body, headers=headers))
        except (RedirectRefusedError, AddressRefusedError):
            raise
        except McpError as exc:
            raise EndpointUnreachable(
                f"the MCP server at {self._ref} did not answer: {exc}"
            ) from exc
        issued = self._session_id_of(reply)
        if issued:
            self._learn(issued)
        agreed = negotiation.settled_version
        refused = _revision_refusal(reply)
        if refused is not None and agreed is not None and wire.version == agreed:
            raise changed(self._ref, agreed, refused.supported_versions())
        return reply

    def _settles_again(self, handshake: RawReply, negotiation: Negotiation) -> bool:
        """Settle the era again when an unsettled handshake was refused by a modern server."""
        refused = _revision_refusal(handshake)
        if refused is None or negotiation.settled_version is not None:
            return False
        offered = refused.supported_versions()
        if not offered:
            return False
        return self._resettle(offered).settled_version is not None

    def _fetch(self, url: str, scope: DiscoveryScope) -> Document:
        """Fetch one discovery document over a connection pinned to an address the guard passed."""
        refusal = refusal_for(url, local_target=scope.local_target)
        if refusal is not None:
            return Document(url=url, refused=refusal)
        try:
            reply = self._spend(
                lambda: self._discovery_send(
                    url,
                    method="GET",
                    headers={"Accept": "application/json"},
                    alongside=self._url,
                    discovery=scope,
                )
            )
        except (RedirectRefusedError, AddressRefusedError) as exc:
            # A refusal is a finding, not a gap in the evidence: the address was
            # reached for and turned down, which is what `discovery_target` reports.
            return Document(url=url, refused=_refused_because(exc))
        except McpError as exc:
            return Document(url=url, error=str(exc))
        if reply.status >= _HTTP_ERROR:
            return Document(url=url, status=reply.status)
        content = reply.json_object()
        if content is None:
            return Document(url=url, status=reply.status, error="the reply is not a JSON object")
        return Document(url=url, status=reply.status, content=content)

    def _first_readable(
        self, urls: tuple[str, ...], scope: DiscoveryScope
    ) -> tuple[Document | None, list[Document]]:
        """Try each candidate in specification order; return the answer and every refusal.

        Refusals are returned separately rather than as the result, because a server
        may advertise an address a client must not follow *and* serve a perfectly
        good document at the well-known path. Reporting only the document that
        worked would lose the pointer, which is the more interesting of the two: a
        server aiming its client at the cloud metadata endpoint has done that on
        purpose, whatever else it also serves.
        """
        attempts: list[Document] = []
        refused: list[Document] = []
        for url in urls:
            document = self._fetch(url, scope)
            if document.refused is not None:
                refused.append(document)
                continue
            if document.readable:
                return document, refused
            attempts.append(document)
        return (attempts[-1] if attempts else None), refused

    def _spend(self, call: Callable[[], RawReply]) -> RawReply:
        self._meter.reserve()
        try:
            return call()
        finally:
            self._meter.record(None)

    def _session_id_of(self, reply: RawReply) -> str | None:
        """Read the session id a reply issued, or None when it issued none."""
        return reply.header("Mcp-Session-Id")


def _refused_because(exc: RedirectRefusedError | AddressRefusedError) -> str:
    """Say why a discovery fetch was turned down after it had set out."""
    if isinstance(exc, RedirectRefusedError):
        return f"it redirected to {display_url(exc.url)}, and {exc.reason}"
    return f"when it was connected to, {exc.reason}"


def _revision_refusal(reply: RawReply) -> McpProtocolError | None:
    """Return the `UnsupportedProtocolVersionError` a reply carries, or None."""
    error = error_member(reply.json_object())
    if error is None or error.get("code") != UNSUPPORTED_PROTOCOL_VERSION:
        return None
    return McpProtocolError("", code=UNSUPPORTED_PROTOCOL_VERSION, data=error.get("data"))


def _answered_revision(reply: RawReply) -> str | None:
    """Say why a handshake's result opens no conversation, or None when it does or carries none."""
    payload = reply.json_object()
    result = payload.get("result") if payload is not None else None
    if not isinstance(result, dict):
        return None
    return handshake_refusal(result.get("protocolVersion"))


def _sampling_problem(reply: RawReply) -> str | None:
    """Say why a sampling handshake was not a result, or None when it was one in `2025-11-25`."""
    payload = reply.json_object()
    error = error_member(payload)
    if error is not None:
        return f"the handshake was answered with JSON-RPC error {error.get('code')}"
    if reply.status not in _SUCCESS:
        return f"the handshake was answered with HTTP {reply.status}"
    result = payload.get("result") if payload is not None else None
    if not isinstance(result, dict):
        return f"the reply to the handshake (HTTP {reply.status}) is not a result"
    return handshake_refusal(result.get("protocolVersion"))


def _refused_handshake(status: int, challenge: str | None) -> Anonymous:
    """Record an error status to the anonymous handshake: a refusal, or a question left open."""
    if status in REFUSAL_STATUSES:
        return Anonymous(status=status, challenge=challenge)
    return Anonymous(
        status=status,
        challenge=challenge,
        error=f"the handshake was answered with HTTP {status}, which is neither a session "
        f"nor a refusal",
    )


def forged_token() -> str:
    """Build the bearer token the audience probe presents.

    Public because the documentation quotes it: an operator reading a critical
    finding is entitled to see exactly what was sent to their server, and a probe
    whose payload is only visible in the source is one nobody can audit.
    """
    header = _segment({"alg": "none", "typ": "JWT"})
    payload = _segment(
        {
            "iss": "https://guardana.invalid/",
            "aud": _FOREIGN_AUDIENCE,
            "sub": "guardana-probe",
            "exp": 4102444800,
        }
    )
    return f"{header}.{payload}.guardana-probe-not-a-valid-signature"


def scopes_in(document: Mapping[str, object] | None) -> tuple[str, ...]:
    """Read `scopes_supported` from a metadata document, ignoring anything unnamed."""
    if document is None:
        return ()
    raw = document.get("scopes_supported")
    if not isinstance(raw, list):
        return ()
    return tuple(entry for entry in raw if isinstance(entry, str) and entry)


def challenge_parameters(challenge: str | None) -> dict[str, str]:
    """Read the quoted parameters out of a `WWW-Authenticate` header."""
    if not challenge:
        return {}
    return {name.lower(): value for name, value in _CHALLENGE_PARAM.findall(challenge)}


def _first_issuer(resource: Document | None) -> str | None:
    """Read the first authorization server a metadata document names."""
    if resource is None or resource.content is None:
        return None
    issuers = resource.content.get("authorization_servers")
    if not isinstance(issuers, list):
        return None
    return next((entry for entry in issuers if isinstance(entry, str) and entry), None)


def _resource_metadata_urls(server: str, challenge: str | None) -> tuple[str, ...]:
    """Every place a Protected Resource Metadata document may be, in specification order."""
    parts = urlsplit(server)
    host = _host_of(parts)
    root = urlunsplit((parts.scheme, host, "/.well-known/oauth-protected-resource", "", ""))
    path = parts.path.rstrip("/")
    candidates = []
    advertised = challenge_parameters(challenge).get("resource_metadata")
    if advertised:
        candidates.append(advertised)
    if path:
        candidates.append(
            urlunsplit((parts.scheme, host, f"/.well-known/oauth-protected-resource{path}", "", ""))
        )
    candidates.append(root)
    return tuple(dict.fromkeys(candidates))


def _authorization_server_urls(issuer: str) -> tuple[str, ...]:
    """List the discovery endpoints a client must try for an issuer, in specification order."""
    parts = urlsplit(issuer)
    host = _host_of(parts)
    path = parts.path.rstrip("/")
    if path:
        return (
            urlunsplit(
                (
                    parts.scheme,
                    host,
                    f"/.well-known/oauth-authorization-server{path}",
                    "",
                    "",
                )
            ),
            urlunsplit((parts.scheme, host, f"/.well-known/openid-configuration{path}", "", "")),
            urlunsplit((parts.scheme, host, f"{path}/.well-known/openid-configuration", "", "")),
        )
    return (
        urlunsplit((parts.scheme, host, "/.well-known/oauth-authorization-server", "", "")),
        urlunsplit((parts.scheme, host, "/.well-known/openid-configuration", "", "")),
    )


def _host_of(parts: SplitResult) -> str:
    """Return the host and port of an address, without any userinfo it carried."""
    return parts.netloc.rpartition("@")[2]


def _segment(claims: Mapping[str, object]) -> str:
    raw = json.dumps(claims, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


__all__ = [
    "Anonymous",
    "Discovery",
    "Document",
    "ForeignToken",
    "LegacyOffer",
    "McpAuthorizationView",
    "Sender",
    "Sessions",
    "challenge_parameters",
    "forged_token",
    "observe",
    "scopes_in",
]
