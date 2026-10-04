from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from guardana.cli._a2a_run import connection_from, run_a2a_probe
from guardana.cli._budget_flags import override
from guardana.cli._connection import (
    AdapterOption,
    ApiKeyEnvOption,
    FixturesOption,
    ModelOption,
    ProviderOption,
    SystemPromptFileOption,
    UrlOption,
    endpoint_for,
    read_fixtures,
    read_system_prompt,
    resolve_flags,
    resolve_tenants,
    seeded_endpoint,
)
from guardana.cli._errors import (
    EndpointFlag,
    remedies_for,
    report_target_stop,
    run_against_endpoint,
    run_judged,
)
from guardana.cli._evaluators import judge_endpoint, wire_config_evaluators
from guardana.cli._exit import refuse_invalid_profile, refuse_unenforceable_budget
from guardana.cli._formats import FORMAT_HELP, OutputFormat
from guardana.cli._mcp_run import (
    McpConnection,
    credential_from,
    registry_entry_from,
    require_chat_endpoint,
    run_mcp_probe,
)
from guardana.cli._output import refuse_incomparable_output
from guardana.cli._outputs import RunOutputs, refuse_installed_output_beside, select_outputs
from guardana.cli._plugins import (
    AllowPluginOption,
    PluginsOption,
    hint_refused_plugins,
    resolve_trust,
)
from guardana.cli._profile import PRESET_HELP, resolve_profile
from guardana.cli._reporting import installed_reporter_or_check, submit_safely
from guardana.cli._rules_loading import load_custom_rules
from guardana.cli._run_meta import calibrations_or_exit, detect_deployment, detect_source
from guardana.cli._safety_flags import parse_impact
from guardana.cli._target_locator import resolve_target
from guardana.cli.exit_codes import ExitCode
from guardana.core.budget import BudgetExhausted
from guardana.core.fixtures import Fixtures
from guardana.core.manifest import DeploymentRef
from guardana.core.profile import Profile, ProfileError
from guardana.core.recording import render_recording
from guardana.core.redaction import EvidenceMode
from guardana.core.registry import Registry
from guardana.core.target import EndpointTarget, SeededTarget, Target, TargetKind, display_url
from guardana.core.target.connection import Connection
from guardana.core.usage import UsageMeter
from guardana.core.verify import (
    JudgeUnreachableError,
    TargetUnavailableError,
    UnenforceableBudgetError,
    UnsupportedTargetError,
    Verification,
    Verifier,
    exchanges_path,
)

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


