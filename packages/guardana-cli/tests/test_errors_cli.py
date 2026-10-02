import io
import re
from collections.abc import Callable
from email.message import Message
from urllib.error import HTTPError, URLError

import guardana.cli._endpoint as endpoint_module
import pytest
import typer
from guardana.cli._errors import EndpointFlag, run_against_endpoint
from guardana.cli.exit_codes import ExitCode
from guardana.cli.main import app
from guardana.core.testing import FailingTransport
from typer.testing import CliRunner

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def normalised(output: str) -> str:
    """Flatten styling and wrapping, which differ between a laptop and a CI runner."""
    return " ".join(_ANSI.sub("", output).replace("\u2502", " ").split())


def _rejects_the_request() -> FailingTransport:
    return FailingTransport(HTTPError("http://x", 401, "Unauthorized", {}, None))  # type: ignore[arg-type]


def test_4xx_reports_rejected_distinctly(capsys: pytest.CaptureFixture[str]) -> None:
    def action() -> None:
        raise HTTPError("http://x", 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

    with pytest.raises(typer.Exit) as exc:
        run_against_endpoint("http://x", action)
    assert exc.value.exit_code == ExitCode.TARGET_UNAVAILABLE
    assert "rejected" in capsys.readouterr().err.lower()


def test_a_sustained_rate_limit_names_the_knob_that_fixes_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Reaching the CLI means the transport already retried with backoff, so the
    # generic 4xx advice ("check your auth header") would send someone to debug a
    # header that is working. The actionable answer is the concurrency limit.
    def action() -> None:
        raise HTTPError("http://x", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]

    with pytest.raises(typer.Exit) as exc:
        run_against_endpoint("http://x", action, accepts=(EndpointFlag.CONCURRENCY,))
    assert exc.value.exit_code == ExitCode.TARGET_UNAVAILABLE
    err = capsys.readouterr().err.lower()
    assert "--concurrency" in err
    assert "auth" not in err


def test_unreachable_host_reports_could_not_reach(capsys: pytest.CaptureFixture[str]) -> None:
    def action() -> None:
        raise URLError("connection refused")

    with pytest.raises(typer.Exit) as exc:
        run_against_endpoint("http://x", action)
    assert exc.value.exit_code == ExitCode.TARGET_UNAVAILABLE
    assert "could not reach" in capsys.readouterr().err.lower()


def test_advice_never_names_a_flag_the_command_does_not_take(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Advice the command would reject costs the reader a second failed run, so a
    # message names only the flags of the command it is printed from.
    def action() -> None:
        raise HTTPError("http://x", 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

    with pytest.raises(typer.Exit):
        run_against_endpoint("http://x", action, accepts=(EndpointFlag.API_KEY_ENV,))
    err = normalised(capsys.readouterr().err)
    assert "rejected the request (HTTP 401)" in err
    assert "--adapter" not in err
    assert "--api-key-env" in err


@pytest.mark.parametrize(
    "command", [["probe"], ["target", "inspect"]], ids=["probe", "target-inspect"]
)
def test_every_command_taking_an_adapter_names_it(
    monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    monkeypatch.setattr(endpoint_module, "transport_factory", _rejects_the_request)

    result = runner.invoke(app, [*command, "--url", "http://x", "--model", "m"])

    assert result.exit_code == ExitCode.TARGET_UNAVAILABLE, result.output
    err = normalised(result.output)
    assert "rejected the request (HTTP 401)" in err
    assert "--adapter" in err
    assert "--api-key-env" in err


def test_a_rate_limit_names_concurrency_only_where_it_exists(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def action() -> None:
        raise HTTPError("http://x", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]

    with pytest.raises(typer.Exit):
        run_against_endpoint("http://x", action, accepts=(EndpointFlag.API_KEY_ENV,))
    err = normalised(capsys.readouterr().err)
    assert "--concurrency" not in err
    assert "wait for the quota to reset" in err


def _fails_with(status: int, body: bytes) -> Callable[[], None]:
    def action() -> None:
        raise HTTPError("http://x", status, "status", Message(), io.BytesIO(body))

    return action


def _message(capsys: pytest.CaptureFixture[str], status: int, body: bytes) -> str:
    with pytest.raises(typer.Exit) as exc:
        run_against_endpoint("http://x", _fails_with(status, body), accepts=tuple(EndpointFlag))
    assert exc.value.exit_code == ExitCode.TARGET_UNAVAILABLE
    return capsys.readouterr().err


def test_a_4xx_that_is_not_about_credentials_quotes_the_body_instead_of_blaming_the_header(
    capsys: pytest.CaptureFixture[str],
) -> None:
    err = _message(capsys, 400, b'{"detail":{"code":"input_rejected"}}')

    assert "rejected the request (HTTP 400); its body begins: " in err
    assert '{"detail":{"code":"input_rejected"}}' in err
    assert "auth" not in err


@pytest.mark.parametrize("status", [401, 403, 407])
def test_a_credentials_status_keeps_the_auth_advice(
    capsys: pytest.CaptureFixture[str], status: int
) -> None:
    err = _message(capsys, status, b"denied")

    assert f"rejected the request (HTTP {status})" in err
    assert "check the auth header" in err


def test_the_quoted_body_is_bounded_redacted_and_escaped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = b"sk-ant-api03-" + b"a" * 95 + b"AA"
    err = _message(capsys, 422, b"bad\x1b[31m\n" + secret + b" " + b"x" * 1000)

    assert secret.decode() not in err
    assert "[redacted:" in err
    assert "\x1b" not in err
    assert "bad\\x1b[31m\\n" in err
    quoted = err.split("its body begins: ", 1)[1].rstrip("\n")
    assert len(quoted) == 201
    assert quoted.endswith("…")


def test_an_empty_body_is_named_rather_than_quoted(capsys: pytest.CaptureFixture[str]) -> None:
    assert "its body was empty" in _message(capsys, 404, b"")


def test_a_5xx_quotes_its_body_too(capsys: pytest.CaptureFixture[str]) -> None:
    err = _message(capsys, 503, b'{"detail":{"code":"chat_disabled"}}')

    assert "returned HTTP 503; its body begins:" in err
    assert "chat_disabled" in err
