import copy
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Self

from guardana.core.entrypoints import (
    EVALUATOR_GROUP,
    RULE_GROUP,
    TARGET_GROUP,
    TAXONOMY_GROUP,
    InstalledEntryPoint,
    installed_entry_points,
)
from guardana.core.evaluator.base import Evaluator, check_expectation
from guardana.core.origin import UNATTRIBUTED, Origin
from guardana.core.plugins import PluginTrust
from guardana.core.report.check_error import CheckError
from guardana.core.rule.base import Rule
from guardana.core.rule.errors import RuleLoadError
from guardana.core.rule.yaml_rule import load_yaml_rules
from guardana.core.target import Target
from guardana.core.taxonomy import TaxonomyRef, known_refs
from guardana.core.taxonomy import register as register_taxonomy
from guardana.core.taxonomy import unregister as unregister_taxonomy
from guardana.core.trials import check_trials

_CANARY_EVALUATOR_ID = "canary"
# Never planted for real: only used to ask a rule whether it participates at all.
_MARKER = "GUARDANA_CANARY_PARTICIPATION_CHECK"
RESERVED_NAMESPACE = "guardana."
_TARGET_SCHEME = re.compile(r"^[a-z][a-z0-9-]*$")
RESERVED_TARGET_SCHEMES = frozenset({"file", "http", "https", "mcp", "trace"})


class RegistryConflictError(RuleLoadError):
    """Two different origins claimed one id, or a plugin claimed a reserved one.

    A `RuleLoadError` because every path that already refuses a rule refuses this
    one the same way: the run keeps going, the refusal lands in `errors`, and the
    gate will not call the result a pass.
    """


@dataclass(frozen=True, slots=True)
class RuleDirLoad:
    """Outcome of loading YAML rules from a set of directories/files."""

    loaded: tuple[str, ...]
    errors: tuple[CheckError, ...]


@dataclass(slots=True)
class _LoadRecord:
    """Everything a registry learned about what it could not load, kept as one value."""

    errors: list[CheckError] = field(default_factory=list)
    refused: list[InstalledEntryPoint] = field(default_factory=list)
    refusal_errors: list[CheckError] = field(default_factory=list)
    """The entries of `errors` that record a refusal, the same objects rather than copies."""
    failed: list[tuple[InstalledEntryPoint, CheckError]] = field(default_factory=list)
    """Each admitted entry point that failed to load, with the entry of `errors` it recorded."""
    trust: PluginTrust | None = None
    """The trust discovery applied; None for a registry nothing discovered."""

    def copied(self) -> "_LoadRecord":
        """Return a copy whose containers are new and whose entries are shared.

        Every field is copied by iterating `fields`, so a field added later travels too;
        the entries stay shared so a refusal error is still found in `errors` by identity.
        """
        return replace(self, **{f.name: copy.copy(getattr(self, f.name)) for f in fields(self)})


