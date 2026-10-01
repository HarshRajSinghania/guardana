"""Run Guardana from Python the way the CLI runs it, and get typed results for every outcome.

`Verifier` holds what a run is configured with — the plugin trust, the profile, local and
in-code rules and evaluators, calibrations — and `Verifier.scan` or `Verifier.run`
returns a `Verification`: the redacted result, the saved-run manifest, the gate's
verdict and the exit code the CLI would use. A run that fails, stays indeterminate or is
stopped by its budget is returned like one that passed; only a run that could not be
carried out raises, with a `VerificationError`.

`guardana scan` and `guardana probe` call this module, so a run from Python and a run
from the command line compose the same steps in the same order.
"""

import json
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError

from guardana.core.budget import BudgetExhausted
from guardana.core.calibration.store import CalibrationStoreError, RecordedCalibration
from guardana.core.evaluator.base import Evaluator
from guardana.core.evaluator.config import (
    EndpointBuilder,
    JudgeMeters,
    JudgeUnavailableError,
    default_endpoint_builder,
    wire_config_evaluators,
)
from guardana.core.gate import GateOutcome, OpenQuestion, exit_code_for, gate_outcome
from guardana.core.gate import open_questions as _open_questions
from guardana.core.manifest.build import (
    build_run_manifest,
    load_profile_calibrations,
    target_identity,
)
from guardana.core.manifest.identity import DeploymentRef, RunSource, TargetIdentity
from guardana.core.manifest.model import RunManifest
from guardana.core.manifest.usage import JudgeUsage
from guardana.core.plugins import PluginTrust
from guardana.core.probe import run_target_probe
from guardana.core.profile import Profile, default_profile
from guardana.core.redaction import EvidenceRedactor
from guardana.core.registry import Registry
from guardana.core.report import ScanResult
from guardana.core.report.baseline import Baseline, apply_baseline
from guardana.core.report.location import relativize, relativize_findings
from guardana.core.report.serialize import run_to_dict
from guardana.core.rule import Rule
from guardana.core.runner import DEFAULT_ENDPOINT_CONCURRENCY, Runner
from guardana.core.target import ArtifactTarget, EndpointError, Target, TargetKind
from guardana.core.target.mcp import McpServerTarget


class VerificationError(Exception):
    """A run that could not be carried out, so there is no result to return."""


class TargetUnavailableError(VerificationError):
    """The target could not be reached, before or during the run; nothing partial is kept."""


class JudgeUnreachableError(VerificationError):
    """A judge configured under `evaluators:` could not be reached during the run."""


class UnenforceableBudgetError(VerificationError):
    """The profile sets a budget this target or judge cannot enforce, refused before sending."""


class CalibrationError(VerificationError):
    """A calibration file the run was pointed at cannot be read."""


class UnsupportedTargetError(VerificationError):
    """A target this facade does not run, refused rather than run without what it needs."""


class TargetReusedError(VerificationError):
    """A target that already ran, so its usage, budgets or cached reads would describe two runs."""


_RAN: "weakref.WeakValueDictionary[int, Target]" = weakref.WeakValueDictionary()
"""Every live target this module has run, by identity; a target is refused the second time."""


