"""A team's recipe: what its checks are, what answers them, and the lock that pins both.

The recipe is hand-written and reviewed; Guardana never rewrites it. The lock is generated
from the plan of the recipe's run and pins what a run already records about itself — rule
digests, the profile digest, judge identities — plus what those records miss: calibration
contents, the distribution behind every rule and evaluator, plugin trust and the subject's
own reviewed files. Design: `docs/design/team-recipes.md`.
"""

import importlib.metadata
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml
from guardana.core.calibration.store import RecordedCalibration
from guardana.core.fingerprint import digest_of
from guardana.core.manifest import SubjectKind, SubjectSource
from guardana.core.plan import RunPlan
from guardana.core.plugins import PluginTrust
from guardana.core.profile import Profile
from guardana.core.profile.digest import profile_digest
from guardana.core.registry import Registry
from guardana.core.report.skipped import SkipReason

if TYPE_CHECKING:
    from guardana.core.evaluator.base import Evaluator

RECIPE_SCHEMA_VERSION = 1
"""The `schema_version` of `guardana-recipe.yaml` this build reads."""

RECIPE_LOCK_SCHEMA_VERSION = 1
"""The `schema_version` of `guardana-recipe.lock.yaml` this build reads and writes."""

RECIPE_NAME = "guardana-recipe.yaml"
LOCK_NAME = "guardana-recipe.lock.yaml"

_TOP_KEYS = frozenset({"schema_version", "name", "profile", "subject", "deployment", "output"})
_SUBJECT_KEYS = frozenset({"kind", "connection", "recording"})
_CONNECTION_KEYS = frozenset(
    {"url", "model", "provider", "api_key_env", "adapter", "system_prompt_file"}
)
_DEPLOYMENT_KEYS = frozenset({"ai_system", "environment", "deployment_id"})
_OUTPUT_KEYS = frozenset({"directory", "exchanges"})
_DEFAULT_OUTPUT = "guardana-artifact"


class RecipeError(ValueError):
    """A recipe or a recipe lock that cannot be used, named down to the key at fault."""


@dataclass(frozen=True, slots=True)
class Recipe:
    """A loaded `guardana-recipe.yaml`, every path resolved beside the file.

    `connection` is the mapping as written; the command that sends turns it into a
    connection and validates it, so a recipe can be locked where no key is set. `kind`
    is None only for a recording subject that leaves the kind to the recording.
    """

    name: str
    path: Path
    profile: Path
    kind: SubjectKind | None
    connection: Mapping[str, str] | None
    recording: Path | None
    deployment: Mapping[str, str]
    output: Path
    keep_exchanges: bool
    digest: str
    """Of the parsed document, so a comment or line endings are not a change."""

    @property
    def source(self) -> SubjectSource:
        """How this recipe's subject answers."""
        return SubjectSource.RECORDING if self.recording is not None else SubjectSource.CONNECTION

    @property
    def lock_path(self) -> Path:
        """The lock beside the recipe."""
        return self.path.parent / LOCK_NAME

    def subject_file(self, key: str) -> Path | None:
        """Resolve `adapter` or `system_prompt_file` from the connection, beside the recipe."""
        raw = None if self.connection is None else self.connection.get(key)
        return None if raw is None else self.path.parent / raw

    def run_kind(self, recorded: SubjectKind | None) -> SubjectKind:
        """Return what answered the run: the recipe's kind, else the one its recording declares.

        `recorded` is the recording's `subject_kind`. A recipe and a recording that declare
        different kinds, or neither declaring one, raise `RecipeError` naming both places.
        """
        if self.kind is not None and recorded is not None and self.kind is not recorded:
            raise RecipeError(
                f"{self.path} declares `subject.kind: {self.kind}` and the recording "
                f"{self.recording} declares `subject_kind: {recorded}`; a run has one subject, "
                f"so make them agree or remove `subject.kind` from the recipe"
            )
        resolved = self.kind if self.kind is not None else recorded
        if resolved is None:
            choices = ", ".join(kind.value for kind in SubjectKind)
            raise RecipeError(
                f"{self.path} declares no `subject.kind` and the recording {self.recording} "
                f"declares no `subject_kind`; declare `subject.kind` ({choices}) in the recipe: "
                f"it has no default, because what answered is what a reader of the result needs "
                f"to know first"
            )
        return resolved


