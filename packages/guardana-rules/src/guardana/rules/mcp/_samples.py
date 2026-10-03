"""The scripted MCP servers the task and registry rules sample themselves against.

Built fresh for each run, so no sample sees what another one learned.
"""

from collections.abc import Callable

from guardana.core.rule.fixture import DeclaredFixture, FixtureOutcome
from guardana.core.target import McpServerTarget, RegistryEntry, Target
from guardana.core.testing import ScriptedMcpServer

SERVER = "https://mcp.invalid/mcp"
"""A name reserved never to resolve, so no sample can reach a real host."""

CREDENTIAL = "sample-operator-token"
TOOLS = ({"name": "lookup", "description": "Look a record up by its key."},)
REGISTRY_NAME = "io.invalid.samples/lookup"
REPORTED_RELEASE = "1.4.0"


def open_server(**behaviour: object) -> ScriptedMcpServer:
    """Build a `2025-11-25` server that answers anybody, behaving as `behaviour` says."""
    settings: dict[str, object] = {
        "tools": TOOLS,
        "server_info": {"name": "lookup", "version": REPORTED_RELEASE},
        **behaviour,
    }
    return ScriptedMcpServer(SERVER, **settings)  # type: ignore[arg-type]


def gated_server(**behaviour: object) -> ScriptedMcpServer:
    """Build a `2025-11-25` server that refuses every caller not presenting `CREDENTIAL`."""
    return open_server(credential=CREDENTIAL, **behaviour)


def target(
    server: ScriptedMcpServer,
    *,
    credential: str | None = None,
    registry_entry: RegistryEntry | None = None,
) -> McpServerTarget:
    """Build a target that reaches `server` and nothing else."""
    return McpServerTarget(
        server.url,
        credential=credential,
        sender=server,
        discovery_sender=server,
        registry_entry=registry_entry,
    )


def entry(
    *, remotes: tuple[str, ...] = (SERVER,), version: str = REPORTED_RELEASE
) -> RegistryEntry:
    """Build a registry entry for the sample server, publishing `remotes` at `version`."""
    return RegistryEntry.from_document(
        {
            "name": REGISTRY_NAME,
            "version": version,
            "remotes": [{"type": "streamable-http", "url": url} for url in remotes],
        }
    )


def sample(name: str, outcome: FixtureOutcome, build: Callable[[], Target]) -> DeclaredFixture:
    """Declare one sample, built afresh each time the rule is verified."""
    return DeclaredFixture(name, outcome, build)