def probe(  # noqa: C901, PLR0913, PLR0915, PLR0917 — Typer surface, target modes
    url: UrlOption = None,
    model: ModelOption = None,
    api_key_env: ApiKeyEnvOption = None,
    provider: ProviderOption = None,
    adapter: AdapterOption = None,
    system_prompt_file: SystemPromptFileOption = None,
    fixtures: FixturesOption = None,
    profile: Annotated[Path | None, typer.Option(help="guardana.yaml path")] = None,
    preset: Annotated[str | None, typer.Option(help=PRESET_HELP)] = None,
    format: Annotated[str, typer.Option(help=FORMAT_HELP)] = "human",
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
        str | None,
        typer.Option(
            help="Collector URL to forward findings to, e.g. server://URL, or an installed "
            "reporter as name://locator"
        ),
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
    mcp_registry_entry: Annotated[
        Path | None,
        typer.Option(
            "--mcp-registry-entry",
            help="The server's registry server.json, to compare its URL and version against.",
        ),
    ] = None,
    a2a: Annotated[
        str | None,
        typer.Option("--a2a", help="A2A agent to examine instead of a model: an http(s) URL"),
    ] = None,
    a2a_token_env: Annotated[
        str | None,
        typer.Option(
            "--a2a-token-env",
            help="Env var holding the first caller's bearer token for the A2A agent.",
        ),
    ] = None,
    a2a_other_token_env: Annotated[
        str | None,
        typer.Option(
            "--a2a-other-token-env",
            help="Env var holding a second, different caller's bearer token; with "
            "--a2a-token-env, settles whether one caller can read another's task.",
        ),
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
    max_requests_per_minute: Annotated[
        int | None,
        typer.Option(
            "--max-requests-per-minute", min=1, help="Send no faster than this many requests."
        ),
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
    keep_exchanges: Annotated[
        bool,
        typer.Option(
            "--keep-exchanges",
            help="Keep every chat exchange, redacted, beside the saved run so "
            "`guardana grade` can grade it again without calling the endpoint.",
        ),
    ] = False,
) -> None:
    """Run dynamic security checks against a live model endpoint, an MCP server or an A2A agent."""
    installed_reporter = installed_reporter_or_check(reporter)
    refuse_installed_output_beside("--write-mcp-pin", write_mcp_pin, format, installed_reporter)
    collector = reporter if installed_reporter is None else None
    refuse_incomparable_output(output, format)
    _refuse_lone_a2a_flags(a2a, a2a_token_env, a2a_other_token_env)
    if mcp_registry_entry is not None and mcp is None:
        raise typer.BadParameter(
            "--mcp-registry-entry describes the MCP server --mcp names; pass --mcp too"
        )
    seeded = _fixtures(fixtures, elsewhere=target is not None or mcp is not None or a2a is not None)
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
            max_requests_per_minute=max_requests_per_minute,
        ),
        trials=prof.trials if trials is None else trials,
    )
    prof = _keeping(prof, keep_exchanges, protocol=mcp or a2a, output=output, format=format)
    resolved = resolve_trust(plugins, allow_plugin, prof)
    outputs = select_outputs(format, installed_reporter, resolved.trust, collector=bool(collector))
    with outputs:
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

        def verifier(of: Profile, secrets: tuple[str, ...]) -> Verifier:
            return Verifier(
                trust=resolved.trust,
                profile=of,
                registry=registry,
                calibrations=calibrations,
                concurrency=concurrency,
                judge_endpoint=judge_endpoint,
                fixtures=None if seeded is None else seeded.record(),
                secrets=secrets,
                remedies=remedies_for(_ACCEPTED_FLAGS),
            )

        def verified(target: Target, secrets: tuple[str, ...] = ()) -> Verification:
            return _carried_out(
                lambda: verifier(prof, secrets).run(
                    target, source=detect_source(), deployment=deployment
                )
            )

        if target is not None:
            conflicting = {
                "--url": url,
                "--model": model,
                "--api-key-env": api_key_env,
                "--provider": provider,
                "--adapter": adapter,
                "--system-prompt-file": system_prompt_file,
                "--mcp": mcp,
                "--mcp-token-env": mcp_token_env,
                "--mcp-pin": mcp_pin,
                "--mcp-registry-entry": mcp_registry_entry,
                "--write-mcp-pin": write_mcp_pin,
                "--a2a": a2a,
                "--a2a-token-env": a2a_token_env,
                "--a2a-other-token-env": a2a_other_token_env,
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
            if prof.privacy.keep_exchanges and not isinstance(
                selected, EndpointTarget | SeededTarget
            ):
                raise typer.BadParameter(
                    f"keeping exchanges keeps the chat exchanges of the built-in endpoint and of a "
                    f"pack's target built on it; {selected.ref} keeps none"
                )
            custom = run_against_endpoint(
                selected.ref,
                lambda: verified(selected),
                privacy=prof.privacy,
                accepts=_ACCEPTED_FLAGS,
            )
            _finish_probe(
                custom,
                selected.ref,
                deployment,
                outputs=outputs,
                output=output,
                collector=collector,
                keep=prof.privacy.keep_exchanges,
            )
            return

        if target_option:
            raise typer.BadParameter("--target-option needs --target scheme://locator")

        if a2a is not None:
            _refuse_beside_a2a(
                {
                    "--url": url,
                    "--model": model,
                    "--api-key-env": api_key_env,
                    "--provider": provider,
                    "--adapter": adapter,
                    "--system-prompt-file": system_prompt_file,
                    "--mcp": mcp,
                    "--mcp-token-env": mcp_token_env,
                    "--mcp-pin": mcp_pin,
                    "--mcp-registry-entry": mcp_registry_entry,
                    "--write-mcp-pin": write_mcp_pin,
                    "--allow-exec": True if allow_exec else None,
                }
            )
            agent = connection_from(a2a, a2a_token_env, a2a_other_token_env)
            examined_agent = run_judged(
                lambda: _carried_out(
                    lambda: run_a2a_probe(
                        registry,
                        prof,
                        agent,
                        concurrency=concurrency,
                        calibrations=calibrations,
                        source=detect_source(),
                        deployment=deployment,
                    )
                )
            )
            _finish_probe(
                examined_agent,
                display_url(a2a),
                deployment,
                outputs=outputs,
                output=output,
                collector=collector,
            )
            return

        if mcp is not None:
            chat_flags = {
                "--url": url,
                "--model": model,
                "--api-key-env": api_key_env,
                "--provider": provider,
                "--adapter": adapter,
                "--system-prompt-file": system_prompt_file,
            }
            chat = [name for name, value in chat_flags.items() if value is not None]
            if chat:
                raise typer.BadParameter(
                    f"--mcp probes an MCP server; {', '.join(chat)} configure a chat endpoint "
                    f"and would be ignored"
                )
            examined = run_judged(
                lambda: _carried_out(
                    lambda: run_mcp_probe(
                        registry,
                        prof,
                        McpConnection(
                            mcp,
                            allow_exec=allow_exec,
                            pin=mcp_pin,
                            credential=credential_from(mcp_token_env),
                            registry_entry=registry_entry_from(mcp_registry_entry),
                        ),
                        write_mcp_pin,
                        concurrency=concurrency,
                        calibrations=calibrations,
                        source=detect_source(),
                        deployment=deployment,
                    )
                )
            )
            if examined is None:
                return
            _finish_probe(
                examined,
                display_url(mcp),
                deployment,
                outputs=outputs,
                output=output,
                collector=collector,
            )
            return

        endpoint_url, model_name = require_chat_endpoint(url, model)
        connection = resolve_flags(
            endpoint_url,
            model_name,
            provider=provider,
            api_key_env=api_key_env,
            adapter=adapter,
            sending=True,
        )
        prompt = read_system_prompt(system_prompt_file)
        # Every pass of the probe — one per planted canary — and every tenant endpoint bills
        # this one meter, so the profile's budgets bound the probe rather than each part of it.
        selected_endpoint = endpoint_for(
            connection, system_prompt=prompt, meter=UsageMeter(prof.budgets)
        )
        subject, tenant_secrets = _seeded(
            selected_endpoint,
            seeded,
            Connection(
                endpoint_url,
                model_name,
                provider=provider,
                api_key_env=api_key_env,
                adapter=adapter,
            ),
            prompt,
        )
        sent = (*connection.secret_values, *tenant_secrets)
        probed = run_against_endpoint(
            endpoint_url,
            lambda: verified(subject, sent),
            privacy=prof.privacy,
            secrets=sent,
            accepts=_ACCEPTED_FLAGS,
        )
        _finish_probe(
            probed,
            selected_endpoint.ref,
            deployment,
            outputs=outputs,
            output=output,
            collector=collector,
            keep=prof.privacy.keep_exchanges,
        )


def _fixtures(path: Path | None, *, elsewhere: bool) -> Fixtures | None:
    """Read `--fixtures`, refusing it beside `--mcp`, `--a2a` or `--target`, which hold none."""
    if path is not None and elsewhere:
        raise typer.BadParameter(
            "--fixtures asks the seeded items through --url, once per tenant; an MCP server, "
            "an A2A agent or a pack's --target holds none"
        )
    return read_fixtures(path)


def _refuse_lone_a2a_flags(
    a2a: str | None, token_env: str | None, other_token_env: str | None
) -> None:
    """Refuse an A2A credential flag given without `--a2a`, which nothing would read."""
    given = [
        name
        for name, value in (
            ("--a2a-token-env", token_env),
            ("--a2a-other-token-env", other_token_env),
        )
        if value is not None
    ]
    if given and a2a is None:
        raise typer.BadParameter(f"{', '.join(given)} names a credential for --a2a; pass --a2a URL")


def _refuse_beside_a2a(flags: dict[str, object]) -> None:
    """Refuse the flags that configure another target beside `--a2a`; they would be ignored."""
    used = [name for name, value in flags.items() if value is not None]
    if used:
        raise typer.BadParameter(
            f"--a2a probes an A2A agent; {', '.join(used)} configure another target and "
            f"would be ignored"
        )


def _seeded(
    endpoint: EndpointTarget, fixtures: Fixtures | None, written: Connection, prompt: str | None
) -> tuple[Target, tuple[str, ...]]:
    """Return the endpoint, or with `--fixtures` the seeded target over it and every tenant.

    The second item holds the secrets the tenants send, which no message may quote.
    """
    if fixtures is None:
        return endpoint, ()
    tenants = resolve_tenants(fixtures, written, sending=True)
    secrets = tuple(value for tenant in tenants for value in tenant.connection.secret_values)
    return seeded_endpoint(endpoint, fixtures, tenants, system_prompt=prompt), secrets


def _carried_out(run: Callable[[], _Run]) -> _Run:
    """Run, re-raising what stopped it as the error the endpoint helpers explain in words.

    The verifier wraps a failure in its own typed error; the CLI's messages and exit codes
    are written for the failure itself.
    """
    try:
        return run()
    except UnenforceableBudgetError as exc:
        raise refuse_unenforceable_budget(exc) from exc
    except UnsupportedTargetError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=ExitCode.INVALID_USAGE) from exc
    except (TargetUnavailableError, JudgeUnreachableError) as exc:
        if exc.__cause__ is not None:
            raise exc.__cause__ from None
        raise