@dataclass(frozen=True, slots=True)
class Verification:
    """One run as typed data: what it found, how it describes itself, and what it concluded.

    `result` is redacted under the profile's privacy policy and has its baseline applied;
    `manifest` is the run's saved-run description. Both are the halves of the document
    `guardana scan --format json --output` writes, which `document()` returns.
    """

    result: ScanResult
    manifest: RunManifest
    gate: GateOutcome
    judge_usage: Mapping[str, JudgeUsage] | None = None
    """What each judge configured under `evaluators:` spent, or None when none was."""

    judge_stops: tuple[str, ...] = ()
    """Each judge whose own ceiling stopped the run, in the words the CLI prints."""

    @property
    def exit_code(self) -> int:
        """The exit code `guardana` gives this result: 0, 1, 2 or 6."""
        return exit_code_for(self.gate, self.result.stopped_by)

    @property
    def passed(self) -> bool:
        """Whether the gate passed. Anything else — a failure, an open question — is False."""
        return self.gate is GateOutcome.PASS

    @property
    def open_questions(self) -> tuple[OpenQuestion, ...]:
        """Every fact in the result that leaves part of the run's question unanswered."""
        return _open_questions(self.result)

    def document(self) -> dict[str, object]:
        """Return the saved-run document, in the current run schema, as a JSON-ready dict."""
        return run_to_dict(self.result, self.manifest)

    def save(self, path: Path) -> None:
        """Write the saved-run document to `path`, as `--format json --output` does."""
        path.write_text(json.dumps(self.document(), indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Verifier:
    """What a run is configured with; one `Verifier` can run several targets in turn.

    `trust` is required: which installed distributions may run code in this process is
    a decision, never a default. `profile` defaults to `default_profile()`, which
    redacts evidence. `rule_paths` load local YAML rules beside the profile's own
    `rules.paths`; `rules` and `evaluators` register objects built in code.
    `calibrations` default to the files the profile names. `concurrency` bounds an
    endpoint run, as `probe --concurrency` does.

    `registry` is for a caller that assembled its own: nothing is discovered or loaded
    into it, so it cannot be combined with `rule_paths`, `rules` or `evaluators`, and
    the profile's `rules.paths` are not loaded either; the caller loads them on it. The
    trust it was discovered under is the one in force and the one the run records.
    Each run works on a copy that gets the profile's trials and the judges configured
    under `evaluators:`, so the registry itself is never changed.
    """

    trust: PluginTrust
    profile: Profile = field(default_factory=default_profile)
    rule_paths: Sequence[Path] = ()
    rules: Sequence[Rule] = ()
    evaluators: Sequence[Evaluator] = ()
    calibrations: Mapping[str, RecordedCalibration] | None = None
    concurrency: int = DEFAULT_ENDPOINT_CONCURRENCY
    registry: Registry | None = None
    judge_endpoint: EndpointBuilder = default_endpoint_builder
    """How the endpoint of each judge under `evaluators:` is built from its url, model and key."""

    _prepared: list[Registry] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Refuse arguments a registry given whole would silently leave out."""
        if self.registry is not None and (self.rule_paths or self.rules or self.evaluators):
            raise ValueError(
                "a Verifier given a registry loads nothing into it: register the rules, "
                "evaluators and rule directories on that registry instead"
            )

    def _registry(self) -> Registry:
        if self.registry is not None:
            return self.registry
        if not self._prepared:
            registry = Registry.discover(self.trust)
            for rule in self.rules:
                registry.register_rule(rule)
            for evaluator in self.evaluators:
                registry.register_evaluator(evaluator)
            registry.load_yaml_rule_dirs(
                [Path(path) for path in self.profile.rule_paths] + list(self.rule_paths)
            )
            self._prepared.append(registry)
        return self._prepared[0]

    def scan(
        self,
        path: Path,
        *,
        relative_to: Path | None = None,
        baseline: Baseline | None = None,
        source: RunSource | None = None,
        deployment: DeploymentRef | None = None,
    ) -> Verification:
        """Scan a file or directory with the artifact rules, as `guardana scan PATH` does.

        `relative_to` rewrites file paths in findings, observations and the listing
        relative to that directory, as the CLI does against its working directory; left
        out, they stay as given. A path that does not exist raises `FileNotFoundError`:
        a scan of a typo would find nothing and pass.
        """
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist, so there is nothing to scan")
        target = ArtifactTarget(path, excludes=self.profile.path_excludes)
        reference = target.ref if relative_to is None else relativize(target.ref, relative_to)
        return self._verify(
            target,
            reference=reference,
            relative_to=relative_to,
            baseline=baseline,
            source=source,
            deployment=deployment,
        )

    def run(
        self,
        target: Target,
        *,
        relative_to: Path | None = None,
        baseline: Baseline | None = None,
        source: RunSource | None = None,
        deployment: DeploymentRef | None = None,
    ) -> Verification:
        """Run every applicable rule against `target` and return what the run concluded.

        An endpoint target gets one pass per canary rule with a fresh canary planted,
        when it can plant one. A trace target is refused with `UnsupportedTargetError`:
        its unreadable records and its contracts are read by `guardana analyze-trace`.
        `relative_to` rewrites file paths in what the run found, never the target's own
        reference, which a third-party target owns. The caller owns the target, and
        closes it. A target runs once: a second run raises `TargetReusedError`, because
        its meter and whatever it cached would describe both runs.
        """
        return self._verify(
            target,
            reference=target.ref,
            relative_to=relative_to,
            baseline=baseline,
            source=source,
            deployment=deployment,
        )

    def _verify(  # noqa: PLR0913 — the finish step's inputs, keyword-only
        self,
        target: Target,
        *,
        reference: str,
        relative_to: Path | None,
        baseline: Baseline | None,
        source: RunSource | None,
        deployment: DeploymentRef | None,
    ) -> Verification:
        if target.kind is TargetKind.TRACE:
            raise UnsupportedTargetError(
                f"{target.ref} is a trace; run `guardana analyze-trace`, which reads its "
                f"unreadable records and its contracts"
            )
        spent = target.usage()
        if spent is not None and spent.requests:
            raise TargetReusedError(
                f"{target.ref} already sent {spent.requests} request(s); build a fresh target "
                f"for each run so its usage and budgets describe this run alone"
            )
        _refuse_a_second_run(target)
        calibrations = self._calibrations()
        registry = self._registry().copied()
        registry.apply_trials(self.profile.trials)
        endpoint = target.kind is TargetKind.ENDPOINT
        judges = self._judges(registry) if endpoint else JudgeMeters()
        started_at = datetime.now(UTC)
        sent = True
        try:
            result, identity = self._execute(target, registry, calibrations, endpoint=endpoint)
        except UnenforceableBudgetError:
            sent = False
            raise
        finally:
            # A budget refused before the first request leaves the target unused.
            if sent:
                _remember_run(target)
        return self._finish(
            registry,
            result,
            target,
            identity=identity if reference == target.ref else target_identity(target, reference),
            reference=reference,
            relative_to=relative_to,
            baseline=baseline,
            started_at=started_at,
            concurrency=self.concurrency if endpoint else 1,
            calibrations=calibrations,
            judges=judges,
            source=source,
            deployment=deployment,
        )

    def _calibrations(self) -> Mapping[str, RecordedCalibration]:
        if self.calibrations is not None:
            return self.calibrations
        try:
            return load_profile_calibrations(self.profile)
        except CalibrationStoreError as exc:
            raise CalibrationError(str(exc)) from exc

    def _judges(self, registry: Registry) -> JudgeMeters:
        try:
            return wire_config_evaluators(
                registry, self.profile, self.profile.budgets, build=self.judge_endpoint
            )
        except BudgetExhausted as exc:
            raise UnenforceableBudgetError(str(exc)) from exc

    def _execute(
        self,
        target: Target,
        registry: Registry,
        calibrations: Mapping[str, RecordedCalibration],
        *,
        endpoint: bool,
    ) -> tuple[ScanResult, TargetIdentity]:
        records = {key: value.as_record() for key, value in calibrations.items()}
        try:
            if endpoint and not isinstance(target, McpServerTarget):
                probed = run_target_probe(
                    registry,
                    self.profile,
                    target,
                    concurrency=self.concurrency,
                    calibrations=records,
                )
                return probed.result, probed.identity
            runner = Runner(
                registry=registry,
                profile=self.profile,
                concurrency=self.concurrency if endpoint else 1,
                calibrations=records,
            )
            return runner.run(target), target_identity(target, target.ref)
        except BudgetExhausted as exc:
            raise UnenforceableBudgetError(str(exc)) from exc
        except JudgeUnavailableError as exc:
            raise JudgeUnreachableError(str(exc)) from exc
        except (URLError, EndpointError) as exc:
            raise TargetUnavailableError(f"could not reach {target.ref}: {exc}") from exc
        except OSError as exc:
            if not endpoint:
                raise
            raise TargetUnavailableError(f"could not reach {target.ref}: {exc}") from exc

    def _finish(  # noqa: PLR0913 — one value per persisted execution fact
        self,
        registry: Registry,
        result: ScanResult,
        target: Target,
        *,
        identity: TargetIdentity,
        reference: str,
        relative_to: Path | None,
        baseline: Baseline | None,
        started_at: datetime,
        concurrency: int,
        calibrations: Mapping[str, RecordedCalibration],
        judges: JudgeMeters,
        source: RunSource | None,
        deployment: DeploymentRef | None,
    ) -> Verification:
        """Relativize, redact, apply the baseline, gate and describe — in that order.

        Redaction comes before the baseline because a waiver's fingerprint is taken from
        the redacted evidence; the gate reads the waived result; the manifest records
        the gate.
        """
        if relative_to is not None:
            result = relativize_findings(result, relative_to)
        result = EvidenceRedactor(self.profile.privacy).redact_result(result)
        if baseline is not None:
            result = apply_baseline(result, baseline.active())
        gate = gate_outcome(result, self.profile.policy)
        manifest = build_run_manifest(
            registry,
            self.profile,
            result,
            target_kind=target.kind,
            target_ref=reference,
            gate=gate,
            started_at=started_at,
            identity=identity,
            concurrency=concurrency,
            deployment=deployment,
            source=source,
            calibrations=calibrations,
            judge_usage=judges.usage(),
        )
        return Verification(
            result=result,
            manifest=manifest,
            gate=gate,
            judge_usage=judges.usage(),
            judge_stops=judges.stops(),
        )


def _refuse_a_second_run(target: Target) -> None:
    """Refuse a target that already ran here, whose cached listing would describe a past run."""
    if _RAN.get(id(target)) is target:
        raise TargetReusedError(
            f"{target.ref} already ran; build a fresh target for each run so what it "
            f"lists and reads describes this run alone"
        )


def _remember_run(target: Target) -> None:
    """Record that `target` ran; one that cannot be weakly referenced keeps only its meter check."""
    try:
        _RAN[id(target)] = target
    except TypeError:
        return


__all__ = [
    "CalibrationError",
    "EndpointBuilder",
    "JudgeUnreachableError",
    "TargetReusedError",
    "TargetUnavailableError",
    "UnenforceableBudgetError",
    "UnsupportedTargetError",
    "Verification",
    "VerificationError",
    "Verifier",
]
