import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from guardana.cli._adapter import load_adapter_config
from guardana.cli._budget_flags import override
from guardana.cli._endpoint import build_endpoint
from guardana.cli._errors import EndpointFlag, run_against_endpoint
from guardana.cli._evaluators import judge_endpoint, wire_config_evaluators
from guardana.cli._exit import exit_with, refuse_invalid_profile, refuse_unenforceable_budget
from guardana.cli._formats import OutputFormat
from guardana.cli._mcp_run import (
    McpConnection,
    credential_from,
    require_chat_endpoint,
    run_mcp_probe,
)
from guardana.cli._output import emit, refuse_incomparable_output
from guardana.cli._plugins import (
    AllowPluginOption,
    PluginsOption,
    hint_refused_plugins,
    resolve_trust,
)
from guardana.cli._profile import PRESET_HELP, resolve_profile
from guardana.cli._reporting import check_reporter_url, submit_safely
from guardana.cli._rules_loading import load_custom_rules
from guardana.cli._run_meta import calibrations_or_exit, detect_deployment, detect_source
from guardana.cli._safety_flags import parse_impact
from guardana.cli._target_locator import resolve_target
from guardana.core.budget import BudgetExhausted
from guardana.core.manifest import DeploymentRef
from guardana.core.profile import Profile, ProfileError
from guardana.core.registry import Registry
from guardana.core.target import (
    ChatTransport,
    EndpointError,
    HttpAdapterTransport,
    Target,
    TargetKind,
    display_url,
)
from guardana.core.usage import UsageMeter
from guardana.core.verify import (
    JudgeUnreachableError,
    TargetUnavailableError,
    UnenforceableBudgetError,
    Verification,
    Verifier,
)
from guardana.report import get_renderer

_Run = TypeVar("_Run", Verification, Verification | None)

# Four in flight speeds up a probe that mostly waits on a model while staying polite to
# a single-slot local server; a 429 is retried with backoff, so a busy endpoint slows
# the probe instead of failing it.
_DEFAULT_CONCURRENCY = 4

_ACCEPTED_FLAGS = (
    EndpointFlag.ADAPTER,
    EndpointFlag.API_KEY_ENV,
    EndpointFlag.CONCURRENCY,
)