def _keeping(
    prof: Profile,
    flag: bool,
    *,
    protocol: str | None,
    output: Path | None,
    format: str,
) -> Profile:
    """Turn `--keep-exchanges` into the profile switch and refuse what it cannot honour.

    Kept exchanges are written beside the saved run, so a run that writes none would keep
    them nowhere; and an MCP server or an A2A agent (`protocol`) has no chat exchanges to
    keep. A `--target` is checked once it is built, since only a target built on the
    endpoint keeps them.
    """
    if flag:
        if prof.privacy.mode is EvidenceMode.METADATA_ONLY:
            raise typer.BadParameter(
                "--keep-exchanges keeps replies, which privacy.evidence_mode: metadata_only "
                "withholds; drop one of the two"
            )
        prof = replace(prof, privacy=replace(prof.privacy, keep_exchanges=True))
    if not prof.privacy.keep_exchanges:
        return prof
    if protocol is not None:
        raise typer.BadParameter(
            "keeping exchanges keeps the chat exchanges of --url (with or without --adapter) "
            "or of a pack's --target built on the endpoint; an MCP server or an A2A agent "
            "keeps none"
        )
    if output is None or format != OutputFormat.json:
        raise typer.BadParameter(
            "kept exchanges are written beside the saved run: pass --format json --output run.json"
        )
    return prof


