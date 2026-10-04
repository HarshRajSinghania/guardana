"""An output sees no more than the saved run holds; one that sends, no more than the collector.

One fake credential is planted in every channel of a result, in the target ref, in the
stop and judge messages and in a kept exchange. A discovered recording format and a
discovered recording reporter are then run, and what each was handed is read where it
arrived: inside the output's own module.
"""

import sys
from collections.abc import Iterator
from dataclasses import fields, replace
from pathlib import Path

import pytest
from _documents import run_manifest, scan_result
from _fake_distribution import FakeSite
from _output_modules import RECORDING_RENDERER, RECORDING_REPORTER, body
from guardana.core.entrypoints import RENDERER_GROUP, REPORTER_GROUP
from guardana.core.gate import GateOutcome
from guardana.core.manifest.usage import JudgeUsage
from guardana.core.output import (
    DeliveryStatus,
    deliver,
    outbound,
    render,
    select_renderer,
    select_reporter,
)
from guardana.core.plugins import PluginMode, PluginTrust
from guardana.core.recording import RecordedExchange, Recording
from guardana.core.redaction import EvidenceRedactor
from guardana.core.report import ScanResult
from guardana.core.report.finding import Finding
from guardana.core.target import ChatMessage
from guardana.core.verify import Verification

_PLANTED = "AKIA" + "PLANTED0FAKE0KEY"
"""A fake credential in the shape of an access key id, built in code, valid nowhere."""

_REF = f"https://model.invalid/v1?key={_PLANTED}"
_TRUST = PluginTrust(mode=PluginMode.ALLOWLIST, allowed=frozenset({"acme-guardana-outputs"}))

_NOT_TEXT = frozenset({"rules_run", "stopped_by", "usage", "protocols", "trials_per_case"})
"""Channels holding only rule ids, counts or protocol versions, so nothing can be planted."""


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    (tmp_path / "site").mkdir()
    fake = FakeSite(tmp_path / "site", monkeypatch)
    yield fake
    fake.forget_imports()


def _planted_finding(finding: Finding) -> Finding:
    verdict = finding.verdict
    return replace(
        finding,
        title=f"title {_PLANTED}",
        target_ref=f"ref {_PLANTED}",
        evidence=replace(finding.evidence, summary=f"saw {_PLANTED}", detail=f"in {_PLANTED}"),
        verdict=None if verdict is None else replace(verdict, rationale=f"why {_PLANTED}"),
    )


def _planted_result() -> ScanResult:
    base = scan_result()
    scope = base.scope
    return replace(
        base,
        findings=tuple(_planted_finding(f) for f in base.findings),
        unverified=tuple(_planted_finding(f) for f in base.unverified),
        waived=tuple(_planted_finding(f) for f in base.waived),
        errors=tuple(replace(e, reason=f"failed {_PLANTED}") for e in base.errors),
        rules_skipped=tuple(replace(s, detail=f"skipped {_PLANTED}") for s in base.rules_skipped),
        observations=tuple(
            replace(o, ref=f"obs {_PLANTED}", attributes={"seen": _PLANTED})
            for o in base.observations
        ),
        coverage_shortfall=tuple(
            replace(g, detail=f"short {_PLANTED}") for g in base.coverage_shortfall
        ),
        assessments=tuple(replace(a, rationale=f"case {_PLANTED}") for a in base.assessments),
        suites={key: replace(s, reason=f"suite {_PLANTED}") for key, s in base.suites.items()},
        scope=None if scope is None else replace(scope, files=(f"keys/{_PLANTED}.txt",)),
    )


def _kept_exchanges() -> Recording:
    return Recording(
        name="guardana-probe",
        version="run",
        verbatim=False,
        subject=None,
        origin=None,
        exchanges=(
            RecordedExchange(
                rule="guardana.prompt.jailbreak",
                input=(ChatMessage(role="user", content=f"use {_PLANTED}"),),
                reply=f"here is {_PLANTED}",
                meta={"session": _PLANTED, "model": "m"},
            ),
        ),
        digest=None,
    )


