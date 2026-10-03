"""Raw HTTP for the MCP client, and the guard on addresses a server hands us.

Two things live here that the JSON-RPC layer above deliberately does not do.

It returns a **reply rather than an exception for a `4xx`**. `401 Unauthorized` is
the single most informative answer an MCP server can give — it carries the
authorization challenge — and a client that turns it into "could not reach the
server" has thrown away the observation it came for.

And it refuses to follow an address that a client must not follow. MCP discovery is
the one place where the server chooses a URL and the client fetches it, which is a
server-side request forgery primitive aimed at whoever runs the scanner. Guardana
resolving `http://169.254.169.254/` because a server asked it to would be the
confused deputy it is here to look for.

A discovery request connects only to an address it checked. Its host is resolved
once at connect time, every address is held to the guard, and the socket is opened
to one of those addresses while the name still travels as `Host` and as TLS SNI, so
a name that answers differently between two lookups has nothing to switch.
"""

import ipaddress
import json
import socket
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPMessage, HTTPResponse, HTTPSConnection
from typing import IO, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, urlsplit
from urllib.request import (
    BaseHandler,
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from guardana.core.target._url import display_url

TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

_SAFE_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}

_CREDENTIAL_HEADERS = frozenset({"authorization", "mcp-session-id"})
"""What a hop to another origin must not carry.

`urlopen` copies every header onto the redirected request — it strips only
`Content-Length` and `Content-Type` — so a bearer token survives a `302` to
anywhere the address guard permits. A session id goes with it: MCP treats one as a
credential often enough that a whole rule exists to grade servers that do.
"""

_Address = ipaddress.IPv4Address | ipaddress.IPv6Address


class McpError(Exception):
    """Raised when an MCP server cannot be reached or answers something unusable."""


@dataclass(frozen=True, slots=True)
class RawReply:
    """One HTTP reply as observed, including the ones that carry an error status."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        """Read one header case-insensitively, or None when it is absent."""
        lowered = name.lower()
        return next((v for k, v in self.headers.items() if k.lower() == lowered), None)

    def json_object(self) -> Mapping[str, object] | None:
        """Parse the body as a JSON object, or None when it is not one.

        Understands an SSE frame, because a streamable-HTTP MCP server routinely
        answers a POST with `text/event-stream` — this client asks for it by name
        in every `Accept` header. Reading only bare JSON here made a perfectly good
        tool listing look like a refusal, which silenced three checks at once.
        """
        try:
            payload = json.loads(json_text(self.body))
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None


def json_text(raw: bytes) -> str:
    """Return the JSON in a reply body, unwrapping an SSE frame when there is one.

    One definition, used by the JSON-RPC reader and by the authorization
    observations, because two readers of the same wire format drift and the one
    that drifts reports the wrong thing quietly.
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if not text.startswith(("event:", "data:", ":")):
        return text
    data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    return data[-1] if data else ""


class RedirectRefusedError(McpError):
    """Raised when a redirect points somewhere a client must not follow."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"refused to follow a redirect to {display_url(url)}: {reason}")
        self.url = url
        self.reason = reason


class AddressRefusedError(McpError):
    """Raised when a discovery host, as it is connected to, resolves to a refused address."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(f"refused to connect to {host}: {reason}")
        self.host = host
        self.reason = reason


@dataclass(frozen=True, slots=True)
class DiscoveryScope:
    """Marks a request as authorization discovery, which connects only to an address it checked.

    `local_target` is whether the server under test is local, decided once for the
    whole discovery, so every fetch in it is held to the same rule even when the
    server's own name answers differently between fetches.
    """

    local_target: bool


