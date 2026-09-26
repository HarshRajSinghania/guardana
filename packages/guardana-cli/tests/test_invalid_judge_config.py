"""An unusable `evaluators:` block is a usage error in one line, before anything is sent."""

from pathlib import Path

import pytest
from guardana.cli.exit_codes import ExitCode
from guardana.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

_ENDPOINT = ["--url", "http://127.0.0.1:9/v1", "--model", "m"]


@pytest.mark.parametrize(
    "command",
    [["plan", "probe", *_ENDPOINT], ["probe", *_ENDPOINT], ["monitor", *_ENDPOINT], ["calibrate"]],
    ids=["plan", "probe", "monitor", "calibrate"],
)
def test_a_judge_without_a_model_exits_invalid_usage_without_a_traceback(
    tmp_path: Path, command: list[str]
) -> None:
    profile = tmp_path / "guardana.yaml"
    profile.write_text(
        "evaluators:\n  llm_judge:\n    endpoint: 'http://127.0.0.1:9/v1'\n", encoding="utf-8"
    )

    result = runner.invoke(app, [*command, "--profile", str(profile)])

    assert result.exit_code == ExitCode.INVALID_USAGE, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    assert "Traceback" not in result.output
    errors = [line for line in result.stderr.splitlines() if not line.startswith("warning: ")]
    assert errors == ["error: evaluators.llm_judge.model must be a non-empty string"]
