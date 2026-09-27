"""Build config-driven evaluators (the LLM judges and the guard) and register them.

The judge's differentiating value is that it grades "did the attack succeed" — but
it needs a model to ask, and nothing built one from config until here. Both the
judge and the optional guard model are ordinary endpoints, so they can point at a
local OpenAI-compatible server for fully offline grading. Absent config leaves an
evaluator unregistered, and a rule that names it is then skipped visibly by the
runner — never a silent pass.
"""

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from guardana.cli._endpoint import build_endpoint
from guardana.cli._errors import JudgeUnavailableError, http_status_problem, safe_url
from guardana.core.budget import BudgetExhausted, Budgets
from guardana.core.evaluator.guard import GuardEvaluator
from guardana.core.evaluator.llm_judge import JudgeCalibration, LlmJudgeEvaluator
from guardana.core.evaluator.reference_judge import ReferenceJudgeEvaluator
from guardana.core.fingerprint import digest_of
from guardana.core.manifest.usage import JudgeUsage
from guardana.core.profile import Profile
from guardana.core.profile.errors import ProfileError
from guardana.core.registry import Registry
from guardana.core.target import ChatMessage, EndpointError, EndpointTarget

_DEFAULT_PROMPT_VERSION = "2025.1"
_DEFAULT_PORTS = {"https": 443, "http": 80}


class JudgeMeter:
    """One `evaluators:` block's judge endpoint: its own tally, and whether it stopped a run.

    Every failure of a call leaves naming the block and the judge's URL without
    credentials: the runner reports a transport failure as the run's endpoint being
    down and a spent budget as a spent budget, so an unnamed one reads as the target's.

    Safe to share across threads: the tally is the endpoint's thread-safe meter, and the
    stop is written once, with the message a reader is shown.
    """

    def __init__(
        self, block: str, target: EndpointTarget, endpoint: str, serves: tuple[str, ...]
    ) -> None:
        self.block = block
        self.name = f"evaluators.{block}"
        self.evaluators = serves
        """The ids of the evaluators whose grading calls this meter counts."""
        self.endpoint = safe_url(endpoint)
        self._raw = (endpoint, endpoint.rstrip("/").removesuffix("/v1"))
        self._target = target
        self.stopped: str | None = None
        """Why this judge's ceiling stopped the run, or None when it never did."""

    def apply(self, budgets: Budgets) -> None:
        """Bound this judge by `budgets`, refusing a ceiling its transport cannot enforce."""
        try:
            self._target.apply_budgets(budgets)
        except BudgetExhausted as exc:
            raise BudgetExhausted(f"{self.name} ({self.endpoint}): {self._scrubbed(exc)}") from exc

    def ask(self, prompt: str) -> str:
        """Send one grading prompt to the judge and return its reply."""
        try:
            return self._target.chat([ChatMessage(role="user", content=prompt)])
        except BudgetExhausted as exc:
            self.stopped = f"{self.name} ({self.endpoint}) stopped the run: {self._scrubbed(exc)}"
            raise BudgetExhausted(self.stopped) from exc
        except HTTPError as exc:
            raise self._unavailable(self._rejection(exc.code)) from exc
        except OSError as exc:
            # `URLError` is the connect failure; a timeout or a reset while the reply is
            # read arrives as a bare `OSError`.
            reason = exc.reason if isinstance(exc, URLError) else exc
            raise self._unavailable(
                f"could not reach endpoint {self.endpoint} ({self.name}): {self._scrubbed(reason)}"
            ) from exc
        except EndpointError as exc:
            raise self._unavailable(
                f"endpoint {self.endpoint} ({self.name}) sent a reply guardana cannot use: "
                f"{self._scrubbed(exc)}"
            ) from exc

    def usage(self) -> JudgeUsage:
        """Return what this judge has spent so far, a null token sum meaning none reported."""
        spent = self._target.usage()
        return JudgeUsage(
            requests=spent.requests,
            input_tokens=spent.input_tokens,
            output_tokens=spent.output_tokens,
            requests_missing_token_counts=spent.requests_missing_token_counts,
            budget_exhausted=self.stopped is not None,
        )

    def _unavailable(self, problem: str) -> JudgeUnavailableError:
        return JudgeUnavailableError(self.block, self.endpoint, problem)

    def _scrubbed(self, problem: object) -> str:
        text = str(problem)
        for raw in self._raw:
            if raw:
                text = text.replace(raw, self.endpoint)
        return text

    def _rejection(self, status: int) -> str:
        return http_status_problem(
            status,
            where=f"endpoint {self.endpoint} ({self.name})",
            sender="the judge",
            rate_limited_remedy="wait for its quota to reset",
            rejected_remedy=f"check {self.name}.api_key_env and the key it names",
        )