class _GuardedRedirect(HTTPRedirectHandler):
    """Re-checks every hop, because the guard was only ever applied to the first one.

    A server that serves its own well-known path with a `302` to the cloud metadata
    endpoint passed the check on the advertised address and was then followed
    anywhere `urlopen` liked — which is precisely the confused deputy this module
    exists to refuse.

    A permitted hop is guarded a second way. `urlopen` copies the request's headers
    onto the new one, so following a redirect to another origin handed that origin
    the operator's bearer token — the same confused deputy aimed at the credential
    rather than at the address, and the reason `--mcp-token-env` needs this before
    it is safe to point at a server nobody controls.
    """

    def __init__(self, *, local_target: bool) -> None:
        super().__init__()
        self._local_target = local_target

    def redirect_request(  # noqa: PLR0913, PLR0917 — the signature urllib calls
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        """Refuse the hop, strip what it must not carry, or hand it back unchanged."""
        refusal = refusal_for(newurl, local_target=self._local_target)
        if refusal is not None:
            # urllib drains and closes the current response only *after* this
            # returns, so raising past it leaks the socket. Close it ourselves.
            fp.close()
            raise RedirectRefusedError(newurl, refusal)
        hop = super().redirect_request(req, fp, code, msg, headers, newurl)
        if hop is None or same_origin(req.full_url, newurl):
            return hop
        return _without_credentials(hop)


def _without_credentials(request: Request) -> Request:
    """Return this request with every credential header removed.

    Rebuilt rather than mutated: `Request.headers` is also read through
    `unredirected_hdrs`, and deleting from one of the two dictionaries is the kind
    of half-measure that leaves the value still being sent.
    """
    kept = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in _CREDENTIAL_HEADERS
    }
    return Request(  # noqa: S310 — the scheme was checked by `refusal_for` one frame up
        request.full_url,
        data=request.data,
        headers=kept,
        origin_req_host=request.origin_req_host,
        unverifiable=True,
        method=request.get_method(),
    )


def same_origin(left: str, right: str) -> bool:
    """Whether two addresses share a scheme, host and port. A missing scheme is never a match.

    One definition, because two would drift: the redirect guard decides what a hop
    may carry with it, and `guardana.mcp.authorization_discovery` decides whether a
    metadata document identifies the server it was served for. Both are asking
    exactly this question, and a scheme's default port is treated as absent so a
    conforming deployment that writes `:443` out is not a different origin from one
    that does not.
    """
    first, second = urlsplit(left), urlsplit(right)
    if not first.scheme or not first.netloc or not second.scheme or not second.netloc:
        return False
    return _origin(first) == _origin(second)


def _origin(parts: SplitResult) -> tuple[str, str, int | None]:
    scheme = parts.scheme.lower()
    port = parts.port
    return (
        scheme,
        (parts.hostname or "").lower(),
        None if port == _DEFAULT_PORTS.get(scheme) else port,
    )


class Sender(Protocol):
    """The one seam every MCP request goes through. Substituted whole in tests.

    Both the JSON-RPC transport and the authorization observer take one, so a
    scripted server doubles the whole client rather than half of it — a double that
    covered only one of the two would leave the other reaching the network from a
    unit test, which is how a suite starts depending on DNS.
    """

    def __call__(  # noqa: PLR0913 — one keyword per thing a request may vary in
        self,
        url: str,
        *,
        method: str = "POST",
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        alongside: str | None = None,
        discovery: DiscoveryScope | None = None,
    ) -> RawReply:
        """Send one request and return the reply, whatever status it carries."""
        raise NotImplementedError


