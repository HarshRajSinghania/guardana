"""The format a run writes and the installed reporter it delivers to, chosen before the run.

Selection runs before discovery and before anything is sent, so every refusal is an
exit `3` that cost nothing. From the moment a reporter is prepared, `RunOutputs` guards
its delivery line: the command prints exactly one, whether it delivered or ended first.
"""

from pathlib import Path
from types import TracebackType
from typing import NoReturn, Self

import typer
from guardana.cli._exit import exit_with
from guardana.cli._formats import OutputFormat, format_name, is_built_in_format, resolve_format
from guardana.cli._output import emit
from guardana.cli._plugins import admission_forms
from guardana.cli._reporting import split_reporter
from guardana.cli.exit_codes import ExitCode, code_for
from guardana.core.budget import BudgetExhausted
from guardana.core.origin import Origin
from guardana.core.output import (
    Delivery,
    DeliveryStatus,
    OutputError,
    OutputSelectionError,
    OutputSelectionKind,
    PreparedReporter,
    SelectedRenderer,
    deliver,
    format_delivery_line,
    render,
    sanitise_reason,
    select_reporter,
)
from guardana.core.plugins import PluginTrust
from guardana.core.verify import UnenforceableBudgetError, Verification
from guardana.report import get_renderer

MONITOR_REFUSAL = (
    "monitor runs cycles, not a saved run; an installed reporter runs with scan, probe or "
    "analyze-trace"
)
"""Why `monitor` refuses an installed reporter."""

IMPORT_REFUSAL = "import-observations loads no plugins; it forwards to the collector only"
"""Why `import-observations` refuses an installed reporter."""

NOT_PRODUCED = "the run's report was not produced"


def refuse_selection(exc: OutputSelectionError) -> typer.Exit:
    """Print a refused selection as `error: <message>` and return the exit `3` to raise.

    A trust refusal is followed by the ways to admit the distribution, narrowest first.
    """
    lines = [f"error: {exc.message}"]
    if exc.kind is OutputSelectionKind.REFUSED:
        first, *rest = admission_forms(list(exc.distributions))
        lines.append(f"  to load it, state the trust, narrowest first: {first}")
        lines.extend(f"    or {form}" for form in rest)
    typer.echo("\n".join(lines), err=True)
    return typer.Exit(code=ExitCode.INVALID_USAGE)


def _unsupported(name: str, message: str) -> typer.Exit:
    return refuse_selection(OutputSelectionError(OutputSelectionKind.UNSUPPORTED, name, message))


def refuse_installed_reporter(reporter: str | None, why: str) -> None:
    """Exit `3` when `reporter` names an installed reporter this command cannot run.

    Decided from the value alone: no metadata is read and nothing is imported.
    """
    split = split_reporter(reporter)
    if split is not None:
        raise _unsupported(split[0], why)


def refuse_installed_output_beside(
    flag: str, given: object, output_format: str, reporter: tuple[str, str] | None
) -> None:
    """Exit `3` when `flag` was `given` beside an installed format or reporter.

    The flag makes the command write something other than the run's report, which an
    installed output needs.
    """
    if given is None:
        return
    if reporter is not None:
        name = reporter[0]
    elif not is_built_in_format(output_format):
        name = output_format
    else:
        return
    raise _unsupported(
        name, f"an installed output needs the run's report, which {flag} does not produce"
    )


def select_outputs(
    output_format: str, reporter: tuple[str, str] | None, trust: PluginTrust
) -> "RunOutputs":
    """Select the format and the installed reporter under `trust`, or exit `3` saying why.

    `reporter` is what `split_reporter` returned; a collector value is not selected here.
    """
    try:
        chosen = resolve_format(output_format, trust)
        prepared = None if reporter is None else select_reporter(reporter[0], reporter[1], trust)
    except OutputSelectionError as exc:
        raise refuse_selection(exc) from exc
    return RunOutputs(chosen, prepared)


def _distribution(origin: Origin) -> str:
    return origin.describe() if origin.distribution is not None else "an unnamed distribution"


def _why(exc: BaseException | None) -> str:
    """Say why a command that ended before delivering sent nothing."""
    if isinstance(exc, KeyboardInterrupt):
        return "the run was interrupted"
    if isinstance(exc, typer.Exit):
        if isinstance(exc.__cause__, BudgetExhausted | UnenforceableBudgetError):
            return "the budget was refused before sending"
        if exc.exit_code == ExitCode.TARGET_UNAVAILABLE:
            return "the target or judge was unavailable"
        if exc.exit_code == ExitCode.INVALID_USAGE:
            return "the run was refused before sending"
    if isinstance(exc, typer.BadParameter):
        return "the run was refused before sending"
    return "the run ended before its report was produced"


