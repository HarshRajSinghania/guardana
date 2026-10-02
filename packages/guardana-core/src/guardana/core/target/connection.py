"""How to reach a chat endpoint, read the same way from command-line flags and a judge block.

A `Connection` is what was written: a URL, a model, and optionally a provider, the name
of the variable holding a key, and an adapter file. `resolve_connection` checks it and
returns what a transport needs, refusing before any request every combination that would
send something other than what the run says it sends.

A secret is read only for a connection that will send. A plan prices a run and a lock
pins one; neither needs the key, so neither may fail for the want of it.
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml
from guardana.core.fingerprint import DigestKind, DocumentDigest
from guardana.core.target._url import display_url, private_url_parts
from guardana.core.target.adapter import AdapterConfig, HttpAdapterTransport
from guardana.core.target.endpoint import ChatTransport, EndpointError

DEFAULT_PROVIDER = "openai"
"""The wire protocol of a connection that names none and has no adapter."""

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ADAPTER_KEYS = frozenset({"url", "method", "headers", "body", "response_path"})
_ADAPTER_METHOD = "POST"


class ConnectionConfigError(ValueError):
    """A connection that cannot be used as written; raised before anything is sent."""


@dataclass(frozen=True, slots=True)
class Spelling:
    """How a connection's settings are named where they were written, so a refusal names them."""

    url: str = "--url"
    provider: str = "--provider"
    api_key_env: str = "--api-key-env"
    adapter: str = "--adapter"

    @classmethod
    def judge(cls, block: str) -> "Spelling":
        """Name the settings of the `evaluators.<block>` judge block."""
        prefix = f"evaluators.{block}"
        return cls(
            url=f"{prefix}.endpoint",
            provider=f"{prefix}.provider",
            api_key_env=f"{prefix}.api_key_env",
            adapter=f"{prefix}.adapter",
        )


@dataclass(frozen=True, slots=True)
class Connection:
    """Where a chat endpoint is and how to reach it, as written; checked by `resolve_connection`.

    `provider` is None when none was named, which is how an explicit provider is told
    apart from the default one an adapter cannot be combined with.
    """

    url: str
    model: str
    provider: str | None = None
    api_key_env: str | None = None
    adapter: Path | None = None


@dataclass(frozen=True, slots=True)
class LoadedAdapter:
    """An adapter file read into its configuration, with the digest of the file as written."""

    config: AdapterConfig
    digest: str
    """The SHA-256 of the file's bytes, taken before any `${VAR}` is expanded."""


@dataclass(frozen=True, slots=True)
class ResolvedConnection:
    """A connection that passed every check, holding what a transport needs to send.

    `provider` is None when an adapter supplies the transport. `api_key` is read only
    when the connection was resolved to send, and `transport` is set only for an
    adapter; otherwise the endpoint builds its provider's own transport.
    """

    url: str
    model: str
    provider: str | None
    api_key: str | None
    transport: ChatTransport | None
    adapter_digest: str | None