def load_recipe(path: Path) -> Recipe:
    """Read and validate a recipe; raise `RecipeError` naming what is wrong."""
    return parse_recipe(read_text(path, "recipe"), path)


def parse_recipe(text: str, path: Path) -> Recipe:
    """Validate a recipe's text, read from `path`; raise `RecipeError` naming what is wrong.

    Unknown keys are refused, and a `schema_version` this build does not know is refused
    rather than read: a key it cannot see would be a pin it silently does not hold.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RecipeError(f"{path} is not valid YAML: {exc}") from exc
    where = str(path)
    document = _mapping(raw, where)
    _refuse_unknown(document, _TOP_KEYS, where)
    _schema(document.get("schema_version"), RECIPE_SCHEMA_VERSION, "recipe", where)
    subject = _mapping(document.get("subject"), f"{where}: subject")
    _refuse_unknown(subject, _SUBJECT_KEYS, f"{where}: subject")
    connection, recording = _source(subject, path, where)
    kind = None if recording is not None and "kind" not in subject else _kind(subject, where)
    output = document.get("output", {})
    output = _mapping(output, f"{where}: output")
    _refuse_unknown(output, _OUTPUT_KEYS, f"{where}: output")
    deployment = _mapping(document.get("deployment", {}), f"{where}: deployment")
    _refuse_unknown(deployment, _DEPLOYMENT_KEYS, f"{where}: deployment")
    keep = output.get("exchanges", False)
    if not isinstance(keep, bool):
        raise RecipeError(f"{where}: output.exchanges must be true or false")
    return Recipe(
        name=_text(document, "name", where),
        path=path,
        profile=path.parent / _text(document, "profile", where),
        kind=kind,
        connection=connection,
        recording=recording,
        deployment={key: _text(deployment, key, f"{where}: deployment") for key in deployment},
        output=_output(output.get("directory", _DEFAULT_OUTPUT), path, where),
        keep_exchanges=keep,
        digest=digest_of("recipe-v1", _canonical(document)),
    )


def _source(
    subject: Mapping[str, Any], path: Path, where: str
) -> tuple[Mapping[str, str] | None, Path | None]:
    has_connection = "connection" in subject
    if has_connection == ("recording" in subject):
        raise RecipeError(f"{where}: subject needs exactly one of `connection` or `recording`")
    if not has_connection:
        return None, path.parent / _text(subject, "recording", f"{where}: subject")
    block = _mapping(subject["connection"], f"{where}: subject.connection")
    _refuse_unknown(block, _CONNECTION_KEYS, f"{where}: subject.connection")
    connection = {key: _text(block, key, f"{where}: subject.connection") for key in block}
    for required in ("url", "model"):
        if required not in connection:
            raise RecipeError(f"{where}: subject.connection needs `{required}`")
    return connection, None


def _kind(subject: Mapping[str, Any], where: str) -> SubjectKind:
    try:
        return SubjectKind(str(subject.get("kind")))
    except ValueError:
        choices = ", ".join(kind.value for kind in SubjectKind)
        raise RecipeError(
            f"{where}: subject.kind must be one of {choices}; it has no default, because what "
            f"answered is what a reader of the result needs to know first"
        ) from None


def _output(raw: object, path: Path, where: str) -> Path:
    """Resolve the artifact directory: a subdirectory beside the recipe, never the recipe's own."""
    if not isinstance(raw, str) or not raw.strip():
        raise RecipeError(f"{where}: output.directory must be a relative directory name")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or Path(raw).is_absolute() or ".." in relative.parts:
        raise RecipeError(f"{where}: output.directory must stay beside the recipe, not {raw!r}")
    if relative.parts in ((), (".",)):
        raise RecipeError(
            f"{where}: output.directory cannot be the recipe's own directory; name a "
            f"subdirectory the run may replace"
        )
    return path.parent / relative