class RunOutputs:
    """What one run writes and where it delivers, and the guard of its delivery line.

    Entered right after selection: a command that leaves the block without delivering
    prints `delivery: not_sent` with the reason, never twice and never after a delivery.
    """

    def __init__(
        self, chosen: OutputFormat | SelectedRenderer, reporter: PreparedReporter | None
    ) -> None:
        self.format = chosen
        self.reporter = reporter
        self._delivery: Delivery | None = None
        self._settled = reporter is None
        self._delivering = False

    @property
    def format_name(self) -> str:
        """The name the format was selected by."""
        return format_name(self.format)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._settled:
            return
        if self._delivering:
            # Interrupted mid-delivery: whether anything left the machine is not known.
            self._line(Delivery(DeliveryStatus.UNKNOWN, detail="the run was interrupted"))
            return
        self.not_sent(_why(exc))

    def not_sent(self, why: str) -> None:
        """Print the `not_sent` line once, if a reporter was selected and nothing settled it."""
        if self._settled:
            return
        self._line(Delivery(DeliveryStatus.NOT_SENT, detail=why))

    def _line(self, delivery: Delivery) -> None:
        self._settled = True
        if self.reporter is not None:
            line = format_delivery_line(self.reporter.name, self.reporter.destination, delivery)
            typer.echo(line, err=True)

    def write(self, verification: Verification, output: Path | None) -> None:
        """Render the run in the selected format and print it or write it to `output`.

        An installed format that fails ends the command: the verdict is printed, nothing is
        written, and the exit is `8` unless the run stopped.
        """
        name = self.format_name
        if isinstance(self.format, OutputFormat):
            renderer = get_renderer(name, run=verification.manifest)
            self._emit(renderer.render(verification.result), output, verbatim=False)
            return
        try:
            rendered = render(self.format, verification)
        except OutputError as exc:
            self._failed(exc, verification)
        self._emit(rendered, output, verbatim=True)

    def _emit(self, rendered: str, output: Path | None, *, verbatim: bool) -> None:
        try:
            emit(rendered, output, self.format_name, verbatim=verbatim)
        except typer.Exit:
            self.not_sent("the run's report could not be written")
            raise

    def _failed(self, exc: OutputError, verification: Verification) -> NoReturn:
        verdict = code_for(verification.gate, verification.result.stopped_by)
        owner = exc.origin.distribution or "the distribution that installed it"
        typer.echo(f"the run's verdict: {verification.gate} (exit {int(verdict)})", err=True)
        typer.echo(
            f"error: the format {exc.name} from {_distribution(exc.origin)} failed: "
            f"{sanitise_reason(exc.reason)} — nothing was written; report it to {owner}",
            err=True,
        )
        self.not_sent(NOT_PRODUCED)
        raise typer.Exit(code=_output_failed(verification))

    def deliver(self, verification: Verification) -> Delivery | None:
        """Deliver the run to the selected reporter and print its line; None without a reporter."""
        if self.reporter is None:
            return None
        self._delivering = True
        delivery = deliver(self.reporter, verification)
        self._delivering = False
        self._line(delivery)
        self._delivery = delivery
        return delivery

    def end(self, verification: Verification) -> None:
        """End with the run's code, or `8` when the reporter failed and no stop outranks it."""
        if self._delivery is not None and self._delivery.status is DeliveryStatus.UNKNOWN:
            raise typer.Exit(code=_output_failed(verification))
        exit_with(verification.gate, verification.result)


def _output_failed(verification: Verification) -> ExitCode:
    """Return `8`, or the stop's code when the run stopped: a stop outranks the output."""
    if verification.result.stopped_by is not None:
        return code_for(verification.gate, verification.result.stopped_by)
    return ExitCode.OUTPUT_FAILED


__all__ = [
    "IMPORT_REFUSAL",
    "MONITOR_REFUSAL",
    "NOT_PRODUCED",
    "RunOutputs",
    "refuse_installed_output_beside",
    "refuse_installed_reporter",
    "refuse_selection",
    "select_outputs",
]
