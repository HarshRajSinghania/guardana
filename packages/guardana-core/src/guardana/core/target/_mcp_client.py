"""A minimal MCP client: JSON-RPC over streamable HTTP, or over a spawned process.

Hand-rolled on the standard library rather than taking the official SDK, for the
same reason the protobuf reader is hand-rolled: a security scanner's dependency
tree is part of its own attack surface, and listing tools needs three calls.

Two transports, and they are not equals. HTTP talks to something already running.
**stdio starts the server**, which means executing the code under test — the only
place in the engine that does — so it is refused unless the caller asked for it
explicitly.

Both speak whichever of the protocol's two eras the server does. Which one that is
gets settled once, by `negotiate`, before any question is asked; how a request is
then written lives in `_mcp_wire`.
"""

import os
import selectors
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol
from urllib.parse import urlsplit

from guardana.core.target._mcp_http import (
    MAX_RESPONSE_BYTES,
    TIMEOUT_SECONDS,
    McpError,
    RawReply,
    Sender,
    send,
)
from guardana.core.target._mcp_wire import (
    COMPLETE,
    LEGACY_WIRE,
    PROBE_WIRE,
    SUPPORTED_VERSIONS,
    Era,
    McpProtocolError,
    Wire,
    choose_version,
    era_of,
    error_from,
    newest_legacy,
    result_of,
    server_info_in,
)
from guardana.core.target._url import display_url
from guardana.core.usage import UsageMeter

_HTTP_ERROR = 400
_DISCOVER = "server/discover"
_READ_CHUNK = 64 * 1024

REFUSAL_STATUSES = frozenset({401, 403})
"""The statuses that mean a server decided this caller may not ask; no other status does."""


class McpTransport(Protocol):
    """What the client needs from a way of talking to a server: a revision, a call, a close."""

    def speak(self, wire: Wire) -> None:
        """Adopt a revision; every later request is written and headed for it."""
        raise NotImplementedError

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Send one JSON-RPC request and return its `result`."""
        raise NotImplementedError

    def close(self) -> None:
        """Release whatever this transport holds, stopping a process if it started one."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class McpTool:
    """One tool a server advertises — the declaration an agent's model is handed as context.

    The description is the part a model reads as instruction, and it was all this
    carried until schema drift became something Guardana checks. `input_schema`
    matters for two reasons at once: a property description is read by the model
    exactly like the tool description, and a widened parameter is a change to what
    the tool can be asked to do without a word of the prose changing.
    """

    name: str
    description: str
    title: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    annotations: Mapping[str, Any] = field(default_factory=dict)

    def declaration(self) -> dict[str, Any]:
        """Everything the server declared about this tool, in a stable shape.

        What a pin digests. Prose alone was the old answer, and it left a server
        free to widen a parameter or rewrite a property description while the
        approved manifest stayed green.
        """
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "annotations": dict(self.annotations),
        }


@dataclass(frozen=True, slots=True)
class CacheHints:
    """What a server said about holding on to a result, and about who else may.

    `scope` is the interesting half. `"public"` invites any shared gateway to serve
    this answer to any caller, which is a statement about a document rather than
    about a cache — and therefore something a client can grade without going
    looking for an intermediary. Absent means the server declared nothing, which is
    not the same as declaring it shareable.
    """

    ttl_ms: int | None = None
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class Negotiation:
    """Which revision of MCP this conversation is in, and what the server said about itself.

    `agreed` is what the *server* confirmed — the version it listed and this client
    chose, or the one its handshake answered. Never the version Guardana offered:
    recording our own offer would put a coverage claim in the run manifest that no
    server ever agreed to.
    """

    wire: Wire
    agreed: str | None = None
    supported_versions: tuple[str, ...] = ()
    server_info: Mapping[str, object] | None = None
    capabilities: Mapping[str, object] | None = None
    unsupported: str | None = None
    """Why there is no conversation to have, when client and server share no revision."""

    @property
    def era(self) -> Era:
        """Which shape of the protocol this conversation is written in."""
        return self.wire.era

    @property
    def legacy_wire(self) -> Wire | None:
        """How to address the handshake era of this server, or None when it has none.

        A **dual-era** server is why this is not simply "the era we negotiated". It
        answers `server/discover`, so the conversation settles as modern and has no
        session — while the same server still hands one to every legacy client it
        serves. An observation about sessions has to be bought where sessions
        exist, or a counter for session ids goes unseen on exactly the servers
        running through a migration.
        """
        if self.wire.era is Era.LEGACY:
            return self.wire
        version = newest_legacy(self.supported_versions)
        return Wire(era=Era.LEGACY, version=version) if version else None