@dataclass(frozen=True, slots=True)
class JudgeMeters:
    """The meters of every judge built from config, for a command to read once per run.

    Read outside the scan result on purpose: every pass of a probe shares these meters,
    and a snapshot carried per pass would be summed once per pass when results merge.
    """

    meters: tuple[JudgeMeter, ...] = ()

    def usage(self) -> dict[str, JudgeUsage] | None:
        """Return each judge's spend by block, or None when no judge was configured."""
        if not self.meters:
            return None
        return {meter.block: meter.usage() for meter in self.meters}

    def stops(self) -> tuple[str, ...]:
        """Say which judge ceilings stopped the run, in the words a reader is shown."""
        return tuple(meter.stopped for meter in self.meters if meter.stopped is not None)


def wire_config_evaluators(
    registry: Registry, profile: Profile, budgets: Budgets | None = None
) -> JudgeMeters:
    """Register every evaluator that must be built from `guardana.yaml` config.

    `llm_judge` and `reference_judge` share one judge model, built from
    `evaluators.llm_judge`; `guard` is an optional safety classifier. Call after
    discovery so they join the evaluator set the runner resolves every rule against.

    `budgets` bounds every judge and guard call on a meter of the model's own, so a
    judge-graded run stops at the ceiling like its target instead of spending past it.
    `None` leaves them unbounded. A token ceiling the judge's transport cannot enforce
    raises `BudgetExhausted` here, before anything is sent.

    Returns the judges' meters, fresh on every call, so the command can record what
    grading spent beside what the target spent, and each meter names the evaluators it
    counts for.
    """
    meters: list[JudgeMeter] = []
    judge_cfg = profile.evaluator_config.get("llm_judge")
    if judge_cfg is not None:
        judge, meter = _endpoint_call(
            judge_cfg, "llm_judge", budgets, (LlmJudgeEvaluator.id, ReferenceJudgeEvaluator.id)
        )
        for evaluator in _build_judges(judge_cfg, judge):
            registry.register_evaluator(evaluator)
        meters.append(meter)
    guard_cfg = profile.evaluator_config.get("guard")
    if guard_cfg is not None:
        guard, meter = _endpoint_call(guard_cfg, "guard", budgets, (GuardEvaluator.id,))
        registry.register_evaluator(
            GuardEvaluator(guard, judge_identity=_identity(guard_cfg, "guard"))
        )
        meters.append(meter)
    return JudgeMeters(tuple(meters))


def _build_judges(
    cfg: Mapping[str, object], judge: Callable[[str], str]
) -> tuple[LlmJudgeEvaluator, ReferenceJudgeEvaluator]:
    """Build the security judge and the reference judge on one judge model and one meter."""
    version = cfg.get("prompt_version", _DEFAULT_PROMPT_VERSION)
    if not isinstance(version, str):
        raise ProfileError("evaluators.llm_judge.prompt_version must be a string")
    min_agreement = cfg.get("min_agreement", 1)
    # `bool` is an `int` subclass, so `min_agreement: true` would slip through — reject it.
    if not isinstance(min_agreement, int) or isinstance(min_agreement, bool):
        raise ProfileError("evaluators.llm_judge.min_agreement must be an integer")
    identity = f"{_identity(cfg, 'llm_judge')}; samples={min_agreement}"
    try:
        # `prompt_version` names the security judge's rubric; the reference judge keeps
        # its own, so neither can inherit a calibration measured for the other.
        return (
            LlmJudgeEvaluator(
                judge, version, min_agreement, _calibration(cfg), judge_identity=identity
            ),
            ReferenceJudgeEvaluator(judge, min_agreement=min_agreement, judge_identity=identity),
        )
    except ValueError as exc:  # unknown prompt_version or min_agreement < 1 — config typos
        raise ProfileError(f"evaluators.llm_judge: {exc}") from exc


