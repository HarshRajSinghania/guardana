"""What a run would cost, worked out without spending anything.

A command that tells you what a run will cost must not cost anything itself, so
nothing here sends a request. Everything it reports comes from what the rules
declare and what the target says about itself.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from guardana.core.budget import Budgets
from guardana.core.evaluator.base import Evaluator
from guardana.core.profile.model import Profile
from guardana.core.registry import Registry
from guardana.core.report import CheckError
from guardana.core.rule import Rule
from guardana.core.target import Target, TargetKind


@dataclass(frozen=True, slots=True)
class JudgeMeterPlan:
    """The judge calls one budgeted judge could be asked for, across every rule."""

    evaluators: tuple[str, ...]
    """The evaluator ids that grade through this judge and draw on its meter."""

    max_calls: int


@dataclass(frozen=True, slots=True)
class JudgePlan:
    """What grading would spend on judges and graders, and what could not be priced.

    Each budgeted judge counts its calls on a meter of its own under the run's
    request ceiling, so each is compared with that ceiling on its own rather than
    added to the target's requests.
    """

    max_calls: int
    """Every priced judge or grader call, metered or not."""

    meters: tuple[JudgeMeterPlan, ...]
    unknown_cost: tuple[str, ...]
    """Selected rules whose judge calls could not be priced."""

    unknown_on_meter: bool
    """Whether an unpriced rule could draw on a budgeted judge, so its meter has no ceiling."""

    @property
    def is_complete(self) -> bool:
        """Whether every selected rule's judge calls were priced."""
        return not self.unknown_cost

    def exceeds(self, limit: int) -> bool:
        """Whether some budgeted judge could be asked for more than `limit` calls."""
        return self.unknown_on_meter or any(m.max_calls > limit for m in self.meters)


@dataclass(frozen=True, slots=True)
class RunPlan:
    """The rules a run would execute, and what they would spend.

    `unknown_cost` is the field that keeps the rest honest. A rule that does not
    declare its request count contributes nothing to `max_requests`, so the
    ceiling would understate a run that includes one — unless the plan says so
    out loud, which is what this list is for.
    """

    rules: tuple[str, ...]
    skipped: tuple[str, ...]
    unknown_cost: tuple[str, ...]
    min_requests: int
    max_requests: int
    budgets: Budgets
    trials: int = 1
    """Attempts per case the run was asked for; already inside `max_requests`."""

    single_attempt: tuple[str, ...] = ()
    """Selected rules that make one attempt per case whatever `trials` says.

    Named so a plan for K attempts cannot be read as K attempts at a protocol check
    or a conversation the endpoint keeps, which do not repeat.
    """

    judge: JudgePlan | None = None
    """The judge calls the run would add, or None when this plan does not price them."""

    errors: tuple[CheckError, ...] = field(default=(), metadata={"in_document": False})
    """The errors the run would record before its first rule, from `pre_run_errors`.

    Each is a check that would not grade what it claims to, so a run carrying one
    cannot pass while `fail_on_error` is on. Left out of the plan document: a command
    reports them through its exit code and its error stream.
    """

    @property
    def requests_complete(self) -> bool:
        """Whether every selected rule declared the target requests it would send."""
        return not self.unknown_cost

    @property
    def is_complete(self) -> bool:
        """Whether everything the plan prices was priced: target requests and judge calls."""
        return self.requests_complete and (self.judge is None or self.judge.is_complete)

    @property
    def exceeds_budget(self) -> bool:
        """Whether the worst case would hit the configured request ceiling.

        Only the request ceiling: tokens and wall time cannot be predicted from a
        declaration, and guessing at them would produce a warning nobody could
        act on. A plan with an unknown-cost rule never claims to fit — its ceiling
        is not a ceiling. The same holds for every budgeted judge, whose meter has
        the same ceiling as the target's.
        """
        limit = self.budgets.max_requests
        if limit is None:
            return False
        over_judge = self.judge is not None and self.judge.exceeds(limit)
        return not self.requests_complete or self.max_requests > limit or over_judge