def artifact_directory_of(path: Path) -> Path:
    """Return the artifact directory a recipe names, read leniently from a recipe that is invalid.

    Used when `load_recipe` refused the file, so the directory its last run wrote can still be
    marked as refused; anything unreadable falls back to the default beside the recipe.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        written = raw["output"]["directory"]
        return _output(written, path, str(path))
    except (OSError, UnicodeDecodeError, yaml.YAMLError, KeyError, TypeError, RecipeError):
        return path.parent / _DEFAULT_OUTPUT


class LockDriftKind(StrEnum):
    """How the configuration of a run differs from the lock its recipe carries."""

    RECIPE_CHANGED = "recipe_changed"
    GUARDANA_CHANGED = "guardana_changed"
    TRUST_CHANGED = "trust_changed"
    PROFILE_CHANGED = "profile_changed"
    RULE_ADDED = "rule_added"
    RULE_REMOVED = "rule_removed"
    RULE_CHANGED = "rule_changed"
    DISTRIBUTION_CHANGED = "distribution_changed"
    SKIP_CHANGED = "skip_changed"
    EVALUATOR_ADDED = "evaluator_added"
    EVALUATOR_REMOVED = "evaluator_removed"
    JUDGE_CHANGED = "judge_changed"
    CALIBRATION_CHANGED = "calibration_changed"
    TRIALS_CHANGED = "trials_changed"
    SUBJECT_FILE_CHANGED = "subject_file_changed"


@dataclass(frozen=True, slots=True)
class LockDrift:
    """One pin that does not hold."""

    kind: LockDriftKind
    subject: str
    detail: str

    def describe(self) -> str:
        """One line naming the pin and what moved."""
        return f"{self.kind}: {self.subject} — {self.detail}"


@dataclass(frozen=True, slots=True)
class PinnedOrigin:
    """Who registered a rule or an evaluator; both None when nobody is named."""

    distribution: str | None = None
    version: str | None = None

    def describe(self) -> str:
        """Name the origin for a drift line."""
        if self.distribution is None:
            return "no distribution"
        return f"{self.distribution} {self.version or '(no version)'}"


@dataclass(frozen=True, slots=True)
class PinnedRule:
    """A selected rule: what it is, and who registered it."""

    digest: str
    origin: PinnedOrigin = field(default_factory=PinnedOrigin)
    trials: int = 1


@dataclass(frozen=True, slots=True)
class PinnedEvaluator:
    """An evaluator a selected rule grades with: who registered it, its judge, its calibration."""

    origin: PinnedOrigin = field(default_factory=PinnedOrigin)
    judge: str | None = None
    calibration: str | None = None
    """Digest of the calibration in force for it, or None when none is."""


@dataclass(frozen=True, slots=True)
class RecipeLock:
    """Everything a recipe's run is pinned to."""

    recipe: str
    guardana: str
    trust: str
    profile: str
    rules: Mapping[str, PinnedRule]
    evaluators: Mapping[str, PinnedEvaluator]
    skipped: Mapping[str, str]
    """Rule id to skip reason, for the skips the configuration decides."""

    subject_files: Mapping[str, str]
    """`adapter` to the digest of its file as written; `system_prompt_file` to that of its text."""

    unpinned: tuple[str, ...] = ()
    """`rule:<id>` and `evaluator:<id>` whose distribution can change under one version."""

    schema_version: int = RECIPE_LOCK_SCHEMA_VERSION

    @property
    def digest(self) -> str:
        """Of the lock's content, recorded in the run so the evidence names its pins."""
        return digest_of("recipe-lock-v1", _canonical(lock_to_dict(self)))