def _calibration(cfg: Mapping[str, object]) -> JudgeCalibration | None:
    """Read a measured accuracy from config, if the operator recorded one.

    Deliberately numbers rather than a corpus path: measuring costs one judge call
    per sample, and a scan is the wrong moment to spend that. Run
    `guardana calibrate`, then record what it measured — an explicit, auditable
    act rather than something that quietly happens on every run.
    """
    raw = cfg.get("calibration")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ProfileError("evaluators.llm_judge.calibration must be a mapping")
    accuracy = raw.get("accuracy")
    samples = raw.get("samples")
    evaluator_id = raw.get("evaluator_id")
    if not isinstance(accuracy, int | float) or isinstance(accuracy, bool):
        raise ProfileError("evaluators.llm_judge.calibration.accuracy must be a number")
    if not isinstance(samples, int) or isinstance(samples, bool):
        raise ProfileError("evaluators.llm_judge.calibration.samples must be an integer")
    if not isinstance(evaluator_id, str) or not evaluator_id:
        raise ProfileError(
            "evaluators.llm_judge.calibration.evaluator_id must name the judge that was "
            "measured, e.g. llm_judge@2025.1 — a changed rubric must not inherit an "
            "older measurement"
        )
    try:
        return JudgeCalibration(
            evaluator_id=evaluator_id, accuracy=float(accuracy), samples=samples
        )
    except ValueError as exc:
        raise ProfileError(f"evaluators.llm_judge.calibration: {exc}") from exc


def _endpoint_call(
    cfg: Mapping[str, object], what: str, budgets: Budgets | None, serves: tuple[str, ...]
) -> tuple[Callable[[str], str], JudgeMeter]:
    """Build a `prompt -> reply` callable from an endpoint config block, bounded when asked.

    `serves` names the evaluators that will grade through it, so its meter can say whose
    calls it counts.
    """
    endpoint = _require_str(cfg, "endpoint", what)
    model = _require_str(cfg, "model", what)
    try:
        target = build_endpoint(endpoint, model, api_key=_api_key(cfg, what))
    except EndpointError:
        # Neither the builder's message nor the URL is repeated: a value that did not
        # parse as a URL can hold its credential where no scrubber looks for one.
        raise ProfileError(
            f"evaluators.{what}.endpoint must be an http or https URL with a host"
        ) from None
    meter = JudgeMeter(what, target, endpoint, serves)
    if budgets is not None:
        meter.apply(budgets)
    return meter.ask, meter


def _identity(cfg: Mapping[str, object], what: str) -> str:
    """State which model at which endpoint grades, so a calibration can be matched to it.

    The endpoint is digested after canonicalisation, never written out: a URL can carry
    credentials in its userinfo or query, and two spellings of one server must not read
    as two judges.
    """
    model = _require_str(cfg, "model", what)
    parts = urlsplit(_require_str(cfg, "endpoint", what))
    try:
        port = parts.port
    except ValueError as exc:
        raise ProfileError(f"evaluators.{what}.endpoint has an unreadable port: {exc}") from exc
    scheme = parts.scheme.lower()
    if port is None:
        port = _DEFAULT_PORTS.get(scheme)
    if port is None:
        raise ProfileError(f"evaluators.{what}.endpoint must state a port, or use http or https")
    host = (parts.hostname or "").lower()
    canonical = f"{scheme}://{host}:{port}{parts.path.rstrip('/')}"
    endpoint = digest_of(canonical).split(":", 1)[-1][:12]
    return f"model={model}; endpoint={endpoint}"


def _require_str(cfg: Mapping[str, object], key: str, what: str) -> str:
    value = cfg.get(key)
    if not isinstance(value, str) or not value:
        raise ProfileError(f"evaluators.{what}.{key} must be a non-empty string")
    return value


def _api_key(cfg: Mapping[str, object], what: str) -> str | None:
    env = cfg.get("api_key_env")
    if env is None:
        return None
    if not isinstance(env, str):
        raise ProfileError(f"evaluators.{what}.api_key_env must be a string")
    return os.environ.get(env)