def build_plan(
    registry: Registry,
    profile: Profile,
    target: Target,
    *,
    judge_meters: Sequence[Collection[str]] | None = None,
) -> RunPlan:
    """Work out what running `profile`'s rules against `target` would cost.

    `judge_meters` prices judge calls: each entry is the evaluator ids that share one
    budgeted judge meter, empty when no judge is configured. None leaves judge calls
    unpriced, for a run that wires no judge.

    Selects exactly the way `Runner` does — same kind, same policy globs, same
    safety ceiling, same capability check — so the plan describes the run that
    would actually happen rather than an idealised one. The safety check and the
    errors recorded before the first rule share the runner's implementation rather
    than repeating it, because a plan that prices rules the run then refuses, or
    lists errors the run does not record, is a plan for a different run. It differs in
    one way, and the difference is stated rather than hidden: capabilities come
    from what the target *declares* without being asked, so an endpoint that turns
    out not to support tool calls will skip more rules than this predicted.
    """
    from guardana.core.runner import (  # noqa: PLC0415 — runner is downstream
        pre_run_errors,
        safety_refusal,
    )

    capabilities = target.capabilities()
    # Only an endpoint run samples a reply; a file plan given `trials: 5` in a shared
    # profile would otherwise list every artifact rule as declining something it
    # was never asked to do.
    repeats = target.kind is TargetKind.ENDPOINT
    selected: list[str] = []
    single_attempt: list[str] = []
    skipped: list[str] = []
    unknown: list[str] = []
    graded: list[Rule] = []
    ceiling = 0
    floor = 0
    for rule in registry.rules():
        meta = rule.meta
        if meta.target_kind != target.kind or not profile.policy.matches(meta.id):
            continue
        if safety_refusal(profile, rule) is not None:
            skipped.append(meta.id)
            continue
        if meta.required_capabilities - capabilities:
            skipped.append(meta.id)
            continue
        selected.append(meta.id)
        graded.append(rule)
        if repeats and rule.trials_per_case < profile.trials:
            single_attempt.append(meta.id)
        declared = rule.estimated_requests
        if declared is None:
            # A rule that sends and did not say how much sends at least once.
            unknown.append(meta.id)
            floor += 1
        else:
            ceiling += declared
            floor += 1 if declared > 0 else 0
    return RunPlan(
        rules=tuple(selected),
        skipped=tuple(skipped),
        unknown_cost=tuple(unknown),
        # The floor counts rules that send something; a rule that declared zero is
        # not one of them.
        min_requests=floor,
        max_requests=ceiling,
        budgets=profile.budgets,
        trials=profile.trials if repeats else 1,
        single_attempt=tuple(single_attempt),
        judge=None
        if judge_meters is None
        else _price_judges(graded, registry.evaluators(), judge_meters),
        errors=pre_run_errors(registry, target),
    )


def _price_judges(
    rules: Sequence[Rule],
    evaluators: Mapping[str, Evaluator],
    judge_meters: Sequence[Collection[str]],
) -> JudgePlan:
    """Price every selected rule's verdicts at its evaluators' calls, meter by meter.

    A rule is unpriced when it does not say what it grades, or grades with an
    evaluator that is not registered or does not say what one verdict costs.
    """
    metered = {evaluator_id for meter in judge_meters for evaluator_id in meter}
    per_evaluator: dict[str, int] = {}
    unknown: list[str] = []
    unknown_on_meter = False
    for rule in rules:
        verdicts = rule.graded_verdicts
        if verdicts is None:
            unknown.append(rule.meta.id)
            unknown_on_meter = unknown_on_meter or bool(metered)
            continue
        priced = True
        for evaluator_id, count in verdicts.items():
            evaluator = evaluators.get(evaluator_id)
            calls = None if evaluator is None else evaluator.judge_calls_per_verdict
            if calls is None:
                priced = False
                unknown_on_meter = unknown_on_meter or evaluator_id in metered
                continue
            per_evaluator[evaluator_id] = per_evaluator.get(evaluator_id, 0) + count * calls
        if not priced:
            unknown.append(rule.meta.id)
    meters = tuple(
        JudgeMeterPlan(
            evaluators=tuple(sorted(meter)),
            max_calls=sum(per_evaluator.get(evaluator_id, 0) for evaluator_id in meter),
        )
        for meter in judge_meters
    )
    return JudgePlan(
        max_calls=sum(per_evaluator.values()),
        meters=meters,
        unknown_cost=tuple(unknown),
        unknown_on_meter=unknown_on_meter,
    )
