"""Two runs whose recipes declared a different kind of subject say so.

An application answers with its own prompt, tools and data; a model harness does not. A
difference between the two runs may be that, not the system changing. Said only when
both runs record a recipe: a run started without one declared nothing.
"""

from datetime import UTC, datetime

import pytest
from guardana.core.diff import compare_reports
from guardana.core.gate import GateOutcome
from guardana.core.manifest import RunManifest, TargetIdentity, ToolInfo
from guardana.core.manifest.records import (
    RecipeRecord,
    ResultSummary,
    SubjectKind,
    SubjectSource,
)
from guardana.core.manifest.settings import ConfigurationRef, ExecutionSettings
from guardana.core.manifest.usage import RunUsage
from guardana.core.report import RunReport, ScanResult
from guardana.core.target import TargetKind

_RULE = "acme.prompt.judged"


def _recipe(kind: SubjectKind) -> RecipeRecord:
    return RecipeRecord(
        name="checkout",
        digest="sha256:" + "ab" * 32,
        lock_digest=None,
        kind=kind,
        source=SubjectSource.CONNECTION,
    )


def _report(day: int, kind: SubjectKind | None) -> RunReport:
    when = datetime(2026, 8, day, tzinfo=UTC)
    return RunReport(
        manifest=RunManifest(
            run_id=f"r{day}",
            created_at=when,
            started_at=when,
            completed_at=when,
            guardana=ToolInfo(version="0.35.0"),
            target=TargetIdentity(kind=TargetKind.ENDPOINT, ref="http://x#m"),
            configuration=ConfigurationRef(profile_name="default"),
            execution=ExecutionSettings(concurrency=1, timeout_seconds=30),
            usage=RunUsage(),
            result_summary=ResultSummary(
                findings=0,
                unverified=0,
                waived=0,
                errors=0,
                observations=0,
                rules_run=(_RULE,),
                rules_skipped=(),
                max_severity=None,
                gate=GateOutcome.PASS,
            ),
            recipe=None if kind is None else _recipe(kind),
        ),
        result=ScanResult(findings=(), rules_run=(_RULE,), rules_skipped=()),
    )


def _subject_notes(before: SubjectKind | None, after: SubjectKind | None) -> list[str]:
    diff = compare_reports(_report(1, before), _report(2, after))
    return [note for note in diff.notes if "declared" in note]


def test_runs_whose_recipes_declared_different_subjects_say_so() -> None:
    (note,) = _subject_notes(SubjectKind.MODEL_HARNESS, SubjectKind.APPLICATION)

    assert "model_harness" in note
    assert "application" in note


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (SubjectKind.APPLICATION, SubjectKind.APPLICATION),
        (None, SubjectKind.APPLICATION),
        (SubjectKind.MODEL_HARNESS, None),
        (None, None),
    ],
    ids=["same kind", "first without a recipe", "second without a recipe", "neither"],
)
def test_no_subject_note_unless_both_recipes_declare_and_differ(
    before: SubjectKind | None, after: SubjectKind | None
) -> None:
    assert _subject_notes(before, after) == []