_CONFIGURED_SKIPS = frozenset(
    {SkipReason.UNSAFE_MODE, SkipReason.MISSING_CAPABILITY, SkipReason.NOT_APPLICABLE}
)
"""Skips the configuration decides; a recording-dependent skip is the subject's answer."""


def lock_of(  # noqa: PLR0913 — the independent inputs a lock pins, each named
    recipe: Recipe,
    *,
    plan: RunPlan,
    registry: Registry,
    profile: Profile,
    calibrations: Mapping[str, RecordedCalibration],
    guardana_version: str,
    subject_files: Mapping[str, str],
    movable: Callable[[str], bool],
) -> RecipeLock:
    """Pin the run `plan` describes.

    `plan` is built against a target that sends nothing: the endpoint as configured, or a
    recording with no replies, so a rule the recording leaves unanswered is still a rule
    the configuration selected. `movable` says whether a distribution can change its code
    under one version (installed editable or from a direct URL).
    """
    rules_by_id = {rule.meta.id: rule for rule in registry.rules()}
    selected = [
        *plan.rules,
        *(skip.rule_id for skip in plan.skipped if skip.reason == SkipReason.NOT_RECORDED),
    ]
    unpinned: list[str] = []
    rules: dict[str, PinnedRule] = {}
    for rule_id in sorted(set(selected)):
        rule = rules_by_id[rule_id]
        origin = registry.origin_of(rule_id)
        if origin.distribution is not None and movable(origin.distribution):
            unpinned.append(f"rule:{rule_id}")
        rules[rule_id] = PinnedRule(
            digest=rule.digest(),
            origin=PinnedOrigin(origin.distribution, origin.version),
            trials=rule.trials_per_case,
        )
    evaluators = _evaluators(
        [rules_by_id[rule_id] for rule_id in rules], registry, calibrations, movable, unpinned
    )
    return RecipeLock(
        recipe=recipe.digest,
        guardana=guardana_version,
        trust=describe_trust(registry.trust),
        profile=profile_digest(profile),
        rules=rules,
        evaluators=evaluators,
        skipped={
            skip.rule_id: str(skip.reason)
            for skip in sorted(plan.skipped, key=lambda s: s.rule_id)
            if skip.reason in _CONFIGURED_SKIPS
        },
        subject_files=dict(sorted(subject_files.items())),
        unpinned=tuple(sorted(unpinned)),
    )


def _evaluators(
    rules: list[Any],
    registry: Registry,
    calibrations: Mapping[str, RecordedCalibration],
    movable: Callable[[str], bool],
    unpinned: list[str],
) -> dict[str, PinnedEvaluator]:
    declared = sorted(
        {
            evaluator_id
            for rule in rules
            for evaluator_id, _expectation in rule.declared_expectations()
            if evaluator_id
        }
    )
    registered: Mapping[str, Evaluator] = registry.evaluators()
    pinned: dict[str, PinnedEvaluator] = {}
    for evaluator_id in declared:
        origin = registry.origin_of(f"evaluator:{evaluator_id}")
        if origin.distribution is not None and movable(origin.distribution):
            unpinned.append(f"evaluator:{evaluator_id}")
        evaluator = registered.get(evaluator_id)
        judge = None if evaluator is None else evaluator.judge_identity
        measured = calibrations.get(evaluator_id)
        pinned[evaluator_id] = PinnedEvaluator(
            origin=PinnedOrigin(origin.distribution, origin.version),
            judge=judge if isinstance(judge, str) and judge.strip() else None,
            calibration=None
            if measured is None
            else digest_of("calibration-v1", _canonical(asdict(measured))),
        )
    return pinned


def describe_trust(trust: PluginTrust | None) -> str:
    """Name a plugin trust the same way on every machine; `unstated` when nobody stated one."""
    if trust is None:
        return "unstated"
    allowed = ",".join(sorted(trust.allowed))
    return f"{trust.mode}:{allowed}" if allowed else str(trust.mode)