class Registry:
    """Single discovery point for rules, evaluators, and targets (built-in or third-party)."""

    def __init__(self) -> None:
        self._rules: list[Rule] = []
        self._evaluators: dict[str, Evaluator] = {}
        self._targets: list[type[Target]] = []
        self._load = _LoadRecord()
        self._origins: dict[str, Origin] = {}

    def empty_with_load_state(self) -> Self:
        """Return a registry with no rules, evaluators or targets, carrying this one's load state.

        Load errors, refusals, failed entry points and what tells them apart all travel,
        so a registry built from part of this one still reports every plugin that did not
        load, and which entry point each failure belongs to.
        """
        other: Self = type(self)()
        other._load = self._load.copied()
        return other

    def copied(self) -> Self:
        """Return a registry holding everything this one holds, its load state included.

        Registering on the copy leaves this one as it was, so a run that adds its own
        judges does not change a registry its caller shares between runs. Every attribute
        is copied, so one added later travels too.
        """
        other: Self = type(self)()
        for name, value in vars(self).items():
            copied = value.copied() if isinstance(value, _LoadRecord) else copy.copy(value)
            setattr(other, name, copied)
        return other

    @property
    def trust(self) -> PluginTrust | None:
        """The plugin trust `discover` loaded under; None for a registry built by hand."""
        return self._load.trust

    @property
    def load_errors(self) -> tuple[CheckError, ...]:
        """Every plugin or rule file that could not be loaded, and why."""
        return tuple(self._load.errors)

    @property
    def refused(self) -> tuple[InstalledEntryPoint, ...]:
        """Every entry point plugin trust kept from being imported, in discovery order.

        The same refusals `load_errors` carries as `discovery` errors, as records a
        caller can read without parsing a reason written for a human.
        """
        return tuple(self._load.refused)

    @property
    def failed(self) -> tuple[tuple[InstalledEntryPoint, CheckError], ...]:
        """Every admitted entry point that failed to load, paired with the error it recorded.

        The error is the same object `load_failures` carries, so a caller attributes a
        failure to its entry point without matching on a name two entry points can share.
        """
        return tuple(self._load.failed)

    @property
    def load_failures(self) -> tuple[CheckError, ...]:
        """Every load error that is not a refusal by plugin trust, in the order recorded.

        Told apart by the error the refusal recorded, not by name: an admitted entry
        point that failed can share its name with a refused one.
        """
        return tuple(
            error
            for error in self._load.errors
            if not any(error is refusal for refusal in self._load.refusal_errors)
        )

    def record_load_error(self, error: CheckError) -> None:
        """Record something that could not be loaded, so the run can report it."""
        self._load.errors.append(error)

    def register_rule(self, rule: Rule, origin: Origin = UNATTRIBUTED) -> None:
        """Add a rule under its id, refusing an id another origin already holds.

        The same origin registering twice still de-duplicates: one rule file can
        arrive through both `rules.paths` and `--rules`, and running it twice means
        doubled findings and doubled probe calls.

        A *different* origin raises `RegistryConflictError`, as does an installed
        plugin claiming the reserved `guardana.*` namespace. Why silent last-wins
        had to go: `docs/design/capability-protocols.md`.
        """
        _require_canary_participation(rule)
        self._refuse_conflict("rule", rule.meta.id, origin)
        for i, existing in enumerate(self._rules):
            if existing.meta.id == rule.meta.id:
                self._rules[i] = rule
                return
        self._rules.append(rule)
        self._origins[rule.meta.id] = origin

    def register_evaluator(self, evaluator: Evaluator, origin: Origin = UNATTRIBUTED) -> None:
        """Add an evaluator under its own `id`, refusing an id another origin holds.

        The sharper case of the two: a rule names its grader by string, so
        replacing `canary` changes how every canary-graded rule decides pass from
        fail without touching a rule.
        """
        self._refuse_conflict("evaluator", evaluator.id, origin)
        self._evaluators[evaluator.id] = evaluator
        self._origins[f"evaluator:{evaluator.id}"] = origin

    def register_target(self, target: type[Target], origin: Origin = UNATTRIBUTED) -> None:
        """Add a target class, validating its optional command-line locator scheme."""
        scheme = target.scheme
        if scheme is not None:
            if not isinstance(scheme, str) or _TARGET_SCHEME.fullmatch(scheme) is None:
                raise RegistryConflictError(
                    f"target {target.__name__} declares invalid scheme {scheme!r}; use a "
                    "lowercase name matching [a-z][a-z0-9-]*"
                )
            if scheme in RESERVED_TARGET_SCHEMES:
                raise RegistryConflictError(
                    f"target {target.__name__} declares reserved scheme {scheme!r}; "
                    "file, http, https, mcp and trace belong to built-in target forms"
                )
            existing = self.target_for(scheme)
            held = self._origins.get(f"target-scheme:{scheme}")
            if existing is not None and existing is not target:
                owner = held.describe() if held is not None else existing.__name__
                raise RegistryConflictError(
                    f"target scheme {scheme!r} is already registered by {owner}; "
                    f"{origin.describe()} cannot make one locator select two targets"
                )
            if existing is target:
                return
            self._origins[f"target-scheme:{scheme}"] = origin
        self._targets.append(target)
        self._origins[f"target:{target.__name__}"] = origin

    def origin_of(self, rule_id: str) -> Origin:
        """Return which origin supplied the rule registered under `rule_id`.

        Public because the run manifest records it: a registry that knows and does
        not say leaves the question unanswerable once the document is all there is.
        """
        return self._origins.get(rule_id, UNATTRIBUTED)

    def _refuse_conflict(self, kind: str, identifier: str, origin: Origin) -> None:
        """Raise unless `identifier` is free, or held by this very origin."""
        if (
            identifier.startswith(RESERVED_NAMESPACE)
            and origin.distribution is not None
            and not origin.is_builtin
        ):
            raise RegistryConflictError(
                f"{origin.describe()} registers {kind} {identifier!r}, but the "
                f"`{RESERVED_NAMESPACE}*` namespace is reserved for Guardana's own "
                f"distributions — namespace your ids (see docs/writing-rules.md)"
            )
        key = identifier if kind == "rule" else f"{kind}:{identifier}"
        held = self._origins.get(key)
        if held is not None and held != origin:
            raise RegistryConflictError(
                f"{kind} {identifier!r} is already registered by {held.describe()}; "
                f"{origin.describe()} cannot claim the same id — one run cannot "
                f"say which code produced the verdict recorded under it. Give yours "
                f"its own id and switch the other off with `rules.exclude`, so the "
                f"report names what actually ran"
            )

    def rules(self) -> tuple[Rule, ...]:
        """Every registered rule, built-in and third-party alike."""
        return tuple(self._rules)

    def apply_trials(self, trials: int) -> None:
        """Make every registered rule that repeats attempt each of its cases `trials` times.

        Applied once, before a plan is priced or a rule runs, so the plan, the budget,
        the run and the saved record all read the same rule objects. A rule that does
        not repeat is left as it is and records one attempt per case.
        """
        check_trials(trials)
        self._rules = [_repeated(rule, trials) for rule in self._rules]

    def evaluators(self) -> Mapping[str, Evaluator]:
        """Every registered evaluator, keyed by the id rules reference it with."""
        return dict(self._evaluators)

    def targets(self) -> tuple[type[Target], ...]:
        """Every registered target class."""
        return tuple(self._targets)

    def target_for(self, scheme: str) -> type[Target] | None:
        """Return the one target class claiming ``scheme``, if it is loaded."""
        return next((target for target in self._targets if target.scheme == scheme), None)

    def schemes(self) -> tuple[str, ...]:
        """Every loaded command-line target scheme, in stable order."""
        return tuple(sorted(target.scheme for target in self._targets if target.scheme is not None))

    def expectation_errors(self) -> tuple[CheckError, ...]:
        """Every rule whose `expect:` block does not satisfy its evaluator's contract.

        Checked here rather than at parse time because a third-party evaluator does
        not exist yet while its rules are being parsed. An unsatisfied contract is a
        check that cannot grade what it claims to, so it belongs in `errors` — a
        rule reading a field its evaluator ignores looks configured and tests
        nothing.

        Evaluators that are not registered are left alone: that is the
        "judge nobody configured" case, which the rule itself reports when it runs.
        """
        errors: list[CheckError] = []
        for rule in self._rules:
            for evaluator_id, expectation in rule.declared_expectations():
                evaluator = self._evaluators.get(evaluator_id)
                if evaluator is None:
                    continue
                problem = check_expectation(evaluator_id, evaluator.expects, expectation)
                if problem is not None:
                    errors.append(CheckError(source=rule.meta.id, stage="load", reason=problem))
        return tuple(errors)

    def load_yaml_rule_dirs(self, paths: Iterable[Path]) -> RuleDirLoad:
        """Load and register declarative YAML rules from directories or files.

        Never raises: a malformed or unloadable rule file is recorded in
        `RuleDirLoad.errors` instead of aborting the caller's scan.
        """
        loaded: list[str] = []
        errors: list[CheckError] = []
        for path in paths:
            files = _yaml_files(path)
            if not files:
                # A directory someone configured that holds no rule file loads nothing,
                # and a run without the checks it was told to add must not look complete.
                errors.append(
                    CheckError(
                        source=str(path),
                        stage="load",
                        reason=(
                            "the directory holds no .yaml or .yml rule file; files in its "
                            "subdirectories are not read"
                        ),
                    )
                )
            for file in files:
                # Resolved, not as written: `rules.paths: [my-rules]` and
                # `--rules ./my-rules/` name one file, and two spellings of it must
                # not read as two origins.
                origin = Origin(source=str(_resolved(file)))
                try:
                    for rule in load_yaml_rules(file):
                        self.register_rule(rule, origin)
                        loaded.append(rule.meta.id)
                except (RuleLoadError, OSError) as exc:
                    errors.append(CheckError.from_exception(str(file), "load", exc))
        self._load.errors.extend(errors)
        return RuleDirLoad(tuple(loaded), tuple(errors))

    @classmethod
    def discover(cls, trust: PluginTrust) -> Self:
        """Load the rules, evaluators and targets that `trust` permits.

        This imports third-party code: an installed plugin is trusted code (see
        SECURITY.md). `PluginTrust` decides how much of it is loaded — everything,
        only Guardana's own reviewed distributions, a named allowlist, or nothing.

        Each entry point is isolated. One that fails to import — a pack pinned to a
        library you do not have, a typo in a provider — is recorded in
        `load_errors` and the rest still load. Without that isolation a single
        broken third-party package left the user with no rules at all, built-ins
        included, which is the most complete failure mode a scanner has.

        Every refusal is recorded, `disabled` included. That mode used to return
        before the loop and so reported nothing at all — the one setting that
        loads no checks whatsoever was also the only one that did not say so, and
        a run with no rules is a run whose silence means nothing.
        """
        if not isinstance(trust, PluginTrust):
            raise TypeError(
                f"Registry.discover needs a PluginTrust, not {type(trust).__name__}: say "
                f"which installed distributions may run code, for example "
                f"PluginTrust(mode=PluginMode.BUILTINS)"
            )
        reg = cls()
        reg._load.trust = trust
        handlers: dict[str, tuple[type | tuple[type, ...], Callable[[Any, Origin], None]]] = {
            TAXONOMY_GROUP: (TaxonomyRef, _ignoring_origin(register_taxonomy)),
            RULE_GROUP: (Rule, reg.register_rule),
            EVALUATOR_GROUP: (Evaluator, reg.register_evaluator),
            TARGET_GROUP: (Target, reg.register_target),
        }
        for entry_point in installed_entry_points():
            expected, register = handlers[entry_point.group]
            if not trust.allows(entry_point.distribution):
                # Recorded, not silently dropped: a rule pack the user
                # installed and this run refused to load is coverage they
                # think they have. Landing in `load_errors` puts it in the
                # `errors` channel, which fails the gate by default.
                refusal = CheckError(
                    source=entry_point.name,
                    stage="discovery",
                    reason=(
                        f"plugin from "
                        f"{entry_point.distribution or 'an unknown distribution'} "
                        f"was not loaded: plugin trust is {trust.describe()}"
                    ),
                )
                reg._load.refused.append(entry_point)
                reg._load.refusal_errors.append(refusal)
                reg.record_load_error(refusal)
                continue
            origin = Origin(distribution=entry_point.distribution, version=entry_point.version)
            # Rollback rather than a pre-flight, so a refusal added later stays
            # atomic without needing a second implementation. The framework
            # catalogue is process-wide, so what a failed provider added to it
            # is forgotten too, and a rule cannot cite a reference whose
            # provider was reported broken.
            snapshot = reg._snapshot()
            references = {ref.reference for ref in known_refs()}
            try:
                _absorb(_provided_by(entry_point), expected, register, origin)
            except Exception as exc:
                reg._restore(snapshot)
                for ref in known_refs():
                    if ref.reference not in references:
                        unregister_taxonomy(ref.reference)
                failure = CheckError.from_exception(entry_point.name, "discovery", exc)
                reg._load.failed.append((entry_point, failure))
                reg.record_load_error(failure)
        return reg

    def _snapshot(
        self,
    ) -> tuple[list[Rule], dict[str, Evaluator], list[type[Target]], dict[str, Origin]]:
        """Copy the registrations, so one provider's failure can be undone whole."""
        return (list(self._rules), dict(self._evaluators), list(self._targets), dict(self._origins))

    def _restore(
        self,
        snapshot: tuple[list[Rule], dict[str, Evaluator], list[type[Target]], dict[str, Origin]],
    ) -> None:
        """Put the registrations back as they were before a provider was absorbed."""
        self._rules, self._evaluators, self._targets, self._origins = (
            snapshot[0],
            snapshot[1],
            snapshot[2],
            snapshot[3],
        )


