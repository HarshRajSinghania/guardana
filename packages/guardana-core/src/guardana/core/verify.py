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

import hashlib
import json
import threading
import uuid
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
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
from guardana.core.fingerprint import DigestKind, DocumentDigest
from guardana.core.gate import GateOutcome, OpenQuestion, exit_code_for, gate_outcome
from guardana.core.gate import open_questions as _open_questions
from guardana.core.keeping import ExchangeKeeper
from guardana.core.manifest.build import (
    ConnectionFacts,
    build_run_manifest,
    load_profile_calibrations,
    target_identity,
)
from guardana.core.manifest.identity import DeploymentRef, RunSource, TargetIdentity
from guardana.core.manifest.model import RunManifest
from guardana.core.manifest.records import (
    ExchangesRecord,
    RecordingOriginRecord,
    RecordingRecord,
)
from guardana.core.manifest.usage import JudgeUsage
from guardana.core.plugins import PluginTrust
from guardana.core.probe import run_target_probe
from guardana.core.profile import Profile, default_profile
from guardana.core.recording import (
    Recording,
    RecordingError,
    RecordingOrigin,
    read_recording,
    render_recording,
)
from guardana.core.redaction import EvidenceRedactor
from guardana.core.registry import Registry
from guardana.core.report import ScanResult
from guardana.core.report.baseline import Baseline, apply_baseline
from guardana.core.report.location import relativize, relativize_findings
from guardana.core.report.serialize import run_to_dict
from guardana.core.rule import Rule
from guardana.core.runner import DEFAULT_ENDPOINT_CONCURRENCY, Runner, select_rules
from guardana.core.target import ArtifactTarget, EndpointError, Target, TargetKind
from guardana.core.target.adapter import HttpAdapterTransport
from guardana.core.target.endpoint import EndpointTarget
from guardana.core.target.mcp import McpServerTarget
from guardana.core.target.recorded import RecordedTarget


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


class RecordingRefusedError(VerificationError):
    """A recording that cannot be graded as asked: unreadable, or kept at other trials."""


class TargetReusedError(VerificationError):
    """A target that already ran, so its usage, budgets or cached reads would describe two runs."""


_KEPT_NAME = "guardana-probe"
"""The name a probe's sidecar recording carries; its version is the run id."""

_NAMED_AT_MOST = 3
"""How many differing rules a refusal names before it says there are more."""

_CANARY_PROBE = "GUARDANA_CANARY_PLANNING"
"""A stand-in token, only to ask a rule whether it plants a canary."""

_RAN: "weakref.WeakValueDictionary[int, Target]" = weakref.WeakValueDictionary()
"""Every live target this module has run, by identity; a target is refused the second time."""
_RAN_LOCK = threading.Lock()


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

    exchanges: Recording | None = None
    """The chat exchanges the run kept under `privacy.keep_exchanges`, redacted, or None.

    `manifest.exchanges` records the digest of `render_recording(exchanges)`, which is what
    `save()` writes beside the run.
    """

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
        """Write the saved-run document to `path`, as `--format json --output` does.

        Kept exchanges go to `exchanges_path(path)` beside it; a file there from an earlier
        run is removed when this one kept none, so it never reads as this run's.
        """
        path.write_text(json.dumps(self.document(), indent=2) + "\n", encoding="utf-8")
        sidecar = exchanges_path(path)
        if self.exchanges is not None:
            sidecar.write_text(render_recording(self.exchanges), encoding="utf-8")
        elif sidecar.exists():
            sidecar.unlink()