@dataclass(frozen=True, slots=True)
class McpConversation:
    """What one conversation established: the revision, the tools offered, the caching claims.

    Not named for a session on purpose. A *session* in MCP is a protocol object the
    `2026-07-28` revision removed and that three rules here grade the minting of;
    reusing the word for "everything one run learned from a server" would put the
    two a reader has to keep apart under one name.
    """

    negotiation: Negotiation
    tools: tuple[McpTool, ...]
    cache: CacheHints = CacheHints()

    @property
    def protocol_version(self) -> str | None:
        """The revision the server confirmed, or None when it confirmed none."""
        return self.negotiation.agreed


class HttpMcpTransport:
    """Talks JSON-RPC to a streamable-HTTP MCP server. Starts nothing."""

    def __init__(self, url: str, *, credential: str | None = None, send: Sender = send) -> None:
        self._url = url
        self._ref = display_url(url)
        self._credential = credential
        self._send = send
        self._session: str | None = None
        self._wire = PROBE_WIRE
        # Validate by sending nothing: a bad scheme has to fail when the target is
        # built, not on the first request, so `guardana plan` refuses it too.
        _reject_unusable_scheme(url)

    @property
    def url(self) -> str:
        """The endpoint this transport posts to."""
        return self._url

    @property
    def session_id(self) -> str | None:
        """The session id the server last issued, or None when it issues none."""
        return self._session

    def speak(self, wire: Wire) -> None:
        """Adopt the negotiated revision for every later request."""
        self._wire = wire

    def headers(self, method: str = _DISCOVER) -> dict[str, str]:
        """Build request headers for one method under the revision in force."""
        return self._wire.headers(method, credential=self._credential, session=self._session)

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Send one JSON-RPC request and return its `result`."""
        reply = self._send(
            self._url, body=self._wire.body(method, params), headers=self.headers(method)
        )
        issued = reply.header("Mcp-Session-Id")
        if issued and self._wire.era is Era.LEGACY:
            self._session = issued
        if reply.status >= _HTTP_ERROR:
            raise _http_failure(reply, self._ref)
        return result_of(reply.body, self._ref)

    def close(self) -> None:
        """Nothing to release: every call is its own request."""


class StdioMcpTransport:
    """Talks JSON-RPC to a server this process **starts**. Executes the thing under test.

    A reply is read in bounded chunks against a deadline: the child is the code under
    examination, so a line without end or a reply that never comes has to cost a
    bounded amount of memory and time, and end in an `McpError`.
    """

    def __init__(self, command: Sequence[str], *, timeout: float = TIMEOUT_SECONDS) -> None:
        if not command:
            raise McpError("an stdio MCP server needs a command to run")
        self._wire = PROBE_WIRE
        self._timeout = timeout
        self._pending = bytearray()
        self._broken: str | None = None
        try:
            # S603: the command comes from the operator, who had to pass
            # --allow-exec to get here; there is no shell and no interpolation.
            self._process = subprocess.Popen(  # noqa: S603
                list(command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise McpError(f"could not start MCP server {command[0]!r}: {exc}") from exc

    def speak(self, wire: Wire) -> None:
        """Adopt the negotiated revision for every later request."""
        self._wire = wire

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Write one JSON-RPC line and read the reply line."""
        if self._process.stdin is None or self._process.stdout is None:
            raise McpError("MCP server process has no usable pipes")
        if self._broken is not None:
            raise McpError(self._broken)
        try:
            self._process.stdin.write(self._wire.body(method, params) + b"\n")
            self._process.stdin.flush()
            reply = self._read_line(self._process.stdout.fileno())
        except OSError as exc:
            raise McpError(f"MCP server stopped responding: {exc}") from exc
        if reply is None:
            raise McpError("MCP server closed its output without answering")
        return result_of(reply, "stdio")

    def _read_line(self, fd: int) -> bytes | None:
        """Read one line from the child, or None when it closed its output first.

        Raw reads on the descriptor, never the buffered pipe: a buffered read would
        block past the deadline, and bytes it buffered would be invisible here.
        Whatever follows the newline is kept for the next request. After a failed
        read the position in the stream is unknown, so every later request fails too.
        """
        deadline = time.monotonic() + self._timeout
        buffered = self._pending
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while (end := buffered.find(b"\n")) < 0:
                if len(buffered) > MAX_RESPONSE_BYTES:
                    raise self._fail(_too_long())
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise self._fail(
                        f"MCP server sent no complete reply within {self._timeout} seconds"
                    )
                chunk = os.read(fd, min(_READ_CHUNK, MAX_RESPONSE_BYTES + 1 - len(buffered)))
                if not chunk:
                    return None
                buffered += chunk
        if end > MAX_RESPONSE_BYTES:
            raise self._fail(_too_long())
        line = bytes(buffered[:end])
        self._pending = buffered[end + 1 :]
        return line

    def _fail(self, reason: str) -> McpError:
        self._broken = reason
        self._pending = bytearray()
        return McpError(reason)

    def close(self) -> None:
        """Stop the server we started; a scanner must not leave a process behind.

        Or a pipe. Terminating the process was enough to stop it and left both
        descriptors open, which a long `monitor` run would accumulate one pair at a
        time until it ran out of them.
        """
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        finally:
            for pipe in (self._process.stdin, self._process.stdout):
                if pipe is not None:
                    pipe.close()