def _repeated(rule: Rule, trials: int) -> Rule:
    """Return `rule` repeating `trials` times, or unchanged when it does not repeat."""
    repeated = rule.with_trials(trials)
    return rule if repeated is None else repeated


def _ignoring_origin(register: Callable[[Any], None]) -> Callable[[Any, Origin], None]:
    """Adapt a one-argument registrar to the two-argument shape discovery uses."""

    def call(item: Any, _origin: Origin) -> None:  # noqa: ANN401 — provider payload
        register(item)

    return call


def _provided_by(entry_point: InstalledEntryPoint) -> object:
    """Import the entry point and call the provider it names."""
    provider = entry_point.load()
    if not callable(provider):
        raise TypeError(f"entry point {entry_point.value!r} does not name a callable provider")
    return provider()


def _require_canary_participation(rule: Rule) -> None:
    """Refuse a rule that grades by canary but will not accept the planted one.

    The probe plants a fresh token and hands it to `Rule.with_canary`. A rule that
    grades by canary and returns None there never sees the marker, so its
    evaluator finds nothing and reports a confident pass for a fully leaking
    model. Checked once, here, because this is the single point every rule —
    built-in, YAML, or a third party's own class — passes through.

    Keyed off the *declared* evaluator, not off `PLANT_SYSTEM_PROMPT`: a rule may
    legitimately need a system prompt planted without grading by canary. A plugin
    rule that reaches for the canary evaluator through `ctx.evaluators` without
    declaring it stays beyond what any static check can see — which is why
    `Rule.with_canary` says so where an author will read it.
    """
    if rule.meta.evaluator == _CANARY_EVALUATOR_ID and rule.with_canary(_MARKER) is None:
        raise RuleLoadError(
            f"rule {rule.meta.id!r} grades with a planted canary but its `with_canary` "
            f"returns None, so the marker would never be planted and the rule would "
            f"pass every model"
        )


def _absorb(
    produced: object,
    expected: type | tuple[type, ...],
    register: Callable[[Any, Origin], None],
    origin: Origin,
) -> None:
    """Register everything a provider returned, or none of it.

    One provider is one transaction, so a run cannot both list a pack's rules in
    `rules_run` and report the pack as unloadable. Materialised first for the same
    reason: a generator that raises half way through is otherwise indistinguishable
    from one that returned a shorter list.
    """
    items = list(produced) if isinstance(produced, Iterable) else [produced]
    for item in items:
        if not isinstance(item, expected) and not (
            isinstance(item, type) and issubclass(item, expected)
        ):
            raise TypeError(f"provider returned {type(item).__name__}, expected {expected}")
    for item in items:
        register(item, origin)


def _resolved(path: Path) -> Path:
    """Absolute, symlink-free form of `path`, falling back to the path as given.

    `resolve()` can raise on a path this process cannot stat. That is not a reason
    to refuse the file — the loader below will report the real problem — so the
    spelling is kept and the two spellings simply stay distinguishable.
    """
    try:
        return path.resolve()
    except OSError:
        return path


def _yaml_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return [path]
    return sorted(
        p for p in path.iterdir() if p.is_file() and p.suffix.lower() in (".yaml", ".yml")
    )