def send(  # noqa: PLR0913 — the keywords the `Sender` protocol publishes
    url: str,
    *,
    method: str = "POST",
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    alongside: str | None = None,
    discovery: DiscoveryScope | None = None,
) -> RawReply:
    """Send one request and return the reply, whatever status it carries.

    Only a transport failure raises. A server that answers `401`, `403` or `500`
    has answered, and every caller here is more interested in *which* of those it
    was than in being handed an exception.

    `alongside` is the server under test, and it decides how strict the guard on
    each **redirect hop** is; it defaults to the address being fetched, so even a
    direct call to the server cannot be bounced somewhere a client must not go.

    `discovery` marks an authorization discovery request and takes the place of
    `alongside` as the source of that strictness. Every hop of it connects only to
    an address the guard accepted, raising `AddressRefusedError` otherwise, and no
    HTTP proxy is used, because a proxy would resolve the name again on its own.
    The server's own requests keep the ordinary opener.
    """
    scheme = urlsplit(url).scheme
    if scheme not in _SAFE_SCHEMES:
        raise McpError("the MCP URL needs an http or https scheme")
    request = Request(url, data=body, headers=dict(headers or {}), method=method)  # noqa: S310
    opener = build_opener(*_handlers(url, alongside=alongside, discovery=discovery))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            return RawReply(
                status=response.status,
                headers=dict(response.headers.items()),
                body=response.read(MAX_RESPONSE_BYTES + 1),
            )
    except HTTPError as error:
        # An error status is an answer. Reading the body may fail on a server that
        # sent headers and hung up; an empty body still leaves the status usable.
        try:
            payload = error.read(MAX_RESPONSE_BYTES + 1)
        except OSError:  # pragma: no cover — depends on the peer hanging up mid-body
            payload = b""
        return RawReply(status=error.code, headers=dict(error.headers.items()), body=payload)
    except (URLError, OSError) as exc:
        raise McpError(f"could not reach {display_url(url)}: {exc}") from exc


def _handlers(
    url: str, *, alongside: str | None, discovery: DiscoveryScope | None
) -> tuple[BaseHandler, ...]:
    """Choose the handlers for one request: guarded redirects, and for discovery a pinned dial."""
    if discovery is None:
        local_target = is_local_address(alongside if alongside is not None else url)
        return (_GuardedRedirect(local_target=local_target),)
    return (
        ProxyHandler({}),
        _GuardedRedirect(local_target=discovery.local_target),
        _PinnedHTTPHandler(local_target=discovery.local_target),
        _PinnedHTTPSHandler(local_target=discovery.local_target),
    )


def refusal_for(url: str, *, local_target: bool) -> str | None:
    """Say why a client must not fetch `url`, or None when fetching it is safe.

    `local_target` says whether the server under test is local, and it decides how
    strict the private-address rule is. A discovery document on `127.0.0.1` is how
    every local development setup works, and refusing it there would make the check
    useless on the machines people try it on first; the same address offered by a
    server on the public internet is an attempt to make this client reach into the
    network it is running in.

    Link-local is refused either way. `169.254.169.254` is the cloud metadata
    endpoint, and nothing legitimate asks a client to go there.

    This lookup is its own, so for a discovery request it only decides early. The
    connection that request opens resolves the name once more, holds those
    addresses to the same rule and dials one of them, so the answer that is
    enforced is the answer that is used.
    """
    parts = urlsplit(url)
    if parts.scheme not in _SAFE_SCHEMES:
        return f"scheme {parts.scheme!r} is not one a client may open"
    host = parts.hostname
    if not host:
        return "the address names no host"
    address_refusal = _refused_address(host, _resolve(host) or (), local_target=local_target)
    if address_refusal is not None:
        return address_refusal
    if parts.scheme == "http" and not local_target:
        return "an authorization endpoint reached over plain http"
    return None


def _refused_address(host: str, addresses: Sequence[_Address], *, local_target: bool) -> str | None:
    """Say why any of a host's addresses must not be reached, or None when all of them may be."""
    for resolved in addresses:
        address = _unmapped(resolved)
        # `::1` sits inside the reserved `::/8`, and loopback is judged by the rule below.
        reserved = address.is_reserved and not address.is_loopback
        if address.is_link_local or address.is_multicast or reserved:
            return f"{host} resolves to {resolved}, an address a client must not be sent to"
        if (address.is_private or address.is_loopback) and not local_target:
            return (
                f"{host} resolves to {resolved}, which is inside the network running this "
                f"scan while the server under test is not"
            )
    return None