def _missing_target() -> Target:
    """Type-safe fallback that is unreachable when a custom locator is present."""
    raise typer.BadParameter("pass --target scheme://locator")


def _finish_probe(  # noqa: PLR0913 — what the command does with a finished run
    verification: Verification,
    source: str,
    deployment: DeploymentRef,
    *,
    outputs: RunOutputs,
    output: Path | None,
    collector: str | None,
    keep: bool = False,
) -> None:
    """Emit, forward and gate one probe the verifier finished.

    A judge whose own ceiling stopped the run is named here, which the exit code alone
    cannot: a judge meters its calls apart from the target's, so a run cut short by
    grading would otherwise read as the target's budget running out. A run its target
    stopped is saved, kept and forwarded as any other, and what the target did is named,
    also when a failed format or reporter boundary ends the command first.
    """
    for stop in verification.judge_stops:
        typer.echo(f"warning: {stop}", err=True)
    try:
        outputs.write(verification, output)
        _write_exchanges(verification, output, keep=keep)
        if collector:
            submit_safely(
                collector,
                verification.result,
                source=source,
                deployment=deployment,
                run=verification.manifest,
            )
        outputs.deliver(verification)
    except typer.Exit:
        report_target_stop(verification)
        raise
    report_target_stop(verification)
    outputs.end(verification)


def _write_exchanges(verification: Verification, output: Path | None, *, keep: bool) -> None:
    """Write the exchanges the run kept beside its saved run, and say where and how many."""
    kept = verification.exchanges
    record = verification.manifest.exchanges
    if output is None or kept is None or record is None:
        if output is not None and exchanges_path(output).exists():
            # The run beside it was just overwritten; left in place, the old exchanges
            # would read as this run's.
            exchanges_path(output).unlink()
            typer.echo(
                f"removed {exchanges_path(output)}, which an earlier run at this path kept",
                err=True,
            )
        if keep and output is not None:
            typer.echo(
                "warning: nothing was kept — no rule finished a chat exchange in the plain pass",
                err=True,
            )
        return
    path = exchanges_path(output)
    path.write_text(render_recording(kept), encoding="utf-8")
    altered = (
        f"; {record.altered} reply(ies) changed by redaction, which `guardana grade` will not grade"
        if record.altered
        else ""
    )
    typer.echo(f"kept {record.count} exchange(s) in {path}{altered}", err=True)