def exchanges_path(run: Path) -> Path:
    """Where the exchanges a run kept are written beside it: `run.json` → `run.exchanges.jsonl`."""
    stem = run.stem if run.suffix == ".json" else run.name
    return run.with_name(f"{stem}.exchanges.jsonl")


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
    """How the endpoint of each judge under `evaluators:` is built from its url, model and key.

    Only the default builder honours a judge block's `provider` or `adapter`; with
    a builder of your own, such a block raises `ProfileError` before anything is sent,
    rather than building that judge on the OpenAI wire.
    """

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
        closes it. A target runs once: a second run, or one started while the first is
        under way, raises `TargetReusedError`, because its meter and whatever it cached
        would describe both runs. A run refused before anything was sent, over its
        calibrations or a budget, leaves the target free; a target that cannot be weakly
        referenced is checked by its meter alone.
        """
        return self._verify(
            target,
            reference=target.ref,
            relative_to=relative_to,
            baseline=baseline,
            source=source,
            deployment=deployment,
        )

    def grade(
        self,
        path: Path,
        *,
        source: RunSource | None = None,
        deployment: DeploymentRef | None = None,
    ) -> Verification:
        """Grade the answers a recording holds, as `guardana grade RECORDING` does; nothing is sent.

        The recording is the execution: its digest becomes `target.document` and its own
        description the manifest's `recording`. Rules run against a `RecordedTarget`, so a
        question the recording does not answer, or a reply redaction altered, is never a
        pass. A recording that cannot be read, or that a probe kept at different trials per
        case than this profile runs, raises `RecordingRefusedError` before anything runs.
        """
        try:
            recording = read_recording(path)
        except RecordingError as exc:
            raise RecordingRefusedError(str(exc)) from exc
        return self.run(RecordedTarget(recording), source=source, deployment=deployment)

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
        keeping = self._keeps(target)
        spent = target.usage()
        if spent is not None and spent.requests:
            raise TargetReusedError(
                f"{target.ref} already sent {spent.requests} request(s); build a fresh target "
                f"for each run so its usage and budgets describe this run alone"
            )
        _claim(target)
        keeper = None
        try:
            calibrations = self._calibrations()
            registry = self._registry().copied()
            registry.apply_trials(self.profile.trials)
            if isinstance(target, RecordedTarget):
                refuse_other_trials(target.recording, registry)
            endpoint = target.kind is TargetKind.ENDPOINT
            judges = self._judges(registry) if endpoint else JudgeMeters()
            if keeping is not None:
                keeper = ExchangeKeeper()
                keeping.keep_exchanges(keeper)
            planned = self._kept_plan(registry, target) if keeper is not None else None
            started_at = datetime.now(UTC)
            result, identity = self._execute(target, registry, calibrations, endpoint=endpoint)
        except (CalibrationError, UnenforceableBudgetError, RecordingRefusedError):
            # Each is refused before the first request, which leaves the target unused.
            if keeping is not None:
                keeping.stop_keeping()
            _release(target)
            raise
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
            kept=None if keeper is None or planned is None else (keeper, planned),
        )

    def _keeps(self, target: Target) -> EndpointTarget | None:
        """Return the endpoint whose exchanges this run keeps, refusing one that cannot keep them.

        Only an endpoint run has chat exchanges, and a recording is already what it answers
        from. The built-in endpoint keeps them through its per-rule views; any other endpoint
        target would keep nothing while the run said it kept everything, so it is refused
        before anything is sent.
        """
        if (
            not self.profile.privacy.keep_exchanges
            or target.kind is not TargetKind.ENDPOINT
            or isinstance(target, RecordedTarget)
        ):
            return None
        if not isinstance(target, EndpointTarget):
            raise UnsupportedTargetError(
                f"privacy.keep_exchanges keeps the chat exchanges of the built-in endpoint "
                f"target (`--url`, `--adapter`); {target.ref} is a {type(target).__name__}, "
                f"which keeps none"
            )
        return target

    def _kept_plan(self, registry: Registry, target: Target) -> dict[str, int]:
        """Return each rule the plain pass plans, with its trials per case.

        A rule that plants a canary runs in a planted pass whose exchanges are never kept,
        so it is left out: a regrade cannot plant one either.
        """
        chosen, _ = select_rules(registry, self.profile, target)
        return {
            rule.meta.id: rule.trials_per_case
            for rule in chosen
            if rule.with_canary(_CANARY_PROBE) is None
        }

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
        kept: tuple[ExchangeKeeper, dict[str, int]] | None = None,
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
        run_id = str(uuid.uuid4())
        exchanges = (
            None
            if kept is None
            else self._kept_recording(
                kept,
                run_id=run_id,
                subject=reference,
                started_at=started_at,
                gate=gate,
                result=result,
            )
        )
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
            exchanges=None if exchanges is None else _exchanges_record(exchanges),
            recording=_recording_record(target.recording)
            if isinstance(target, RecordedTarget)
            else None,
            run_id=run_id,
            connection=_connection_facts(target),
        )
        return Verification(
            result=result,
            manifest=manifest,
            gate=gate,
            judge_usage=judges.usage(),
            judge_stops=judges.stops(),
            exchanges=exchanges,
        )

    def _kept_recording(  # noqa: PLR0913 — the facts the sidecar's origin states
        self,
        kept: tuple[ExchangeKeeper, dict[str, int]],
        *,
        run_id: str,
        subject: str,
        started_at: datetime,
        gate: GateOutcome,
        result: ScanResult,
    ) -> Recording | None:
        """Turn what the keeper collected into the sidecar recording, or None when it holds nothing.

        A recording with no exchange is refused by every reader, so a run that kept none
        writes no sidecar and records no `exchanges`.
        """
        keeper, planned = kept
        recorded = keeper.recorded(EvidenceRedactor(self.profile.privacy))
        if not recorded:
            return None
        recording = Recording(
            name=_KEPT_NAME,
            version=run_id,
            verbatim=True,
            subject=subject,
            origin=RecordingOrigin(
                run_id=run_id,
                target=subject,
                started_at=started_at.isoformat(),
                stopped_by=None if result.stopped_by is None else str(result.stopped_by),
                gate=str(gate),
                trials=planned,
                rules=tuple(sorted(planned)),
            ),
            exchanges=recorded,
            digest=None,
        )
        data = render_recording(recording).encode("utf-8")
        digest = DocumentDigest(
            digest=f"sha256:{hashlib.sha256(data).hexdigest()}",
            kind=DigestKind.CONTENT,
            bytes=len(data),
        )
        return replace(recording, digest=digest)


def refuse_other_trials(recording: Recording, registry: Registry) -> None:
    """Refuse grading a probe's exchanges at other trials per case than it kept.

    Raises `RecordingRefusedError`; `guardana plan grade` asks the same question, so a plan
    never promises a grade this refuses.

    Fewer trials would leave a kept reply, possibly the failing one, ungraded; more would
    ask for replies the probe never received.
    """
    if recording.origin is None:
        return
    rules = {rule.meta.id: rule for rule in registry.rules()}
    differing = [
        f"{rule_id} kept {kept}, this run grades {rules[rule_id].trials_per_case}"
        for rule_id, kept in sorted(recording.origin.trials.items())
        if rule_id in rules and rules[rule_id].trials_per_case != kept
    ]
    if differing:
        raise RecordingRefusedError(
            f"the recording kept other trials per case than this run grades "
            f"({'; '.join(differing[:_NAMED_AT_MOST])}"
            f"{'…' if len(differing) > _NAMED_AT_MOST else ''}); grade it with "
            f"the trials the probe ran"
        )


def _connection_facts(target: Target) -> ConnectionFacts | None:
    """Describe how an endpoint run reached its model; None for any other target.

    Read off the target the caller passed, before a canary is planted on a view of it.
    """
    if not isinstance(target, EndpointTarget):
        return None
    transport = target.transport
    prompt = target.system_prompt
    return ConnectionFacts(
        provider=target.provider,
        adapter_digest=transport.source_digest
        if isinstance(transport, HttpAdapterTransport)
        else None,
        system_prompt_digest=None
        if prompt is None
        else DocumentDigest.of(prompt.encode("utf-8"), DigestKind.CONTENT).digest,
    )


def _recording_record(recording: Recording) -> RecordingRecord:
    """Describe the recording a graded run answered from, as the recording declares itself."""
    origin = recording.origin
    return RecordingRecord(
        name=recording.name,
        version=recording.version,
        subject=recording.subject,
        verbatim=recording.verbatim,
        origin=None
        if origin is None
        else RecordingOriginRecord(
            run_id=origin.run_id,
            target=origin.target,
            started_at=origin.started_at,
            stopped_by=origin.stopped_by,
            gate=origin.gate,
        ),
    )


def _exchanges_record(recording: Recording) -> ExchangesRecord:
    """Describe a kept recording in the manifest: its digest, its size, how many were altered."""
    if recording.digest is None:
        raise ValueError("a kept recording is digested before the manifest records it")
    return ExchangesRecord(
        digest=recording.digest.digest,
        count=len(recording.exchanges),
        altered=sum(1 for exchange in recording.exchanges if recording.reply_altered(exchange)),
    )


def _claim(target: Target) -> None:
    """Claim `target` for one run, refusing one that ran or is running here.

    A target that cannot be weakly referenced is not tracked; its meter is still checked.
    """
    with _RAN_LOCK:
        if _RAN.get(id(target)) is target:
            raise TargetReusedError(
                f"{target.ref} already ran; build a fresh target for each run so what it "
                f"lists and reads describes this run alone"
            )
        try:
            _RAN[id(target)] = target
        except TypeError:
            return


def _release(target: Target) -> None:
    """Give back a claim on a target that was refused before it sent anything."""
    with _RAN_LOCK:
        if _RAN.get(id(target)) is target:
            del _RAN[id(target)]


__all__ = [
    "CalibrationError",
    "EndpointBuilder",
    "JudgeUnreachableError",
    "RecordingRefusedError",
    "TargetReusedError",
    "TargetUnavailableError",
    "UnenforceableBudgetError",
    "UnsupportedTargetError",
    "Verification",
    "VerificationError",
    "Verifier",
    "exchanges_path",
]