def compare(locked: RecipeLock, current: RecipeLock) -> tuple[LockDrift, ...]:
    """Every pin in `locked` that `current` does not hold, in both directions."""
    drift: list[LockDrift] = []
    for kind, name, before, after in (
        (LockDriftKind.RECIPE_CHANGED, "recipe", locked.recipe, current.recipe),
        (LockDriftKind.GUARDANA_CHANGED, "guardana", locked.guardana, current.guardana),
        (LockDriftKind.TRUST_CHANGED, "plugins", locked.trust, current.trust),
        (LockDriftKind.PROFILE_CHANGED, "profile", locked.profile, current.profile),
    ):
        if before != after:
            drift.append(LockDrift(kind, name, f"locked {before}, now {after}"))
    drift.extend(_rule_drift(locked.rules, current.rules))
    drift.extend(_evaluator_drift(locked.evaluators, current.evaluators))
    for rule_id in sorted(set(locked.skipped) | set(current.skipped)):
        was, now = locked.skipped.get(rule_id), current.skipped.get(rule_id)
        if was != now:
            drift.append(
                LockDrift(
                    LockDriftKind.SKIP_CHANGED,
                    rule_id,
                    f"skipped {was or 'never'} when locked, now {now or 'not skipped'}",
                )
            )
    for name in sorted(set(locked.subject_files) | set(current.subject_files)):
        held, found = locked.subject_files.get(name), current.subject_files.get(name)
        if held != found:
            drift.append(
                LockDrift(
                    LockDriftKind.SUBJECT_FILE_CHANGED,
                    name,
                    f"locked {held or 'absent'}, now {found or 'absent'}",
                )
            )
    return tuple(drift)


def _rule_drift(
    locked: Mapping[str, PinnedRule], current: Mapping[str, PinnedRule]
) -> list[LockDrift]:
    drift: list[LockDrift] = []
    for rule_id in sorted(set(locked) | set(current)):
        before, after = locked.get(rule_id), current.get(rule_id)
        if after is None:
            drift.append(LockDrift(LockDriftKind.RULE_REMOVED, rule_id, "locked, no longer runs"))
        elif before is None:
            drift.append(LockDrift(LockDriftKind.RULE_ADDED, rule_id, "runs, and was not locked"))
        else:
            if before.digest != after.digest:
                drift.append(
                    LockDrift(
                        LockDriftKind.RULE_CHANGED,
                        rule_id,
                        f"digest {before.digest} is now {after.digest}",
                    )
                )
            if before.origin != after.origin:
                drift.append(
                    LockDrift(
                        LockDriftKind.DISTRIBUTION_CHANGED,
                        rule_id,
                        f"locked from {before.origin.describe()}, now {after.origin.describe()}",
                    )
                )
            if before.trials != after.trials:
                drift.append(
                    LockDrift(
                        LockDriftKind.TRIALS_CHANGED,
                        rule_id,
                        f"{before.trials} trial(s) per case when locked, now {after.trials}",
                    )
                )
    return drift


def _evaluator_drift(
    locked: Mapping[str, PinnedEvaluator], current: Mapping[str, PinnedEvaluator]
) -> list[LockDrift]:
    drift: list[LockDrift] = []
    for evaluator_id in sorted(set(locked) | set(current)):
        before, after = locked.get(evaluator_id), current.get(evaluator_id)
        if after is None:
            drift.append(
                LockDrift(
                    LockDriftKind.EVALUATOR_REMOVED, evaluator_id, "locked, grades nothing now"
                )
            )
            continue
        if before is None:
            drift.append(
                LockDrift(LockDriftKind.EVALUATOR_ADDED, evaluator_id, "grades, and was not locked")
            )
            continue
        if before.origin != after.origin:
            drift.append(
                LockDrift(
                    LockDriftKind.DISTRIBUTION_CHANGED,
                    f"evaluator {evaluator_id}",
                    f"locked from {before.origin.describe()}, now {after.origin.describe()}",
                )
            )
        if before.judge != after.judge:
            drift.append(
                LockDrift(
                    LockDriftKind.JUDGE_CHANGED,
                    evaluator_id,
                    f"locked {before.judge or 'no judge'}, now {after.judge or 'no judge'}",
                )
            )
        if before.calibration != after.calibration:
            drift.append(
                LockDrift(
                    LockDriftKind.CALIBRATION_CHANGED,
                    evaluator_id,
                    f"locked {before.calibration or 'uncalibrated'}, "
                    f"now {after.calibration or 'uncalibrated'}",
                )
            )
    return drift