class MeteredTransport:
    """Counts every call a transport makes, and stops one the budget has no room for.

    A wrapper rather than a field on each transport, so an injected double is
    metered exactly like the real thing — a ceiling that only applied to production
    code would be a ceiling no test could prove.

    `reserve` runs *before* the call. That is the whole point: a ceiling of five
    means five requests were sent, and a check made after the fact is a ceiling that
    tells you afterwards how far past it you went.
    """

    def __init__(self, inner: McpTransport, meter: UsageMeter) -> None:
        self._inner = inner
        self._meter = meter

    def speak(self, wire: Wire) -> None:
        """Pass the negotiated revision down; settling one costs nothing to count."""
        self._inner.speak(wire)

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Claim room for this call, make it, and record that it happened."""
        self._meter.reserve()
        try:
            return self._inner.request(method, params)
        finally:
            # Recorded even when the call raised: the request left this machine, and
            # a bill that only counts successes understates what the target was sent.
            self._meter.record(None)

    def close(self) -> None:
        """Close the transport underneath."""
        self._inner.close()


def negotiate(transport: McpTransport) -> Negotiation:
    """Settle which era this server speaks, before anything is asked of it.

    `server/discover` is the question, because it is the only one whose *answer*
    identifies the era: the method did not exist before `2026-07-28`, so a server
    that answers it correctly is modern and one that does anything else is not.

    The specification permits a cheaper route on HTTP — open with an ordinary
    request and read the body of a `400` — and it is not taken. It warns in the
    same breath that some legacy servers do not check that a request arrived after
    `initialize` and will answer an era-ambiguous method anyway; `tools/list` is
    era-ambiguous, so that route would take a tool list from a legacy server and
    record `2026-07-28` in the run manifest. One request is cheaper than a coverage
    claim no server agreed to.
    """
    transport.speak(PROBE_WIRE)
    try:
        discovered = transport.request(_DISCOVER, {})
    except McpProtocolError as exc:
        offered = exc.supported_versions()
        return _modern(transport, offered, None) if offered else _fall_back(transport)
    except McpError:
        return _fall_back(transport)
    offered = _versions_in(discovered)
    if not offered:
        # A reply that is not a discovery result at all: a legacy server whose
        # framework answers unknown methods with an empty object rather than an
        # error. Fall back on the shape, not on a status code.
        return _fall_back(transport)
    return _modern(transport, offered, discovered)


def _modern(
    transport: McpTransport, offered: tuple[str, ...], discovered: Mapping[str, object] | None
) -> Negotiation:
    """Choose a revision from what a modern server named, and adopt it."""
    version = choose_version(offered)
    if version is None:
        return Negotiation(
            wire=PROBE_WIRE, supported_versions=offered, unsupported=_no_common(offered)
        )
    wire = Wire(era=era_of(version), version=version)
    transport.speak(wire)
    if wire.era is Era.LEGACY:
        # A server that advertises its versions but shares only a handshake-era one
        # with this client: modern discovery, legacy conversation. The version it
        # agrees to is what the handshake answers, and the handshake belongs to
        # opening a conversation rather than to settling which one to have.
        return Negotiation(wire=wire, supported_versions=offered)
    return Negotiation(
        wire=wire,
        agreed=version,
        supported_versions=offered,
        server_info=server_info_in(discovered) if discovered is not None else None,
        capabilities=_capabilities_in(discovered),
    )


def _fall_back(transport: McpTransport) -> Negotiation:
    """Adopt the era that opens with `initialize`, without opening anything yet.

    Nothing is sent here. An authorization challenge is not an era signal — a `401`
    on the probe says who may ask, not which protocol answers — so falling back is
    the conservative direction: it leaves every observation a run without a
    credential can still make exactly as it was, and no revision is recorded as
    agreed until a server actually agrees to one.
    """
    transport.speak(LEGACY_WIRE)
    return Negotiation(wire=LEGACY_WIRE)


def _open_the_handshake_era(transport: McpTransport, negotiation: Negotiation) -> Negotiation:
    """Handshake, and re-settle the era when the answer says the server is modern after all.

    The discovery probe is not always conclusive: an authorization challenge says
    who may ask, not which protocol answers, so a protected server that refuses the
    probe leaves the era unsettled and the client falls back. If the handshake then
    comes back as `UnsupportedProtocolVersionError` naming versions, that *is*
    conclusive — the specification says a recognized modern error identifies a
    modern server, and the client retries with a version it named rather than
    reporting a mismatch it has just been told how to fix.
    """
    try:
        return replace(negotiation, agreed=initialize(transport))
    except McpProtocolError as exc:
        offered = exc.supported_versions()
        if not offered:
            raise
        return _modern(transport, offered, None)


def initialize(transport: McpTransport) -> str | None:
    """Open a legacy conversation and return the revision the *server* answered with."""
    result = transport.request(
        "initialize",
        {
            "protocolVersion": LEGACY_WIRE.version,
            "capabilities": {},
            "clientInfo": {"name": "guardana", "version": "0"},
        },
    )
    agreed = result.get("protocolVersion")
    return agreed if isinstance(agreed, str) else None


def _no_common(offered: tuple[str, ...]) -> str:
    return (
        f"the server supports MCP {list(offered)} and Guardana speaks "
        f"{list(SUPPORTED_VERSIONS)}, so there is no revision in common and nothing "
        f"about this server was examined"
    )


def _versions_in(result: Mapping[str, object]) -> tuple[str, ...]:
    listed = result.get("supportedVersions")
    if not isinstance(listed, list):
        return ()
    return tuple(entry for entry in listed if isinstance(entry, str) and entry)


def _capabilities_in(result: Mapping[str, object] | None) -> Mapping[str, object] | None:
    declared = (result or {}).get("capabilities")
    return declared if isinstance(declared, Mapping) else None


def open_conversation(transport: McpTransport) -> McpConversation:
    """Settle the revision and read the manifest, which is everything a run needs from one."""
    return read_manifest(transport, negotiate(transport))


def read_manifest(transport: McpTransport, negotiation: Negotiation) -> McpConversation:
    """Open the conversation if the era needs opening, and list the tools over it.

    Refuses before sending when there is no shared revision. A `tools/list` written
    for a version the server rejected would come back as an error whose message is
    about the request rather than about the mismatch, and a rule reading that would
    report a server it could not reach instead of one it could not speak to.

    The legacy handshake happens here rather than during negotiation because that is
    what it is for: a modern conversation needs no opening, and a run that never
    reads a manifest should not pay for one.
    """
    if negotiation.unsupported is not None:
        raise McpError(negotiation.unsupported)
    settled = negotiation
    if settled.era is Era.LEGACY and settled.agreed is None:
        settled = _open_the_handshake_era(transport, negotiation)
    if settled.unsupported is not None:
        raise McpError(settled.unsupported)
    result = transport.request("tools/list", {})
    return McpConversation(negotiation=settled, tools=tools_in(result), cache=cache_in(result))


def list_tools(transport: McpTransport) -> tuple[McpTool, ...]:
    """Read every tool the server advertises, in the order it advertises them."""
    return tools_in(transport.request("tools/list", {}))


def tools_in(result: Mapping[str, object]) -> tuple[McpTool, ...]:
    """Read a `tools/list` result, skipping entries too malformed to name."""
    raw = result.get("tools")
    if not isinstance(raw, list):
        raise McpError("MCP server did not return a tool list")
    tools = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        tools.append(
            McpTool(
                name=name,
                description=_text(entry, "description"),
                title=_text(entry, "title"),
                input_schema=_mapping(entry, "inputSchema"),
                output_schema=_mapping(entry, "outputSchema"),
                annotations=_mapping(entry, "annotations"),
            )
        )
    return tuple(tools)


def cache_in(result: Mapping[str, object]) -> CacheHints:
    """Read the caching claims a result carries, keeping absent and present apart."""
    ttl = result.get("ttlMs")
    scope = result.get("cacheScope")
    return CacheHints(
        ttl_ms=ttl if isinstance(ttl, int) and not isinstance(ttl, bool) else None,
        scope=scope if isinstance(scope, str) and scope else None,
    )


def carries_tools(reply: RawReply) -> bool | None:
    """Say whether this reply is a tool listing — or None when nobody could tell.

    Three answers, not two. `True` is a manifest the caller received. `False` is a
    refusal: a `401` or `403`, the server declining on purpose. `None` is everything
    nobody could read as either — any other error status (`429`, `500`, `503` say the
    server never got as far as deciding), a success status carrying a JSON-RPC error
    (`-32603` is the server failing, and no code is reserved for a refusal), an
    unparseable body, a reply with no result at all, or an interim result asking for
    input. Folding those into `False` reported a server
    nobody could read as a server that refused, which is a pass on a question that
    was never answered.
    """
    if reply.status in REFUSAL_STATUSES:
        return False
    if not 200 <= reply.status < 300:  # noqa: PLR2004 — the HTTP success range
        return None
    payload = reply.json_object()
    if payload is None:
        return None
    if payload.get("error") is not None:
        return None
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("resultType", COMPLETE) != COMPLETE:
        return None
    return isinstance(result.get("tools"), list)


def _http_failure(reply: RawReply, ref: str) -> McpError:
    """Build the exception for an error status, keeping a JSON-RPC error in the body.

    A modern server answers `400` for an unsupported version, a missing client
    capability and a header mismatch alike, and the body is the only thing that
    tells them apart — which is also how a client decides whether the server is
    modern at all. Discarding it on the status alone is what made every one of
    those look like a server that could not be reached.
    """
    message = f"MCP server at {ref} answered HTTP {reply.status}"
    payload = reply.json_object()
    error = payload.get("error") if payload is not None else None
    return error_from(message, error) if error is not None else McpError(message)


def _too_long() -> str:
    return f"a reply line from the stdio MCP server exceeds {MAX_RESPONSE_BYTES} bytes; refusing it"


def _reject_unusable_scheme(url: str) -> None:
    scheme = urlsplit(url).scheme
    if scheme not in ("http", "https"):
        raise McpError("the MCP server URL needs an http or https scheme")


def _text(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    return value if isinstance(value, str) else ""


def _mapping(entry: Mapping[str, object], key: str) -> Mapping[str, Any]:
    value = entry.get(key)
    return value if isinstance(value, dict) else {}
