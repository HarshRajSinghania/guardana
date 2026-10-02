"""A recipe pins what a team's checks are; a moved pin is named, never matched by accident.

The lock is built from the plan of the recipe's run against a target that sends nothing,
so these tests build a plan, lock it, change one thing a team could change without
noticing, and expect exactly that change to come back as drift.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from guardana.core.calibration.store import RecordedCalibration
from guardana.core.evaluator.base import Evaluator, Expectation, Verdict
from guardana.core.exchange import Exchange
from guardana.core.manifest import SubjectKind, SubjectSource
from guardana.core.origin import Origin
from guardana.core.plan import build_plan
from guardana.core.plugins import PluginMode, PluginTrust
from guardana.core.profile import Policy, Profile
from guardana.core.recipe import (
    LockDriftKind,
    Recipe,
    RecipeError,
    RecipeLock,
    compare,
    describe_trust,
    load_recipe,
    lock_of,
    read_lock,
    render_lock,
)
from guardana.core.recording import Recording
from guardana.core.registry import Registry
from guardana.core.rule.yaml_rule import load_yaml_rules
from guardana.core.target import EndpointTarget, RecordedTarget, Target
from guardana.core.testing import ScriptedTransport

_RECIPE = """\
schema_version: 1
name: support-bot
profile: guardana.yaml
subject:
  kind: application
  connection:
    url: http://127.0.0.1:8080
    model: support-bot
output:
  directory: artifact
"""


def _write(tmp_path: Path, text: str = _RECIPE, name: str = "guardana-recipe.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_recipe_resolves_its_paths_beside_itself(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))

    assert recipe.name == "support-bot"
    assert recipe.kind is SubjectKind.APPLICATION
    assert recipe.source is SubjectSource.CONNECTION
    assert recipe.profile == tmp_path / "guardana.yaml"
    assert recipe.output == tmp_path / "artifact"
    assert recipe.keep_exchanges is False
    assert recipe.lock_path == tmp_path / "guardana-recipe.lock.yaml"


def test_a_comment_or_key_order_does_not_change_the_recipe_digest(tmp_path: Path) -> None:
    first = load_recipe(_write(tmp_path, _RECIPE, "a.yaml"))
    reordered = "# reviewed\n" + _RECIPE.replace(
        "schema_version: 1\nname: support-bot\n", "name: support-bot\nschema_version: 1\n"
    )
    second = load_recipe(_write(tmp_path, reordered.replace("\n", "\r\n"), "b.yaml"))

    assert first.digest == second.digest
    changed = load_recipe(_write(tmp_path, _RECIPE.replace("8080", "8081"), "c.yaml"))
    assert changed.digest != first.digest


@pytest.mark.parametrize(
    ("edit", "says"),
    [
        (lambda t: t.replace("  kind: application\n", ""), "subject.kind"),
        (lambda t: t.replace("kind: application", "kind: staging"), "subject.kind"),
        (lambda t: t + "extra: 1\n", "unknown key"),
        (lambda t: t.replace("    model: support-bot\n", ""), "`model`"),
        (lambda t: t.replace("directory: artifact", "directory: ."), "own directory"),
        (lambda t: t.replace("directory: artifact", "directory: ../out"), "beside the recipe"),
        (lambda t: t.replace("directory: artifact", "directory: /tmp/out"), "beside the recipe"),
        (lambda t: t.replace("schema_version: 1", "schema_version: 2"), "upgrade Guardana"),
        (
            lambda t: t.replace("  connection:\n", "  recording: a.jsonl\n  connection:\n"),
            "exactly one",
        ),
    ],
)
def test_a_recipe_that_cannot_be_trusted_as_written_is_refused(
    tmp_path: Path, edit: object, says: str
) -> None:
    assert callable(edit)
    with pytest.raises(RecipeError, match=says):
        load_recipe(_write(tmp_path, edit(_RECIPE)))


_CONNECTION = "  connection:\n    url: http://127.0.0.1:8080\n    model: support-bot\n"


def _recording_recipe(tmp_path: Path, kind: str | None) -> Recipe:
    text = _RECIPE.replace(_CONNECTION, "  recording: answers.jsonl\n")
    declared = "" if kind is None else f"  kind: {kind}\n"
    return load_recipe(_write(tmp_path, text.replace("  kind: application\n", declared)))


def test_a_recording_recipe_may_leave_the_kind_to_the_recording(tmp_path: Path) -> None:
    recipe = _recording_recipe(tmp_path, None)

    assert recipe.kind is None
    assert recipe.run_kind(SubjectKind.MODEL_HARNESS) is SubjectKind.MODEL_HARNESS


@pytest.mark.parametrize("recorded", [SubjectKind.APPLICATION, None])
def test_a_declared_kind_is_the_run_kind_when_the_recording_agrees_or_is_silent(
    tmp_path: Path, recorded: SubjectKind | None
) -> None:
    recipe = _recording_recipe(tmp_path, "application")

    assert recipe.run_kind(recorded) is SubjectKind.APPLICATION


def test_a_kind_the_recording_contradicts_is_refused_naming_both(tmp_path: Path) -> None:
    recipe = _recording_recipe(tmp_path, "application")

    with pytest.raises(RecipeError) as caught:
        recipe.run_kind(SubjectKind.MODEL_HARNESS)

    message = str(caught.value)
    assert "subject.kind: application" in message
    assert "subject_kind: model_harness" in message
    assert str(recipe.path) in message
    assert str(tmp_path / "answers.jsonl") in message


def test_a_kind_neither_the_recipe_nor_the_recording_declares_is_refused(tmp_path: Path) -> None:
    recipe = _recording_recipe(tmp_path, None)

    with pytest.raises(RecipeError, match="it has no default"):
        recipe.run_kind(None)


def test_a_recording_recipe_with_a_kind_that_names_none_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match=r"subject\.kind must be one of"):
        _recording_recipe(tmp_path, "staging")


class _Judge(Evaluator):
    """A judge-shaped evaluator whose identity a test can change."""

    id = "acme.judge"

    def __init__(self, identity: str = "model=judge-1") -> None:
        self.judge_identity = identity

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Pass everything; only the identity matters here."""
        return Verdict("pass", 1.0, "ok", self.id)