def lock_to_dict(lock: RecipeLock) -> dict[str, Any]:
    """Return the lock as its file holds it, every digest under a `digest:` key."""
    return {
        "schema_version": lock.schema_version,
        "recipe": {"digest": lock.recipe},
        "guardana": lock.guardana,
        "plugins": lock.trust,
        "profile": {"digest": lock.profile},
        "rules": {
            rule_id: {
                "digest": pinned.digest,
                "distribution": pinned.origin.distribution,
                "version": pinned.origin.version,
                "trials": pinned.trials,
            }
            for rule_id, pinned in sorted(lock.rules.items())
        },
        "evaluators": {
            evaluator_id: {
                "distribution": pinned.origin.distribution,
                "version": pinned.origin.version,
                "judge": pinned.judge,
                "calibration": None
                if pinned.calibration is None
                else {"digest": pinned.calibration},
            }
            for evaluator_id, pinned in sorted(lock.evaluators.items())
        },
        "skipped": dict(sorted(lock.skipped.items())),
        "subject_files": {
            name: {"digest": value} for name, value in sorted(lock.subject_files.items())
        },
        "unpinned": list(lock.unpinned),
    }


def render_lock(lock: RecipeLock) -> str:
    """Return the lock file's text."""
    return yaml.safe_dump(lock_to_dict(lock), sort_keys=False, allow_unicode=True)


_LOCK_KEYS = frozenset(
    {
        "schema_version",
        "recipe",
        "guardana",
        "plugins",
        "profile",
        "rules",
        "evaluators",
        "skipped",
        "subject_files",
        "unpinned",
    }
)


def read_lock(path: Path) -> RecipeLock:
    """Read a recipe lock; raise `RecipeError` for a missing, malformed or newer one."""
    return parse_lock(read_text(path, "recipe lock"), path)


def read_text(path: Path, what: str) -> str:
    """Return a recipe's or a lock's text, naming the missing lock's remedy."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        remedy = (
            "; write one with `guardana recipe lock` and review it" if what == "recipe lock" else ""
        )
        raise RecipeError(f"no {what} at {path}{remedy}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise RecipeError(f"cannot read {what} {path}: {exc}") from exc


def parse_lock(text: str, path: Path) -> RecipeLock:
    """Validate a lock's text, read from `path`; raise `RecipeError` if malformed or newer."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RecipeError(f"{path} is not valid YAML: {exc}") from exc
    where = str(path)
    document = _mapping(raw, where)
    _refuse_unknown(document, _LOCK_KEYS, where)
    _require(document, _LOCK_KEYS, where)
    _schema(document["schema_version"], RECIPE_LOCK_SCHEMA_VERSION, "recipe lock", where)
    return RecipeLock(
        recipe=_digest(document, "recipe", where),
        guardana=_text(document, "guardana", where),
        trust=_text(document, "plugins", where),
        profile=_digest(document, "profile", where),
        rules={
            rule_id: PinnedRule(
                digest=_text(entry, "digest", here),
                origin=_origin(entry, here),
                trials=_count(entry["trials"], f"{here}.trials"),
            )
            for rule_id, entry, here in _entries(document, "rules", _RULE_KEYS, where)
        },
        evaluators={
            evaluator_id: PinnedEvaluator(
                origin=_origin(entry, here),
                judge=_optional_text(entry, "judge", here),
                calibration=None
                if entry["calibration"] is None
                else _digest(entry, "calibration", here),
            )
            for evaluator_id, entry, here in _entries(
                document, "evaluators", _EVALUATOR_KEYS, where
            )
        },
        skipped={
            str(rule_id): _reason(value, f"{where}: skipped.{rule_id}")
            for rule_id, value in _mapping(document["skipped"], f"{where}: skipped").items()
        },
        subject_files={
            str(name): _digest(document["subject_files"], str(name), f"{where}: subject_files")
            for name in _mapping(document["subject_files"], f"{where}: subject_files")
        },
        unpinned=tuple(_strings(document["unpinned"], f"{where}: unpinned")),
    )


