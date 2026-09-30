"""A credential in a target URL is refused or redacted, never saved or printed.

The built-in transports cannot use a base URL with userinfo, a query or a fragment,
so `--url` refuses one as invalid usage before anything is sent. An adapter or an
MCP server may legitimately need a query; it is sent as given and shown as a digest
placeholder in the run document, SARIF and every message.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.error import URLError

import guardana.cli._endpoint as endpoint_module
import guardana.cli._reporting as reporting_module
import pytest
from guardana.cli.exit_codes import ExitCode
from guardana.cli.main import app
from guardana.core.manifest import DeploymentRef
from guardana.core.report import ScanResult
from guardana.core.target import McpServerTarget
from guardana.core.testing import RefusingTransport, ScriptedMcpServer
from typer.testing import CliRunner, Result

runner = CliRunner()

_MARKER = "s3cretvalue"
_MCP_SERVER = "https://93.184.215.14/mcp"
_TOOLS = [{"name": "read_file", "description": "Read a file."}]

_UNUSABLE_URLS = pytest.mark.parametrize(
    "url",
    [
        f"http://user:{_MARKER}@fake/v1",
        f"http://fake/v1?key={_MARKER}",
        f"http://fake/v1#{_MARKER}",
        f"http://user:{_MARKER}/rest@fake/v1",
        f"http://user:{_MARKER}?rest@fake/v1",
        f"http://user:{_MARKER}#rest@fake/v1",
        f"http://user:12/{_MARKER}@fake/v1",
    ],
    ids=[
        "userinfo",
        "query",
        "fragment",
        "password-with-slash",
        "password-with-question-mark",
        "password-with-hash",
        "password-with-a-numeric-start",
    ],
)

_URL_COMMANDS = pytest.mark.parametrize(
    "command",
    [
        ["probe"],
        ["plan", "probe"],
        ["target", "inspect"],
        ["monitor", "--max-cycles", "1", "--interval", "0"],
    ],
    ids=["probe", "plan-probe", "target-inspect", "monitor"],
)


def _leaked(result: Result, *files: Path) -> bool:
    texts = [result.stdout, result.stderr, *(f.read_text("utf-8") for f in files if f.exists())]
    return any(_MARKER in text for text in texts)


def _adapter(tmp_path: Path, url: str | None = None) -> Path:
    path = tmp_path / "adapter.yaml"
    line = f"url: '{url}'\n" if url is not None else ""
    path.write_text(f'{line}body:\n  message: "{{{{prompt}}}}"\nresponse_path: reply\n')
    return path


@_URL_COMMANDS
@_UNUSABLE_URLS
def test_a_url_the_built_in_transports_cannot_use_is_invalid_usage(
    monkeypatch: pytest.MonkeyPatch, command: list[str], url: str
) -> None:
    monkeypatch.setattr(endpoint_module, "transport_factory", RefusingTransport)

    result = runner.invoke(app, [*command, "--url", url, "--model", "m"])

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert "--url" in result.output
    assert not _leaked(result)


@_URL_COMMANDS
def test_a_plain_url_is_not_refused(monkeypatch: pytest.MonkeyPatch, command: list[str]) -> None:
    monkeypatch.setattr(endpoint_module, "transport_factory", RefusingTransport)

    result = runner.invoke(app, [*command, "--url", "http://fake/v1", "--model", "m"])

    assert result.exit_code != ExitCode.INVALID_USAGE, result.output


@_URL_COMMANDS
def test_a_url_without_http_is_invalid_usage_without_its_text(
    monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    monkeypatch.setattr(endpoint_module, "transport_factory", RefusingTransport)

    result = runner.invoke(app, [*command, "--url", f"{_MARKER}:x@fake", "--model", "m"])

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert not _leaked(result)


def test_a_plain_url_keeps_the_ref_it_always_had(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(endpoint_module, "transport_factory", RefusingTransport)
    written = tmp_path / "run.json"

    result = runner.invoke(
        app,
        [
            "probe",
            "--url",
            "http://fake/v1/",
            "--model",
            "m",
            "--format",
            "json",
            "--output",
            str(written),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(written.read_text("utf-8"))["run"]["target"]["ref"] == "http://fake#m"


@pytest.mark.parametrize("output_format", ["json", "sarif"])
def test_an_adapter_query_is_sent_but_never_saved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, output_format: str
) -> None:
    sent: list[str] = []

    def fetch(url: str, data: bytes, headers: Mapping[str, str]) -> object:
        sent.append(url)
        return {"reply": "Sure! Here goes, step by step."}

    monkeypatch.setattr("guardana.core.target.adapter._default_fetch", fetch)
    url = f"http://fake/v1?key={_MARKER}"
    written = tmp_path / f"run.{output_format}"
    adapter = str(_adapter(tmp_path))

    result = runner.invoke(
        app,
        [
            *("probe", "--url", url, "--model", "m", "--adapter", adapter),
            *("--format", output_format, "--output", str(written)),
        ],
    )

    assert result.exit_code in (0, 1), result.output
    assert sent
    assert set(sent) == {url}
    assert not _leaked(result, written)
    assert "[redacted:query:" in written.read_text("utf-8")


def test_an_unreachable_adapter_is_named_without_its_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fetch(url: str, data: bytes, headers: Mapping[str, str]) -> object:
        raise URLError("Connection refused")

    monkeypatch.setattr("guardana.core.target.adapter._default_fetch", fetch)

    result = runner.invoke(
        app,
        [
            *("probe", "--url", f"http://fake/v1?key={_MARKER}", "--model", "m"),
            *("--adapter", str(_adapter(tmp_path))),
        ],
    )

    assert result.exit_code == ExitCode.TARGET_UNAVAILABLE, result.output
    assert "could not reach endpoint http://fake/v1?[redacted:query:" in result.stderr
    assert not _leaked(result)


@pytest.mark.parametrize("where", ["adapter-file", "fallback-url"])
def test_an_adapter_url_with_userinfo_is_invalid_usage(tmp_path: Path, where: str) -> None:
    url = f"https://user:{_MARKER}@api.example.com/chat"
    adapter = _adapter(tmp_path, url if where == "adapter-file" else None)
    fallback = url if where == "fallback-url" else "http://fake/v1"

    result = runner.invoke(
        app, ["probe", "--url", fallback, "--model", "m", "--adapter", str(adapter)]
    )

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert not _leaked(result)


@pytest.mark.parametrize("command", [["probe"], ["plan", "probe"]], ids=["probe", "plan-probe"])
def test_an_mcp_url_with_userinfo_is_invalid_usage(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--mcp", f"https://user:{_MARKER}@mcp.example/mcp"])

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert "--mcp" in result.output
    assert not _leaked(result)


def test_an_mcp_query_is_sent_but_never_saved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = f"{_MCP_SERVER}?key={_MARKER}"
    server = ScriptedMcpServer(url, tools=_TOOLS)
    monkeypatch.setattr(
        "guardana.cli._mcp_run.build_mcp_target",
        lambda connection: McpServerTarget(connection.address, sender=server),
    )
    written = tmp_path / "run.json"

    result = runner.invoke(
        app, ["probe", "--mcp", url, "--format", "json", "--output", str(written)]
    )

    assert result.exit_code in (0, 1), result.output
    assert any(sent == url for _, sent, _ in server.requests)
    assert not _leaked(result, written)
    ref = json.loads(written.read_text("utf-8"))["run"]["target"]["ref"]
    assert ref.startswith(f"{_MCP_SERVER}?[redacted:query:")


def test_an_mcp_query_never_reaches_the_collector_as_the_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources: list[str] = []

    class _Collector:
        def __init__(
            self,
            url: str,
            *,
            api_key: str | None = None,
            deployment: DeploymentRef | None = None,
            run: object | None = None,
        ) -> None:
            pass

        def submit(self, result: ScanResult, *, source: str) -> None:
            sources.append(source)

    url = f"{_MCP_SERVER}?key={_MARKER}"
    server = ScriptedMcpServer(url, tools=_TOOLS)
    monkeypatch.setattr(reporting_module, "HttpReporter", _Collector)
    monkeypatch.setattr(
        "guardana.cli._mcp_run.build_mcp_target",
        lambda connection: McpServerTarget(connection.address, sender=server),
    )

    result = runner.invoke(
        app, ["probe", "--mcp", url, "--reporter", "http://collector.example:8000"]
    )

    assert result.exit_code in (0, 1), result.output
    assert sources
    assert all(_MARKER not in source for source in sources)


def test_a_pin_written_for_an_mcp_query_url_holds_no_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    url = f"{_MCP_SERVER}?key={_MARKER}"
    server = ScriptedMcpServer(url, tools=_TOOLS)
    monkeypatch.setattr(
        "guardana.cli._mcp_run.build_mcp_target",
        lambda connection: McpServerTarget(connection.address, sender=server),
    )
    pin = tmp_path / "pin.json"

    result = runner.invoke(app, ["probe", "--mcp", url, "--write-mcp-pin", str(pin)])

    assert result.exit_code == 0, result.output
    assert not _leaked(result, pin)
    assert json.loads(pin.read_text("utf-8"))["server"].startswith(f"{_MCP_SERVER}?[redacted:")


def test_writing_a_pin_for_an_unreachable_server_is_target_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Unreachable:
        def open(self, *args: object, **kwargs: object) -> object:
            raise URLError("Connection refused")

    monkeypatch.setattr(
        "guardana.core.target._mcp_http.build_opener", lambda *handlers: _Unreachable()
    )
    pin = tmp_path / "pin.json"

    result = runner.invoke(
        app,
        ["probe", "--mcp", f"http://127.0.0.1:9/mcp?key={_MARKER}", "--write-mcp-pin", str(pin)],
    )

    assert result.exit_code == ExitCode.TARGET_UNAVAILABLE, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.stderr.strip().count("\n") == 0, result.stderr
    assert result.stderr.startswith("error: ")
    assert "Traceback" not in result.output
    assert not pin.exists()
    assert not _leaked(result)


@pytest.mark.parametrize(
    "endpoint",
    [
        f"http://judge-user:{_MARKER}@judge.internal/v1",
        f"http://judge.internal/v1?key={_MARKER}",
        f"http://judge.internal/v1#{_MARKER}",
    ],
    ids=["userinfo", "query", "fragment"],
)
def test_a_judge_endpoint_carrying_a_credential_is_refused_in_its_own_words(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, endpoint: str
) -> None:
    monkeypatch.setattr(endpoint_module, "transport_factory", RefusingTransport)
    profile = tmp_path / "guardana.yaml"
    profile.write_text(
        f"evaluators:\n  llm_judge:\n    endpoint: '{endpoint}'\n    model: j\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["probe", "--url", "http://fake", "--model", "m", "--profile", str(profile)]
    )

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert not _leaked(result)
    errors = [line for line in result.stderr.splitlines() if not line.startswith("warning: ")]
    assert len(errors) == 1, result.stderr
    assert errors[0].startswith("error: evaluators.llm_judge.endpoint "), result.stderr
    assert "api_key_env" in errors[0]


@pytest.mark.parametrize(
    "reporter",
    [f"https://collector:{_MARKER}@127.0.0.1", f"collector:8000/?token={_MARKER}"],
    ids=["userinfo", "no-scheme"],
)
def test_a_reporter_url_it_cannot_use_is_refused_before_the_scan_without_its_text(
    tmp_path: Path, reporter: str
) -> None:
    result = runner.invoke(app, ["scan", str(tmp_path), "--reporter", reporter])

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert "--reporter" in result.output
    assert not _leaked(result)
