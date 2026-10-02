import threading
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.error import URLError

from guardana.core.assessment import Assessment, UnmeasuredReason
from guardana.core.budget import BudgetExhausted
from guardana.core.gate import GateOutcome, gate, gate_outcome
from guardana.core.inventory import observe
from guardana.core.manifest.records import CalibrationRecord, SuiteSummary
from guardana.core.observation import Observation, ObservationKind
from guardana.core.profile.model import Profile
from guardana.core.registry import Registry
from guardana.core.report import CheckError, Finding, ScanResult, StopReason, split_ref
from guardana.core.report.shortfall import CoverageShortfall, ShortfallKind
from guardana.core.report.skipped import SkippedRule, SkipReason
from guardana.core.rule.base import Rule, RuleContext
from guardana.core.safety import permits
from guardana.core.source import UnreadSource
from guardana.core.target import (
    Capability,
    EndpointError,
    RecordedTarget,
    ReplyUnavailable,
    Target,
    TargetKind,
)
from guardana.core.target._scoped import RuleScoped
from guardana.core.target.protocols import FileReader, TraceReader, unmet_surfaces
from guardana.core.target.scope import FileScope, ReportsFileScope

DEFAULT_ENDPOINT_CONCURRENCY = 1
"""Rules run one at a time unless a caller asks for more.

Embedding Guardana must not silently start N connections to someone's model, so
the library default is sequential and the CLI opts in (`probe`/`monitor` take
`--concurrency`).
"""