def _unmapped(address: _Address) -> _Address:
    """Read an IPv4-mapped IPv6 address as the IPv4 address it reaches.

    The socket reaches the IPv4 host either way, and how the mapped form is
    classified differs between Python versions.
    """
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _resolve(host: str) -> list[_Address] | None:
    """Resolve a host to every address it answers with, or None when it resolves to none.

    An unresolvable host is not refused here. It is a fetch that will fail on its
    own, with an error the caller records; refusing it as dangerous would report a
    typo as an attack.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return None
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _dial(host: str, port: int, timeout: float | None, *, local_target: bool) -> socket.socket:
    """Resolve `host` once, refuse it unless every address passes, and connect to one of them.

    A name that does not resolve raises the resolver's `OSError`, which the caller
    reports as a document that could not be read: a typo is not an attack.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except UnicodeError as exc:
        raise OSError(f"{host} is not a name that can be resolved") from exc
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    refusal = _refused_address(host, addresses, local_target=local_target)
    if refusal is not None:
        raise AddressRefusedError(host, refusal)
    failure = OSError(f"{host} resolves to no address")
    for family, kind, proto, _, address in infos:
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(address)
        except OSError as exc:
            sock.close()
            failure = exc
            continue
        return sock
    raise failure


class _PinnedHTTPConnection(HTTPConnection):
    """A plain-HTTP connection that dials only an address the guard accepted."""

    def __init__(self, host: str, *, timeout: float, local_target: bool) -> None:
        super().__init__(host, timeout=timeout)
        self._local_target = local_target

    def connect(self) -> None:
        """Open the socket to a checked address; `Host` still carries the name."""
        self.sock = _dial(self.host, self.port, self.timeout, local_target=self._local_target)


class _PinnedHTTPSConnection(HTTPSConnection):
    """A TLS connection that dials only an address the guard accepted.

    The handshake names the host, not the address: SNI carries the name and the
    certificate is verified against it, exactly as a connection by name would.
    """

    def __init__(
        self, host: str, *, timeout: float, context: ssl.SSLContext, local_target: bool
    ) -> None:
        super().__init__(host, timeout=timeout, context=context)
        self._pinned_context = context
        self._local_target = local_target

    def connect(self) -> None:
        """Open the socket to a checked address and start TLS for the name."""
        sock = _dial(self.host, self.port, self.timeout, local_target=self._local_target)
        try:
            self.sock = self._pinned_context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


class _PinnedHTTPHandler(HTTPHandler):
    """Opens every plain-HTTP hop of a discovery request through a pinned connection."""

    def __init__(self, *, local_target: bool) -> None:
        super().__init__()
        self._local_target = local_target

    def http_open(self, req: Request) -> HTTPResponse:
        """Open one hop."""
        return self.do_open(self._connection, req)

    def _connection(
        self,
        host: str,
        /,
        *,
        port: int | None = None,
        timeout: float = TIMEOUT_SECONDS,
        source_address: tuple[str, int] | None = None,
        blocksize: int = 8192,
    ) -> HTTPConnection:
        return _PinnedHTTPConnection(host, timeout=timeout, local_target=self._local_target)


class _PinnedHTTPSHandler(HTTPSHandler):
    """Opens every TLS hop of a discovery request through a pinned, verifying connection."""

    def __init__(self, *, local_target: bool) -> None:
        self.verifying = ssl.create_default_context()
        super().__init__(context=self.verifying)
        self._local_target = local_target

    def https_open(self, req: Request) -> HTTPResponse:
        """Open one hop."""
        return self.do_open(self._connection, req)

    def _connection(
        self,
        host: str,
        /,
        *,
        port: int | None = None,
        timeout: float = TIMEOUT_SECONDS,
        source_address: tuple[str, int] | None = None,
        blocksize: int = 8192,
    ) -> HTTPConnection:
        return _PinnedHTTPSConnection(
            host, timeout=timeout, context=self.verifying, local_target=self._local_target
        )


def is_local_address(url: str) -> bool:
    """Say whether this address is inside the machine or its private network.

    Read by the rule that grades an unauthenticated server: one on `127.0.0.1` is
    how everybody develops and reporting it as `high` teaches people to ignore the
    rule, while the same server on a routable address is handing its tool manifest
    to anonymous callers.
    """
    host = urlsplit(url).hostname
    if not host:
        return False
    addresses = _resolve(host)
    if not addresses:
        return False
    return all(address.is_private or address.is_loopback for address in addresses)