def resolve_connection(
    connection: Connection,
    *,
    sending: bool,
    spelling: Spelling | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedConnection:
    """Check `connection` and return what a transport needs, or raise `ConnectionConfigError`.

    `sending` says whether the caller will send through it. Only then are the api key
    variable and an adapter's `${VAR}` headers read; a connection resolved not to send
    carries no credential at all, so nothing it builds can authenticate by accident.
    """
    names = spelling or Spelling()
    env = os.environ if environ is None else environ
    if connection.adapter is not None:
        return _through_adapter(connection, connection.adapter, names, env if sending else None)
    provider = connection.provider or DEFAULT_PROVIDER
    _check_provider(provider, names)
    api_key = None
    if sending and connection.api_key_env is not None:
        api_key = _api_key(connection.api_key_env, names, env)
    return ResolvedConnection(
        url=connection.url,
        model=connection.model,
        provider=provider,
        api_key=api_key,
        transport=None,
        adapter_digest=None,
    )


def load_adapter(
    path: Path,
    *,
    url: str,
    environ: Mapping[str, str] | None,
    spelling: Spelling | None = None,
) -> LoadedAdapter:
    """Read an adapter file, refusing anything it cannot honour as written.

    `url` is the URL the run names; an adapter `url:` that differs from it is refused,
    because the requests would go somewhere the run does not say. `environ` expands each
    `${VAR}` in `headers:`; None leaves the headers out, for a connection that will not send.
    """
    names = spelling or Spelling()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ConnectionConfigError(f"cannot read {names.adapter} {path}: {exc}") from exc
    digest = DocumentDigest.of(data, DigestKind.CONTENT).digest
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConnectionConfigError(f"invalid adapter {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConnectionConfigError(f"invalid adapter {path}: the top level must be a mapping")
    unknown = sorted(str(key) for key in set(raw) - _ADAPTER_KEYS)
    if unknown:
        raise ConnectionConfigError(f"invalid adapter {path}: unknown key(s): {', '.join(unknown)}")
    method = raw.get("method", _ADAPTER_METHOD)
    if not isinstance(method, str) or method.upper() != _ADAPTER_METHOD:
        raise ConnectionConfigError(
            f"invalid adapter {path}: method must be POST, the only method the adapter sends"
        )
    if "body" not in raw:
        raise ConnectionConfigError(f"invalid adapter {path}: 'body' is required")
    response_path = raw.get("response_path")
    if not isinstance(response_path, str) or not response_path:
        raise ConnectionConfigError(
            f"invalid adapter {path}: 'response_path' must be a non-empty string"
        )
    raw_headers = raw.get("headers", {})
    if not isinstance(raw_headers, dict):
        raise ConnectionConfigError(f"invalid adapter {path}: 'headers' must be a mapping")
    target = _adapter_url(raw.get("url"), url, path, names)
    headers = (
        {}
        if environ is None
        else {str(key): _expand(str(value), path, environ) for key, value in raw_headers.items()}
    )
    config = AdapterConfig(
        url=target, body=raw["body"], response_path=response_path, headers=headers
    )
    return LoadedAdapter(config=config, digest=digest)


def _through_adapter(
    connection: Connection, adapter: Path, names: Spelling, environ: Mapping[str, str] | None
) -> ResolvedConnection:
    if connection.provider is not None:
        raise ConnectionConfigError(
            f"{names.adapter} cannot be combined with {names.provider}: the adapter file "
            f"is the wire shape; drop one of the two"
        )
    if connection.api_key_env is not None:
        raise ConnectionConfigError(
            f"{names.adapter} cannot be combined with {names.api_key_env}: an adapter sends "
            f"only the headers it names; put the credential in a header reading ${{VAR}}"
        )
    loaded = load_adapter(adapter, url=connection.url, environ=environ, spelling=names)
    try:
        transport = HttpAdapterTransport(loaded.config)
    except EndpointError as exc:
        raise ConnectionConfigError(f"invalid adapter {adapter}: {exc}") from exc
    return ResolvedConnection(
        url=connection.url,
        model=connection.model,
        provider=None,
        api_key=None,
        transport=transport,
        adapter_digest=loaded.digest,
    )


def _adapter_url(written: object, url: str, path: Path, names: Spelling) -> str:
    """Return the URL the adapter posts to, which is always the one the run names."""
    if written is not None and (
        not isinstance(written, str) or written.rstrip("/") != url.rstrip("/")
    ):
        shown = display_url(written) if isinstance(written, str) else repr(written)
        raise ConnectionConfigError(
            f"invalid adapter {path}: its url ({shown}) differs from {names.url} "
            f"({display_url(url)}); the run names the URL it calls, so drop url: from the "
            f"adapter or make the two agree"
        )
    if "userinfo" in private_url_parts(url):
        # urllib fails on userinfo rather than sending it, and the error it raises
        # repeats the part of the address that holds the password.
        raise ConnectionConfigError(
            f"invalid adapter {path}: its URL carries userinfo, which cannot be sent; "
            f"put the credential in a header, e.g. one reading ${{VAR}} from the environment"
        )
    return url


def _expand(value: str, path: Path, environ: Mapping[str, str]) -> str:
    """Replace each `${VAR}` with its value, refusing a variable that is unset or empty.

    A header that expanded to an empty token would send unauthenticated requests whose
    rejections read as refusals.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        found = environ.get(name)
        if not found:
            raise ConnectionConfigError(
                f"adapter {path} references ${{{name}}}, which is unset or empty in this "
                f"environment"
            )
        return found

    return _ENV_REF.sub(replace, value)


def _check_provider(provider: str, names: Spelling) -> None:
    # Imported here, as the endpoint imports it: a provider's backend stays out of
    # the registry walk until a connection names one.
    from guardana.core.target._providers import select_transport  # noqa: PLC0415

    try:
        select_transport(provider)
    except EndpointError as exc:
        raise ConnectionConfigError(f"{names.provider}: {exc}") from None


def _api_key(variable: str, names: Spelling, environ: Mapping[str, str]) -> str:
    value = environ.get(variable) if variable else None
    if not value:
        raise ConnectionConfigError(
            f"{names.api_key_env} names {variable!r}, which is unset or empty in this "
            f"environment; export it, or drop {names.api_key_env} if the endpoint needs no key"
        )
    return value


__all__ = [
    "DEFAULT_PROVIDER",
    "Connection",
    "ConnectionConfigError",
    "LoadedAdapter",
    "ResolvedConnection",
    "Spelling",
    "load_adapter",
    "resolve_connection",
]