def _rule_file(tmp_path: Path, rule_id: str, prompt: str = "hello?") -> Path:
    path = tmp_path / "rules" / f"{rule_id}.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        f"id: {rule_id}\n"
        "title: answers\n"
        "severity: high\n"
        "target_kind: endpoint\n"
        "taxonomy: [LLM01:2025]\n"
        "evaluator: acme.judge\n"
        "requires: [chat]\n"
        f"prompts: [{prompt!r}]\n",
        encoding="utf-8",
    )
    return path


def _registry(
    tmp_path: Path, *rule_ids: str, judge: str = "model=judge-1", prompt: str = "hello?"
) -> Registry:
    registry = Registry()
    for rule_id in rule_ids:
        for rule in load_yaml_rules(_rule_file(tmp_path, rule_id, prompt)):
            registry.register_rule(rule, Origin(source=f"rules/{rule_id}.yaml"))
    registry.register_evaluator(_Judge(judge), Origin(distribution="acme-judges", version="1.0"))
    return registry


def _endpoint() -> Target:
    return EndpointTarget("http://127.0.0.1:8080", "support-bot", transport=ScriptedTransport("x"))


def _lock(  # noqa: PLR0913 — each is a thing a team can change
    recipe: Recipe,
    registry: Registry,
    *,
    profile: Profile | None = None,
    target: Target | None = None,
    calibrations: dict[str, RecordedCalibration] | None = None,
    files: dict[str, str] | None = None,
    movable: frozenset[str] = frozenset(),
) -> RecipeLock:
    prof = profile or Profile("t", Policy())
    plan = build_plan(registry, prof, target or _endpoint())
    return lock_of(
        recipe,
        plan=plan,
        registry=registry,
        profile=prof,
        calibrations=calibrations or {},
        guardana_version="0.36.0",
        subject_files=files or {},
        movable=lambda distribution: distribution in movable,
    )


def _kinds(locked: RecipeLock, current: RecipeLock) -> list[LockDriftKind]:
    return [drift.kind for drift in compare(locked, current)]


