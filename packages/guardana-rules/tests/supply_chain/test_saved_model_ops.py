from pathlib import Path

import pytest
from guardana.core.report import ShortfallKind
from guardana.core.rule import RuleContext
from guardana.core.target import ArtifactTarget
from guardana.rules.supply_chain import saved_model_ops
from guardana.rules.supply_chain.saved_model_ops import SavedModelOpsRule


def _findings(tmp_path: Path) -> list[tuple[str, str]]:
    rule = SavedModelOpsRule()
    return [
        (f.severity.name, f.evidence.summary)
        for f in rule.run(ArtifactTarget(tmp_path), RuleContext())
    ]


def _unread(root: Path) -> list[str]:
    """The files the rule names as unread components when run over `root`."""
    ctx = RuleContext()
    list(SavedModelOpsRule().run(ArtifactTarget(root), ctx))
    return [
        gap.name
        for gap in ctx.shortfalls()
        if gap.kind is ShortfallKind.UNEXAMINED_COMPONENT
        and gap.detail.startswith("guardana.supply_chain.saved_model_ops could not read it: ")
    ]


def test_flags_readfile_op(tmp_path: Path) -> None:
    (tmp_path / "saved_model.pb").write_bytes(b"\x08\x01tensorflow...ReadFile...\x00")
    findings = _findings(tmp_path)
    assert len(findings) == 1
    assert findings[0][0] == "MEDIUM"
    assert "ReadFile" in findings[0][1]


def test_flags_writefile_op(tmp_path: Path) -> None:
    (tmp_path / "saved_model.pb").write_bytes(b"tensorflow graph WriteFile op here")
    assert any("WriteFile" in s for _, s in _findings(tmp_path))


def test_reports_each_dangerous_op_once(tmp_path: Path) -> None:
    (tmp_path / "saved_model.pb").write_bytes(b"tensorflow ReadFile ... WriteFile ... ReadFile")
    ops = sorted(s.split()[0] for _, s in _findings(tmp_path))
    assert ops == ["ReadFile", "WriteFile"]


def test_clean_graph_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "saved_model.pb").write_bytes(b"tensorflow MatMul BiasAdd Relu Softmax")
    assert _findings(tmp_path) == []


def test_non_tf_pb_without_ops_is_clean(tmp_path: Path) -> None:
    (tmp_path / "data.pb").write_bytes(b"some other protobuf payload")
    assert _findings(tmp_path) == []


def test_a_graph_past_the_read_bound_is_unverified_and_a_named_shortfall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(saved_model_ops, "_MAX_SCAN_BYTES", 64)
    (tmp_path / "saved_model.pb").write_bytes(b"\x08\x01" + b"\x00" * 128 + b"WriteFile")

    findings = list(SavedModelOpsRule().run(ArtifactTarget(tmp_path), RuleContext()))

    assert [f.title for f in findings] == ["SavedModel not scanned"]
    assert findings[0].verdict is not None
    assert findings[0].verdict.outcome == "inconclusive"
    assert _unread(tmp_path) == [str(tmp_path / "saved_model.pb")]


def test_a_graph_read_whole_is_no_shortfall(tmp_path: Path) -> None:
    (tmp_path / "saved_model.pb").write_bytes(b"\x08\x01 WriteFile")

    assert _unread(tmp_path) == []


def test_an_unreadable_graph_is_unverified_and_a_named_shortfall(tmp_path: Path) -> None:
    path = tmp_path / "saved_model.pb"
    path.write_bytes(b"\x08\x01 WriteFile")
    path.chmod(0)
    ctx = RuleContext()
    try:
        findings = list(SavedModelOpsRule().run(ArtifactTarget(tmp_path), ctx))
    finally:
        path.chmod(0o600)

    assert [(f.title, f.evidence.summary) for f in findings] == [
        ("SavedModel not scanned", "the file could not be read")
    ]
    assert findings[0].verdict is not None
    assert findings[0].verdict.outcome == "inconclusive"
    assert [gap.name for gap in ctx.shortfalls()] == [str(path)]