def _planted() -> Verification:
    manifest = run_manifest()
    return Verification(
        result=_planted_result(),
        manifest=replace(manifest, target=replace(manifest.target, ref=_REF)),
        gate=GateOutcome.FAIL,
        judge_usage={"judge": JudgeUsage(requests=2, input_tokens=10, output_tokens=5)},
        judge_stops=(f"judge stopped {_PLANTED}",),
        exchanges=_kept_exchanges(),
        stop_messages=(f"the target stopped {_PLANTED}",),
    )


def test_the_credential_is_planted_in_every_channel_that_carries_text() -> None:
    """Fails when a channel is added to `ScanResult` and nothing is planted in it here."""
    result = _planted_result()

    planted = {f.name for f in fields(ScanResult) if _PLANTED in repr(getattr(result, f.name))}

    assert planted == {f.name for f in fields(ScanResult)} - _NOT_TEXT


def _seen(module_name: str) -> Verification:
    (seen,) = sys.modules[module_name].SEEN
    assert isinstance(seen, Verification)
    return seen


def test_a_discovered_format_sees_no_planted_credential(site: FakeSite) -> None:
    module = site.module(body(RECORDING_RENDERER, "acme-table"))
    site.distribution("acme-guardana-outputs", (RENDERER_GROUP, "acme-table", module.name))

    render(select_renderer("acme-table", _TRUST), _planted())

    seen = _seen(module.name)
    assert seen.manifest.target.ref == _REF, "a format is handed the target ref as saved"
    without_ref = replace(
        seen, manifest=replace(seen.manifest, target=replace(seen.manifest.target, ref=""))
    )
    assert _PLANTED not in repr(without_ref)
    assert seen.stop_messages == ()
    assert seen.judge_stops == ()
    assert seen.exchanges is not None
    (exchange,) = seen.exchanges.exchanges
    assert exchange.altered
    assert dict(exchange.meta) == {"model": "m"}


def test_a_discovered_reporter_sees_no_planted_credential(site: FakeSite) -> None:
    module = site.module(body(RECORDING_REPORTER, "acme-webhook"))
    site.distribution("acme-guardana-outputs", (REPORTER_GROUP, "acme-webhook", module.name))

    delivery = deliver(select_reporter("acme-webhook", "x", _TRUST), _planted())

    assert delivery.status is DeliveryStatus.DELIVERED
    seen = _seen(module.name)
    assert _PLANTED not in repr(seen)
    assert seen.manifest.target.ref.startswith("https://model.invalid/v1?key=")
    assert seen.exchanges is None
    assert seen.stop_messages == ()
    assert seen.judge_stops == ()


def test_the_boundary_redacts_the_result_as_the_built_ins_do_and_keeps_the_verdict() -> None:
    given = _planted()

    for leaves_machine in (False, True):
        seen = outbound(given, leaves_machine=leaves_machine)

        assert seen.result == EvidenceRedactor().redact_result(given.result)
        assert seen.gate is given.gate
        assert seen.exit_code == given.exit_code
        assert seen.open_questions == given.open_questions
        assert seen.judge_usage == given.judge_usage
        assert replace(seen.manifest, target=given.manifest.target) == given.manifest


def test_a_target_ref_that_leaves_the_machine_is_redacted_at_redacted_mode() -> None:
    manifest = run_manifest()
    given = Verification(
        result=scan_result(),
        manifest=replace(
            manifest, target=replace(manifest.target, ref="https://owner@example.invalid/v1")
        ),
        gate=GateOutcome.PASS,
    )

    kept = outbound(given, leaves_machine=False).manifest.target.ref
    sent = outbound(given, leaves_machine=True).manifest.target.ref

    assert kept == "https://owner@example.invalid/v1"
    assert "owner@example.invalid" not in sent
    assert sent.startswith("https://")