def test_an_unchanged_configuration_matches_its_lock(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    locked = _lock(recipe, _registry(tmp_path, "acme.a", "acme.b"))

    assert sorted(locked.rules) == ["acme.a", "acme.b"]
    assert locked.evaluators["acme.judge"].judge == "model=judge-1"
    assert compare(locked, _lock(recipe, _registry(tmp_path, "acme.a", "acme.b"))) == ()


def test_a_changed_rule_an_added_one_and_a_removed_one_are_each_named(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    locked = _lock(recipe, _registry(tmp_path, "acme.a", "acme.b"))
    (tmp_path / "rules" / "acme.b.yaml").unlink()

    changed = _lock(recipe, _registry(tmp_path, "acme.a", "acme.c", prompt="goodbye?"))

    drift = {(d.kind, d.subject) for d in compare(locked, changed)}
    assert (LockDriftKind.RULE_CHANGED, "acme.a") in drift
    assert (LockDriftKind.RULE_ADDED, "acme.c") in drift
    assert (LockDriftKind.RULE_REMOVED, "acme.b") in drift


def test_a_new_judge_and_a_new_calibration_are_drift_although_no_rule_moved(
    tmp_path: Path,
) -> None:
    recipe = load_recipe(_write(tmp_path))
    measured = RecordedCalibration(
        evaluator="acme.judge",
        dataset_digest="sha256:" + "0" * 64,
        measured_at=datetime(2026, 1, 1, tzinfo=UTC),
        brier=0.1,
        ece=0.05,
        samples=200,
    )
    locked = _lock(recipe, _registry(tmp_path, "acme.a"), calibrations={"acme.judge": measured})

    rejudged = _lock(
        recipe,
        _registry(tmp_path, "acme.a", judge="model=judge-2"),
        calibrations={"acme.judge": replace(measured, ece=0.2)},
    )

    assert _kinds(locked, rejudged) == [
        LockDriftKind.JUDGE_CHANGED,
        LockDriftKind.CALIBRATION_CHANGED,
    ]


def test_a_profile_change_trust_change_and_subject_file_change_are_drift(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    registry = _registry(tmp_path, "acme.a")
    locked = _lock(recipe, registry, files={"adapter": "sha256:aa"})
    stricter = Profile("t", Policy(), trials=3)
    registry.apply_trials(3)

    current = _lock(recipe, registry, profile=stricter, files={"adapter": "sha256:bb"})
    current = replace(current, trust=describe_trust(PluginTrust(mode=PluginMode.BUILTINS)))

    kinds = _kinds(locked, current)
    assert LockDriftKind.PROFILE_CHANGED in kinds
    assert LockDriftKind.TRUST_CHANGED in kinds
    assert LockDriftKind.SUBJECT_FILE_CHANGED in kinds


def test_a_distribution_that_can_change_under_one_version_is_unpinned(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))

    locked = _lock(recipe, _registry(tmp_path, "acme.a"), movable=frozenset({"acme-judges"}))

    assert locked.unpinned == ("evaluator:acme.judge",)


def test_a_recording_subject_pins_the_rules_its_configuration_selects(tmp_path: Path) -> None:
    """The recording is the subject's answer: an unanswered rule is still a selected rule."""
    recipe = load_recipe(
        _write(
            tmp_path,
            _RECIPE.replace(
                "  connection:\n    url: http://127.0.0.1:8080\n    model: support-bot\n",
                "  recording: answers.jsonl\n",
            ),
        )
    )
    empty = Recording(
        "lock", "0", verbatim=True, subject=None, origin=None, exchanges=(), digest=None
    )

    locked = _lock(recipe, _registry(tmp_path, "acme.a"), target=RecordedTarget(empty))

    assert recipe.source is SubjectSource.RECORDING
    assert list(locked.rules) == ["acme.a"]
    assert locked.skipped == {}


def test_the_lock_file_round_trips_and_its_digest_is_stable(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    locked = _lock(recipe, _registry(tmp_path, "acme.a"), files={"system_prompt_file": "sha256:cc"})
    path = tmp_path / "guardana-recipe.lock.yaml"
    path.write_text(render_lock(locked), encoding="utf-8")

    read = read_lock(path)

    assert read == locked
    assert read.digest == locked.digest
    assert "digest:" in path.read_text(encoding="utf-8")


def test_a_lock_written_by_a_newer_guardana_is_refused_not_relocked(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    text = render_lock(_lock(recipe, _registry(tmp_path, "acme.a")))
    path = tmp_path / "lock.yaml"
    path.write_text(text.replace("schema_version: 1", "schema_version: 2"), encoding="utf-8")

    with pytest.raises(RecipeError, match="upgrade Guardana"):
        read_lock(path)


def test_a_missing_lock_says_how_to_write_one(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="guardana recipe lock"):
        read_lock(tmp_path / "absent.yaml")


def test_a_calibration_re_measured_on_more_samples_is_drift(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    measured = RecordedCalibration(
        evaluator="acme.judge",
        dataset_digest="sha256:" + "0" * 64,
        measured_at=datetime(2026, 1, 1, tzinfo=UTC),
        brier=0.1,
        ece=0.05,
        samples=200,
    )
    registry = _registry(tmp_path, "acme.a")
    locked = _lock(recipe, registry, calibrations={"acme.judge": measured})

    current = _lock(recipe, registry, calibrations={"acme.judge": replace(measured, samples=300)})

    assert _kinds(locked, current) == [LockDriftKind.CALIBRATION_CHANGED]