def probe(  # noqa: C901, PLR0913, PLR0917 — Typer surface, target modes
    url: Annotated[
        str | None, typer.Option(help="Base URL of the OpenAI-compatible endpoint")
    ] = None,
    model: Annotated[str | None, typer.Option(help="Model name")] = None,
    api_key_env: Annotated[
        str | None, typer.Option("--api-key-env", help="Env var holding the API key")
    ] = None,
    provider: Annotated[
        str, typer.Option(help="Endpoint wire protocol: openai|ollama|tgi")
    ] = "openai",
    adapter: Annotated[
        Path | None,
        typer.Option(
            help="Adapter file mapping a guarded endpoint's custom request/response schema."
        ),
    ] = None,
    system_prompt_file: Annotated[
        Path | None, typer.Option("--system-prompt-file", help="File containing a system prompt")
    ] = None,
    profile: Annotated[Path | None, typer.Option(help="guardana.yaml path")] = None,
    preset: Annotated[str | None, typer.Option(help=PRESET_HELP)] = None,
    format: Annotated[
        OutputFormat, typer.Option(help="human|json|sarif|junit")
    ] = OutputFormat.human,
    rules: Annotated[
        list[Path],
        typer.Option("--rules", help="Directory or file of custom YAML rules; repeatable."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
    concurrency: Annotated[
        int,
        typer.Option(
            min=1, help="How many rules may query the model at once (raises probe throughput)"
        ),
    ] = _DEFAULT_CONCURRENCY,
    reporter: Annotated[
        str | None, typer.Option(help="Collector URL to forward findings to, e.g. server://URL")
    ] = None,
    ai_system: Annotated[
        str | None,
        typer.Option(
            "--ai-system",
            help="Which AI system this run verifies, e.g. support-agent. Never guessed.",
        ),
    ] = None,
    environment: Annotated[
        str | None,
        typer.Option(
            "--environment",
            help="Where it runs, e.g. production. Never guessed from a branch name.",
        ),
    ] = None,
    deployment_id: Annotated[
        str | None,
        typer.Option("--deployment-id", help="Which version of it, if you have an identifier."),
    ] = None,
    mcp: Annotated[
        str | None,
        typer.Option(
            help="MCP server to examine instead of a model: an http(s) URL, or a "
            "command to run with --allow-exec"
        ),
    ] = None,
    allow_exec: Annotated[
        bool,
        typer.Option("--allow-exec", help="Permit --mcp to START the server, executing it"),
    ] = False,
    mcp_token_env: Annotated[
        str | None,
        typer.Option(
            "--mcp-token-env",
            help="Env var holding a bearer token for the MCP server. Needed by the checks "
            "that can only be answered with a credential.",
        ),
    ] = None,
    mcp_pin: Annotated[
        Path | None, typer.Option("--mcp-pin", help="Approved MCP manifest to compare against")
    ] = None,
    write_mcp_pin: Annotated[
        Path | None,
        typer.Option("--write-mcp-pin", help="Write the server's current manifest and exit"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help="Write the report to this file instead of stdout (needed by `guardana diff`).",
        ),
    ] = None,
    max_requests: Annotated[
        int | None, typer.Option("--max-requests", min=1, help="Stop after this many requests.")
    ] = None,
    max_input_tokens: Annotated[
        int | None, typer.Option("--max-input-tokens", min=1, help="Input-token ceiling.")
    ] = None,
    max_output_tokens: Annotated[
        int | None, typer.Option("--max-output-tokens", min=1, help="Output-token ceiling.")
    ] = None,
    max_duration: Annotated[
        str | None, typer.Option("--max-duration", help="Wall-clock ceiling, e.g. 15m.")
    ] = None,
    trials: Annotated[
        int | None,
        typer.Option(
            "--trials",
            min=1,
            help="Attempts per case for rules that grade a sampled reply; overrides `trials:`.",
        ),
    ] = None,
    safety: Annotated[
        str,
        typer.Option(help="How far rules may reach: passive|active|side-effecting"),
    ] = "active",
    allow_destructive: Annotated[
        bool,
        typer.Option(
            "--allow-destructive",
            help="Permit rules that can destroy or alter something the target owns.",
        ),
    ] = False,
    plugins: PluginsOption = None,
    allow_plugin: AllowPluginOption = None,
    target: Annotated[
        str | None,
        typer.Option("--target", help="Installed endpoint target as scheme://locator."),
    ] = None,
    target_option: Annotated[
        list[str],
        typer.Option("--target-option", help="Non-secret key=value for --target; repeatable."),
    ] = [],  # noqa: B006 — typer builds the option from a literal default
) -> None:
    """Run dynamic security checks against a live model endpoint, or an MCP server."""
    check_reporter_url(reporter)
    refuse_incomparable_output(output, format.value)
    deployment = detect_deployment(ai_system, environment, deployment_id)
    prof = resolve_profile(profile, preset)
    prof = replace(
        prof,
        max_impact=parse_impact(safety),
        allow_destructive=allow_destructive,
        budgets=override(
            prof.budgets,
            max_requests=max_requests,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            max_duration=max_duration,
        ),
        trials=prof.trials if trials is None else trials,
    )
    resolved = resolve_trust(plugins, allow_plugin, prof)
    registry = Registry.discover(resolved.trust)
    hint_refused_plugins(registry, resolved)
    try:
        # Validated here, before anything is sent, so a typo exits as invalid usage; the
        # verifier wires the judges again for the run, with fresh meters.
        wire_config_evaluators(Registry(), prof, prof.budgets)
    except BudgetExhausted as exc:
        raise refuse_unenforceable_budget(exc) from exc
    except ProfileError as exc:
        raise refuse_invalid_profile(exc) from exc
    load_custom_rules(registry, prof, rules)
    registry.apply_trials(prof.trials)
    # Read before anything is sent, and once: the rules correct with these while they
    # run, and the manifest records the very same ones.
    calibrations = calibrations_or_exit(prof)

    def verifier(of: Profile) -> Verifier:
        return Verifier(
            trust=resolved.trust,
            profile=of,
            registry=registry,
            calibrations=calibrations,
            concurrency=concurrency,
            judge_endpoint=judge_endpoint,
        )

    def verified(target: Target, of: Profile = prof) -> Verification:
        return _carried_out(
            lambda: verifier(of).run(target, source=detect_source(), deployment=deployment)
        )

    if target is not None:
        conflicting = {
            "--url": url,
            "--model": model,
            "--api-key-env": api_key_env,
            "--adapter": adapter,
            "--system-prompt-file": system_prompt_file,
            "--mcp": mcp,
            "--mcp-token-env": mcp_token_env,
            "--mcp-pin": mcp_pin,
            "--write-mcp-pin": write_mcp_pin,
        }
        used = [name for name, value in conflicting.items() if value is not None]
        if allow_exec:
            used.append("--allow-exec")
        if used:
            raise typer.BadParameter(
                f"--target cannot be combined with {', '.join(used)}; pass target-specific "
                "configuration through --target-option"
            )
        selected = resolve_target(
            registry,
            locator=target,
            options=target_option,
            kind=TargetKind.ENDPOINT,
            fallback=_missing_target,
        )
        custom = run_against_endpoint(
            selected.ref, lambda: verified(selected), accepts=_ACCEPTED_FLAGS
        )
        _finish_probe(
            custom, selected.ref, deployment, format=format, output=output, reporter=reporter
        )
        return

    if target_option:
        raise typer.BadParameter("--target-option needs --target scheme://locator")

    if mcp is not None:
        examined = _carried_out(
            lambda: run_mcp_probe(
                registry,
                prof,
                McpConnection(
                    mcp,
                    allow_exec=allow_exec,
                    pin=mcp_pin,
                    credential=credential_from(mcp_token_env),
                ),
                write_mcp_pin,
                concurrency=concurrency,
                calibrations=calibrations,
                source=detect_source(),
                deployment=deployment,
            )
        )
        if examined is None:
            return
        _finish_probe(
            examined, display_url(mcp), deployment, format=format, output=output, reporter=reporter
        )
        return

    endpoint_url, model_name = require_chat_endpoint(url, model)
    transport: ChatTransport | None = None
    if adapter is not None:
        try:
            transport = HttpAdapterTransport(load_adapter_config(adapter, endpoint_url))
        except EndpointError as exc:
            raise typer.BadParameter(str(exc)) from exc
    # Every pass of the probe — one per planted canary — bills this one meter, so the
    # profile's budgets bound the probe rather than each pass of it.
    selected_endpoint = build_endpoint(
        endpoint_url,
        model_name,
        api_key=os.environ.get(api_key_env) if api_key_env else None,
        system_prompt=(
            system_prompt_file.read_text(encoding="utf-8") if system_prompt_file else None
        ),
        provider=provider,
        transport=transport,
        meter=UsageMeter(prof.budgets),
    )
    probed = run_against_endpoint(
        endpoint_url, lambda: verified(selected_endpoint), accepts=_ACCEPTED_FLAGS
    )
    _finish_probe(
        probed,
        selected_endpoint.ref,
        deployment,
        format=format,
        output=output,
        reporter=reporter,
    )


def _carried_out(run: Callable[[], _Run]) -> _Run:
    """Run, re-raising what stopped it as the error the endpoint helpers explain in words.

    The verifier wraps a failure in its own typed error; the CLI's messages and exit codes
    are written for the failure itself.
    """
    try:
        return run()
    except UnenforceableBudgetError as exc:
        raise refuse_unenforceable_budget(exc) from exc
    except (TargetUnavailableError, JudgeUnreachableError) as exc:
        if exc.__cause__ is not None:
            raise exc.__cause__ from None
        raise


def _missing_target() -> Target:
    """Type-safe fallback that is unreachable when a custom locator is present."""
    raise typer.BadParameter("pass --target scheme://locator")


def _finish_probe(  # noqa: PLR0913 — what the command does with a finished run
    verification: Verification,
    source: str,
    deployment: DeploymentRef,
    *,
    format: OutputFormat,
    output: Path | None,
    reporter: str | None,
) -> None:
    """Emit, forward and gate one probe the verifier finished.

    A judge whose own ceiling stopped the run is named here, which the exit code alone
    cannot: a judge meters its calls apart from the target's, so a run cut short by
    grading would otherwise read as the target's budget running out.
    """
    for stop in verification.judge_stops:
        typer.echo(f"warning: {stop}", err=True)
    run = verification.manifest
    emit(get_renderer(format.value, run=run).render(verification.result), output, format.value)
    if reporter:
        submit_safely(reporter, verification.result, source=source, deployment=deployment, run=run)
    exit_with(verification.gate, verification.result)