def incomplete_recording(target: Target) -> tuple[CoverageShortfall, ...]:
    """Return the shortfall of grading a recording whose origin run was stopped.

    Only a stop counts: an origin that ended `indeterminate` is what regrading exists
    for, and its errors already return as errors. The origin is declared, not verified.
    `Runner.run` and `build_plan` both read this, so a plan refuses what the run cannot pass.
    """
    if not isinstance(target, RecordedTarget):
        return ()
    origin = target.recording.origin
    if origin is None or origin.stopped_by is None:
        return ()
    return (
        CoverageShortfall(
            kind=ShortfallKind.INCOMPLETE_RECORDING,
            name=origin.run_id,
            detail=(
                f"{target.ref} was kept from run {origin.run_id}, which stopped with "
                f"{origin.stopped_by}; replies it never received cannot be graded, so this "
                f"run cannot pass"
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class _RuleOutcome:
    """What one rule produced: findings, unverified findings, and whether it ran."""

    rule_id: str
    findings: tuple[Finding, ...] = ()
    unverified: tuple[Finding, ...] = ()
    assessments: tuple[Assessment, ...] = ()
    error: CheckError | None = None
    suite: SuiteSummary | None = None
    """What a suite concluded, carried from its context; None for every other rule."""

    raised: type[Exception] | None = None
    """The class of the exception `error` was built from, None when no exception was."""

    examined: frozenset[str] = frozenset()
    """The files this rule examined in its own format, those it reported on included."""

    shortfalls: tuple[CoverageShortfall, ...] = ()
    """The coverage this rule reported it could not get, through `RuleContext.shortfall`."""

    stopped_by: StopReason | None = None
    """Set when the run ran out of budget part-way through this rule.

    Separate from `error`, because the rule did not fail — and separate from a
    clean outcome, because the rule did not finish either. A rule cut off here
    must not join `rules_run`: listing it would claim coverage the run does not
    have, and a later comparison would read the missing findings as an
    improvement.
    """

    @property
    def ran(self) -> bool:
        """Whether the rule completed — an errored or cut-off rule did not."""
        return self.error is None and self.stopped_by is None


def pre_run_errors(registry: Registry, target: Target) -> tuple[CheckError, ...]:
    """Return every error a run of `registry` against `target` records before its first rule.

    A capability `target` declares without implementing it, an entry point or rule file
    that did not load, and a rule whose `expect:` block does not satisfy its evaluator's
    contract: each is a check that will not grade what it claims to. `Runner.run` and
    `build_plan` both read this, so a plan never lists a different set than the run records.
    """
    # One error naming the missing protocol beats every rule that needs it declining.
    contract_errors = tuple(
        CheckError(
            source=target.ref,
            stage="capability",
            reason=(
                f"{target.ref} declares {unmet} but does not implement it — "
                f"see guardana.core.target.protocols"
            ),
        )
        for unmet in unmet_surfaces(target)
    )
    return (
        *contract_errors,
        *registry.load_errors,
        *registry.expectation_errors(),
        *_unknown_recorded_rules(registry, target),
    )


@dataclass(frozen=True, slots=True)
class Runner:
    """Runs the rules a profile selects against one target."""

    registry: Registry
    profile: Profile
    concurrency: int = DEFAULT_ENDPOINT_CONCURRENCY
    calibrations: Mapping[str, CalibrationRecord] = field(default_factory=dict)
    """The judge calibrations each rule may read while it runs, keyed by evaluator id.

    Loaded once by the command and handed to the manifest too, so the run and its record
    correct with the same measurements.
    """

    def concurrency_for(self, kind: TargetKind) -> int:
        """How many rules may run at once against this kind of target.

        Endpoint rules are network-bound and overlap well. Artifact rules are
        local, already linear-cost since reads are shared, and a pool there would
        buy little while costing determinism — so file scanning stays sequential.
        """
        if kind is not TargetKind.ENDPOINT:
            return 1
        return max(1, self.concurrency)

    def run(self, target: Target) -> ScanResult:
        """Run every applicable rule; one that cannot run is recorded, never fatal, never silent.

        Two outcomes, deliberately kept apart. A rule is **skipped** only when the
        target cannot satisfy its capabilities — normal, expected, and no cause for
        alarm. Every other way a rule fails to produce a verdict, including a
        `RuleLoadError` for an evaluator nobody configured, is recorded in
        `errors`: the check did not run, and where it failed does not change that.
        The scan continues and the gate refuses to green-light the run.

        Results are collected in rule order regardless of which rule finishes
        first, so two runs of the same probe produce the same report and a CI diff
        stays signal.
        """
        # Installed before a single rule runs, so a budget set in a profile reaches
        # the target that has to hold it. A target that cannot enforce it refuses
        # here rather than letting the run proceed under a ceiling nothing watches.
        target.apply_budgets(self.profile.budgets)
        plan, skipped = select_rules(self.registry, self.profile, target)

        findings: list[Finding] = []
        unverified: list[Finding] = []
        errors: list[CheckError] = list(pre_run_errors(self.registry, target))
        # Names, not a count: the outcome carries its own rule id rather than being
        # paired back up with the plan by position, because a run aborted by an
        # unreachable endpoint yields fewer outcomes than it planned rules — and
        # pairing by position would then attribute results to the wrong rules.
        ran: list[str] = []
        executed: list[str] = []
        examined: set[str] = set()
        assessments: list[Assessment] = []
        suites: dict[str, SuiteSummary] = {}
        reported: list[CoverageShortfall] = []
        stopped_by: StopReason | None = None
        for outcome in self._execute(plan, target):
            executed.append(outcome.rule_id)
            # Kept even from a rule the budget cut off: a finding produced before
            # the ceiling is as real as one produced after it, and discarding it
            # would punish the user for the budget they set.
            findings.extend(outcome.findings)
            unverified.extend(outcome.unverified)
            # Kept from a cut-off rule, like its findings: a case measured before
            # the ceiling was measured. The rule still stays out of `rules_run`.
            assessments.extend(outcome.assessments)
            # Kept from a rule that did not finish too: a control that failed before the
            # rule stopped failed, and the stop alone would not say which item it was.
            reported.extend(outcome.shortfalls)
            if outcome.stopped_by is not None:
                stopped_by = outcome.stopped_by
            elif outcome.error is not None:
                errors.append(outcome.error)
            else:
                ran.append(outcome.rule_id)
                examined.update(outcome.examined)
            # Carried from an errored or cut-off suite too: it concluded that it did not
            # finish, over every case it planned, and dropping that decline would leave the
            # cases it never sent unaccounted for. The rule still stays out of `rules_run`.
            if outcome.suite is not None:
                suites[outcome.rule_id] = outcome.suite
        if isinstance(target, RecordedTarget):
            errors.extend(_ungraded_lines(target, executed))
        # A file the rules were prevented from reading is a check that did not
        # run, so it joins `errors` rather than disappearing. Collected after the
        # rules, because that is when the target knows what it was asked for.
        errors.extend(
            CheckError(source="guardana.core.source", stage="read", reason=unread.reason)
            for unread in _unread_sources(target)
        )
        # Taken from the target, not from the rules: if the inventory came out of what
        # fired, narrowing a profile would quietly shrink the list of components a
        # report says are deployed.
        scope = _file_scope(target)
        observations = observe(
            target, files=None if scope is None else [Path(path) for path in scope.files]
        )
        return ScanResult(
            tuple(findings),
            tuple(ran),
            tuple(skipped),
            tuple(unverified),
            errors=tuple(errors),
            assessments=tuple(assessments),
            observations=observations,
            # Taken from the target, which is the only thing that knows what left
            # the machine. A target that does not meter itself reports None, and
            # that travels all the way to the manifest as an explicit unknown.
            usage=target.usage(),
            # Read after the rules ran: a protocol version is only known once a
            # session has actually been opened, and asking before would record
            # "nothing negotiated" for a server that negotiated fine.
            protocols=target.protocols(),
            # Computed here rather than in a command, because a run whose verdict is
            # `indeterminate` for a reason that is not in its own document leaves
            # `diff` and the collector holding a conclusion with no cause.
            coverage_shortfall=(
                *_coverage_shortfall(self.profile, target),
                *incomplete_recording(target),
                *_unexamined_components(target, observations, examined),
                *reported,
            ),
            stopped_by=stopped_by,
            trials_per_case={
                rule.meta.id: rule.trials_per_case for rule in plan if rule.meta.id in ran
            },
            suites=suites,
            scope=scope,
        )

    def _execute(self, plan: Sequence[Rule], target: Target) -> Iterator[_RuleOutcome]:
        limit = self.concurrency_for(target.kind)
        if limit == 1 or len(plan) < 2:  # noqa: PLR2004 — nothing to overlap with one rule
            for rule in plan:
                outcome = self._execute_one(rule, target)
                yield outcome
                # Every remaining rule would hit the same ceiling, and sending more
                # requests to spend a budget that is already gone is pure cost.
                if outcome.stopped_by is not None:
                    return
            return
        yield from self._execute_pooled(plan, target, limit)

    def _execute_pooled(
        self, plan: Sequence[Rule], target: Target, limit: int
    ) -> Iterator[_RuleOutcome]:
        """Run `plan` across `limit` daemon threads, yielding outcomes in rule order.

        Deliberately hand-rolled rather than a `ThreadPoolExecutor`. That pool's
        workers are non-daemon and CPython joins them at interpreter exit, so a
        probe that hit an unreachable endpoint — or a Ctrl-C — printed its error
        and then sat there until every in-flight rule had finished its network
        work. Daemon threads let the process leave when the caller decides to.

        Once a rule reports the endpoint itself is gone, no further rule is
        started: they would all fail identically, and continuing to send prompts
        to a dead or rate-limited model is pure harm.
        """
        outcomes = self._run_pool(plan, target, limit)
        # Rule order, not completion order: two runs of the same probe must
        # produce the same report. A propagating failure surfaces at the first
        # rule that hit it, deterministically, rather than whichever thread lost.
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                raise outcome
            if outcome is not None:  # None: never started, because an abort won
                yield outcome

    def _run_pool(
        self, plan: Sequence[Rule], target: Target, limit: int
    ) -> list["_RuleOutcome | Exception | None"]:
        """Run the plan across `limit` daemon threads; return outcomes in plan order.

        A `None` in the result never started, because something aborted the pool:
        a propagating endpoint failure, or a budget that ran out.
        """
        outcomes: list[_RuleOutcome | Exception | None] = [None] * len(plan)
        aborted = threading.Event()
        cursor = iter(range(len(plan)))
        lock = threading.Lock()

        def take_next() -> int | None:
            with lock:
                return None if aborted.is_set() else next(cursor, None)

        def run_at(index: int) -> None:
            try:
                outcome = self._execute_one(plan[index], target)
            except Exception as exc:  # a propagating endpoint failure
                outcomes[index] = exc
                aborted.set()
                return
            outcomes[index] = outcome
            # Every remaining rule would hit the same ceiling; continuing would
            # spend requests against a budget that is already gone.
            if outcome.stopped_by is not None:
                aborted.set()

        def worker() -> None:
            while (index := take_next()) is not None:
                run_at(index)

        threads = [
            threading.Thread(target=worker, daemon=True, name=f"guardana-rule-{n}")
            for n in range(min(limit, len(plan)))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return outcomes

    def _execute_one(self, rule: Rule, target: Target) -> _RuleOutcome:
        """Run one rule, converting anything it throws into a recorded error.

        Any `Exception` is caught, not just `RuleError`: a third-party rule with an
        ordinary bug in it used to abort the entire scan. `BaseException` is
        deliberately not caught, so Ctrl-C and `SystemExit` still stop the run.

        A target that attributes exchanges is asked for this rule's own view here, in
        the thread that runs the rule, so nothing about which rule is asking is shared.
        """
        ctx = RuleContext(
            config=dict(self.profile.rule_config.get(rule.meta.id, {})),
            evaluators=self.registry.evaluators(),
            calibrations=self.calibrations,
        )
        subject = target.for_rule(rule.meta.id) if isinstance(target, RuleScoped) else target
        return _unanswered(self._run_rule(rule, subject, ctx), target, ctx)

    def _run_rule(self, rule: Rule, target: Target, ctx: RuleContext) -> _RuleOutcome:
        """Run `rule` against `target`, keeping what it produced before any failure."""
        findings: list[Finding] = []
        unverified: list[Finding] = []
        try:
            # Findings already yielded are kept: a rule is a generator, and what
            # it produced before dying is as real as a dangerous pickle global
            # found before a deliberately broken tail.
            for finding in rule.run(target, ctx):
                bucket = unverified if _is_inconclusive(finding) else findings
                bucket.append(finding)
        except BudgetExhausted:
            # Not a `CheckError`: the rule did not fail, the run ran out of room.
            # Reported as a stop so the result says its coverage is partial, and
            # so this rule stays out of `rules_run` — it did not finish.
            return _RuleOutcome(
                rule.meta.id,
                tuple(findings),
                tuple(unverified),
                ctx.recorded(),
                suite=ctx.concluded(),
                stopped_by=StopReason.BUDGET_EXHAUSTED,
                shortfalls=ctx.shortfalls(),
            )
        except (URLError, EndpointError) as exc:
            # The endpoint being unreachable is a fact about the run, not about
            # this rule: every rule would fail identically, so it is reported
            # once at the top with its own exit code, and therefore propagates.
            # Narrowed to connection failures on purpose — a rule that merely
            # opens a missing local file raises OSError too, and reporting a
            # healthy endpoint as down while abandoning every remaining rule is
            # a worse lie than the one this catch exists to avoid.
            if target.kind is TargetKind.ENDPOINT:
                raise
            return _RuleOutcome(
                rule.meta.id,
                tuple(findings),
                tuple(unverified),
                ctx.recorded(),
                error=CheckError.from_exception(rule.meta.id, "run", exc),
                suite=ctx.concluded(),
                raised=type(exc),
                shortfalls=ctx.shortfalls(),
            )
        except Exception as exc:
            return _RuleOutcome(
                rule.meta.id,
                tuple(findings),
                tuple(unverified),
                ctx.recorded(),
                error=CheckError.from_exception(rule.meta.id, "run", exc),
                suite=ctx.concluded(),
                raised=type(exc),
                shortfalls=ctx.shortfalls(),
            )
        reported = {split_ref(f.target_ref)[0] for f in (*findings, *unverified)}
        return _RuleOutcome(
            rule.meta.id,
            tuple(findings),
            tuple(unverified),
            ctx.recorded(),
            suite=ctx.concluded(),
            examined=ctx.examined_paths() | reported,
            shortfalls=ctx.shortfalls(),
        )


def select_rules(
    registry: Registry, profile: Profile, target: Target
) -> tuple[tuple[Rule, ...], tuple[SkippedRule, ...]]:
    """Choose the rules a run of `profile` against `target` executes, and the ones it skips.

    The one selection `Runner.run` and `guardana plan` both make: a filter added here
    reaches the plan too, so the plan never describes a run that selects differently.
    A rule of another target kind, or one the policy does not match, is neither.
    """
    capabilities = target.capabilities()
    selected: list[Rule] = []
    skipped: list[SkippedRule] = []
    for rule in registry.rules():
        meta = rule.meta
        if meta.target_kind != target.kind or not profile.policy.matches(meta.id):
            continue
        refusal = (
            safety_refusal(profile, rule)
            or capability_refusal(rule, target.ref, capabilities)
            or applicability_refusal(rule, target)
        )
        if refusal is None and isinstance(target, RecordedTarget):
            refusal = _unrecorded(rule, target)
        if refusal is not None:
            skipped.append(refusal)
            continue
        selected.append(rule)
    return tuple(selected), tuple(skipped)


def _unrecorded(rule: Rule, target: RecordedTarget) -> SkippedRule | None:
    """Skip a rule the recording holds no answer for, before it asks a single question."""
    if rule.meta.id in target.recorded_rules:
        return None
    return SkippedRule(
        rule_id=rule.meta.id,
        reason=SkipReason.NOT_RECORDED,
        missing=(target.ref,),
        detail=(
            f"{target.ref} holds no reply for {rule.meta.id} and does not list it among the "
            f"rules it was recorded for, so the check did not happen"
        ),
    )


def safety_refusal(profile: Profile, rule: Rule) -> SkippedRule | None:
    """Refuse a rule that reaches further than `profile` permits, and say so.

    Reported as a skip rather than dropped: a check that did not happen is a
    coverage gap whatever the reason, and the reason here points at a flag rather
    than at the target — which is what somebody reading the log needs to know.

    A free function rather than a `Runner` method because `guardana plan` has to
    reach the same verdict. A plan that priced rules the run then refuses is a
    plan describing a different run, and a second copy of this decision is a
    second copy that drifts.
    """
    meta = rule.meta
    if meta.destructive and not profile.allow_destructive:
        return SkippedRule(
            rule_id=meta.id,
            reason=SkipReason.UNSAFE_MODE,
            missing=("allow_destructive",),
            detail=(
                f"{meta.id} can destroy or alter something the target owns, and this "
                f"run does not permit that"
            ),
        )
    if not permits(profile.max_impact, meta.impact):
        return SkippedRule(
            rule_id=meta.id,
            reason=SkipReason.UNSAFE_MODE,
            missing=(str(meta.impact),),
            detail=(
                f"{meta.id} is {meta.impact}, and this run permits at most {profile.max_impact}"
            ),
        )
    return None


def capability_refusal(
    rule: Rule, target_ref: str, capabilities: Collection[Capability]
) -> SkippedRule | None:
    """Skip a rule whose required capabilities the target does not declare, and say which.

    Shared with `guardana plan` for the reason `safety_refusal` is: the reason is recorded
    where it is known, and a plan that words the same skip differently describes another run.
    """
    missing = rule.meta.required_capabilities - set(capabilities)
    if not missing:
        return None
    names = tuple(sorted(str(c) for c in missing))
    return SkippedRule(
        rule_id=rule.meta.id,
        reason=SkipReason.MISSING_CAPABILITY,
        missing=names,
        detail=f"{target_ref} does not support {', '.join(names)}, which {rule.meta.id} needs",
    )


def applicability_refusal(rule: Rule, target: Target) -> SkippedRule | None:
    """Skip a rule that says it has nothing to check on `target`, and record why.

    Not a coverage gap: nothing the rule needs is missing. A rule whose
    `not_applicable_to` raises is run instead, so its own failure is recorded as an error
    rather than read as having nothing to check.
    """
    try:
        reason = rule.not_applicable_to(target)
    except Exception:
        return None
    if reason is None:
        return None
    return SkippedRule(
        rule_id=rule.meta.id,
        reason=SkipReason.NOT_APPLICABLE,
        missing=(),
        detail=f"{rule.meta.id} has nothing to check on {target.ref}: {reason}",
    )


def refused_by_this_run(profile: Profile, rule: Rule) -> bool:
    """Whether this run will not execute `rule` because of a decision its operator made.

    Deliberately narrower than "did not run". A capability the target cannot satisfy is
    the *target's* answer and is exactly what a coverage demand exists to catch; an
    exclusion glob or a safety ceiling is the operator's, and a demand derived from a
    check they switched off would fail the build for not running it. Composed from the
    two things the plan already consults, so the wiring that withdraws a demand and the
    runner that drops the rule cannot disagree about which rules those are.
    """
    return not profile.policy.matches(rule.meta.id) or safety_refusal(profile, rule) is not None


def _unread_sources(target: Target) -> tuple[UnreadSource, ...]:
    """Return what this target could not read, for targets that track it."""
    if isinstance(target, FileReader):
        return target.unread_sources()
    return ()


def _unanswered(outcome: _RuleOutcome, target: Target, ctx: RuleContext) -> _RuleOutcome:
    """Turn a rule that asked a recording for a reply it lacks into an error.

    Read from the target's ledger rather than from what the rule raised: a rule may catch
    `ReplyUnavailable` and finish as if nothing happened. A rule that concluded a suite is
    left alone only when it recorded every such trial as ungraded: concluding is open to
    any rule, and one that concluded over replies it never got would otherwise pass.
    """
    if not isinstance(target, RecordedTarget):
        return outcome
    missed = target.missed(outcome.rule_id)
    if not missed:
        return outcome
    ungraded = sum(1 for a in outcome.assessments if a.reason in _UNANSWERED)
    if ctx.concluded() is not None and ungraded >= len(missed):
        return outcome
    reason = (
        f"{len(missed)} request(s) got no gradable reply from the recording, so the rule "
        f"did not grade what it set out to; the first: {missed[0]}"
    )
    if outcome.error is not None and not (
        outcome.raised is not None and issubclass(outcome.raised, ReplyUnavailable)
    ):
        reason = f"{reason}; then: {outcome.error.reason}"
    error = CheckError(source=outcome.rule_id, stage="run", reason=reason)
    return replace(outcome, error=error, raised=None)


_UNANSWERED = frozenset({UnmeasuredReason.NOT_RECORDED, UnmeasuredReason.REPLY_ALTERED})
"""The reasons a trial carries when the recording had no gradable reply for it."""

_NAMED_LINES = 5
"""How many unread line numbers an error names before it says how many more."""


def _ungraded_lines(target: RecordedTarget, executed: Collection[str]) -> tuple[CheckError, ...]:
    """Return an error per recorded reply nobody graded that someone was meant to.

    A rule that ran and left lines unread may have skipped the failing one. A loaded rule
    the profile did not select leaves its lines unread on purpose.
    """
    errors: list[CheckError] = []
    for rule_id in executed:
        unread = target.unread(rule_id)
        if not unread:
            continue
        lines = ", ".join(str(exchange.line) for exchange in unread[:_NAMED_LINES])
        more = f" and {len(unread) - _NAMED_LINES} more" if len(unread) > _NAMED_LINES else ""
        errors.append(
            CheckError(
                source=rule_id,
                stage="read",
                reason=(
                    f"{len(unread)} recorded repl(ies) of {rule_id} were never asked for "
                    f"(line {lines}{more}): a reply the recording holds and nobody graded "
                    f"may be the failing one"
                ),
            )
        )
    return tuple(errors)


def _unknown_recorded_rules(registry: Registry, target: Target) -> tuple[CheckError, ...]:
    """Return an error per rule a recording answers for that no loaded rule is.

    Known before the first rule runs, so a plan names it too: a renamed rule or a typo in
    a recording would otherwise leave its replies graded by nothing.
    """
    if not isinstance(target, RecordedTarget):
        return ()
    loaded = {rule.meta.id for rule in registry.rules()}
    return tuple(
        CheckError(
            source="guardana.core.recording",
            stage="read",
            reason=(
                f"{target.ref} answers for rule {rule_id}, which no loaded rule has, so its "
                f"replies are graded by nothing"
            ),
        )
        for rule_id in sorted(target.recorded_rules - loaded)
    )


_NAMED_UNEXAMINED = 3
"""How many unexamined components a shortfall names before it says how many more."""


def _unexamined_components(
    target: Target, observations: Sequence[Observation], examined: Collection[str]
) -> tuple[CoverageShortfall, ...]:
    """Return one shortfall per model format the run observed and no completed rule read.

    Only a file target is asked: an endpoint's model is the thing every rule talks to,
    not a file one of them has to open.
    """
    if not isinstance(target, FileReader):
        return ()
    unread: dict[str, list[str]] = {}
    for observation in observations:
        if observation.kind is ObservationKind.MODEL and observation.ref not in examined:
            unread.setdefault(observation.attributes.get("format", "unknown"), []).append(
                observation.ref
            )
    return tuple(
        CoverageShortfall(
            kind=ShortfallKind.UNEXAMINED_COMPONENT,
            name=model_format,
            detail=(
                f"{len(refs)} {model_format} model component(s) that no rule which ran reads: "
                f"{', '.join(refs[:_NAMED_UNEXAMINED])}"
                f"{' and more' if len(refs) > _NAMED_UNEXAMINED else ''} — whether they are "
                f"safe is unknown; exclude them from the scan or add a rule that reads "
                f"{model_format}"
            ),
        )
        for model_format, refs in sorted(unread.items())
    )


def _file_scope(target: Target) -> FileScope | None:
    """Return what a file target listed and excluded; None for a target that lists no files.

    A target that does not report its excludes is listed here, and its excludes are
    recorded as unknown rather than as none.
    """
    if isinstance(target, ReportsFileScope):
        return target.file_scope()
    if isinstance(target, FileReader):
        return FileScope(files=tuple(str(path) for path in target.iter_files()), excludes=None)
    return None


def _coverage_shortfall(profile: Profile, target: Target) -> tuple[CoverageShortfall, ...]:
    """Return the demanded evidence this target cannot supply.

    Measured against what the *producer declared it records*, not against the
    capabilities derived from it. The two agree for every dimension a rule needs
    today, and they come apart for one that no rule needs yet: a producer that
    records `memory` has satisfied a `require: [memory]` even though nothing in this
    build licenses a capability from it. Checking the derived set would report that
    trace as missing evidence it plainly contains.

    Only a trace is asked. `trace.require` is a statement about a *producer's*
    instrumentation, so demanding it of an artifact scan is a category error — and
    reading it as one would make a shared `guardana.yaml` a `guardana scan` that can
    never pass.
    """
    if not profile.required_dimensions or not isinstance(target, TraceReader):
        return ()
    return tuple(
        CoverageShortfall(
            kind=ShortfallKind.MISSING_DIMENSION,
            name=str(dimension),
            detail=(
                f"this run requires {dimension} evidence and {target.ref} does not record it, "
                f"so nothing here could establish what needs it"
            ),
        )
        for dimension in profile.required_dimensions
        if dimension not in target.trace.instrumented
    )


def _is_inconclusive(finding: Finding) -> bool:
    return finding.verdict is not None and finding.verdict.outcome == "inconclusive"


__all__ = [
    "DEFAULT_ENDPOINT_CONCURRENCY",
    "GateOutcome",
    "Runner",
    "gate",
    "gate_outcome",
    "incomplete_recording",
    "refused_by_this_run",
    "safety_refusal",
]