_RULE_KEYS = frozenset({"digest", "distribution", "version", "trials"})
_EVALUATOR_KEYS = frozenset({"distribution", "version", "judge", "calibration"})


def _require(raw: Mapping[str, Any], keys: frozenset[str], where: str) -> None:
    """Refuse a lock missing a key: a pin that is not written down holds nothing."""
    missing = sorted(keys - set(raw))
    if missing:
        raise RecipeError(f"{where}: missing key(s) {', '.join(missing)}; write the lock again")


def _entries(
    document: Mapping[str, Any], key: str, keys: frozenset[str], where: str
) -> list[tuple[str, Mapping[str, Any], str]]:
    block = _mapping(document[key], f"{where}: {key}")
    entries: list[tuple[str, Mapping[str, Any], str]] = []
    for name, value in block.items():
        here = f"{where}: {key}.{name}"
        entry = _mapping(value, here)
        _refuse_unknown(entry, keys, here)
        _require(entry, keys, here)
        entries.append((str(name), entry, here))
    return entries


def _origin(entry: Mapping[str, Any], where: str) -> PinnedOrigin:
    return PinnedOrigin(
        distribution=_optional_text(entry, "distribution", where),
        version=_optional_text(entry, "version", where),
    )


def _reason(value: object, where: str) -> str:
    try:
        return str(SkipReason(str(value)))
    except ValueError:
        raise RecipeError(f"{where}: {value!r} is not a skip reason this build knows") from None


def _digest(document: Mapping[str, Any], key: str, where: str) -> str:
    block = _mapping(document.get(key), f"{where}: {key}")
    return _text(block, "digest", f"{where}: {key}")


def _schema(raw: object, supported: int, what: str, where: str) -> None:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise RecipeError(f"{where}: schema_version must be an integer")
    if raw > supported:
        raise RecipeError(
            f"{where}: {what} schema {raw} was written by a newer Guardana; this build reads "
            f"schema {supported} — upgrade Guardana"
        )
    if raw < 1:
        raise RecipeError(f"{where}: schema_version {raw} does not exist")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _mapping(raw: object, where: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise RecipeError(f"{where} must be a mapping")
    return raw


def _refuse_unknown(raw: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(str(key) for key in raw if key not in allowed)
    if unknown:
        raise RecipeError(
            f"{where}: unknown key(s) {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}"
        )


def _text(raw: Mapping[str, Any], key: str, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RecipeError(f"{where}: `{key}` must be a non-empty string")
    return value


def _optional_text(raw: Mapping[str, Any], key: str, where: str) -> str | None:
    return None if raw.get(key) is None else _text(raw, key, where)


def _count(raw: object, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise RecipeError(f"{where} must be a positive integer")
    return raw


def _strings(raw: object, where: str) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise RecipeError(f"{where} must be a list of strings")
    return list(raw)


def moves_under_one_version(distribution: str) -> bool:
    """Whether `distribution` came from a direct URL, so its code can move under one version.

    PEP 610: an install from a local directory (editable or not), a VCS checkout or an
    archive URL writes `direct_url.json`; an install from an index does not. A version pin
    says nothing about the first three, so the lock lists what they register as unpinned.
    """
    try:
        found = importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError:
        return False
    return found.read_text("direct_url.json") is not None
