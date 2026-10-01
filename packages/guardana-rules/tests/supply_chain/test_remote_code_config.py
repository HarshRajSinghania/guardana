import json
import os
from pathlib import Path

import pytest
from guardana.core.report import Finding
from guardana.core.rule import RuleContext
from guardana.core.severity import Severity
from guardana.core.target import ArtifactTarget
from guardana.rules.supply_chain._reading import MAX_SCAN_BYTES
from guardana.rules.supply_chain.remote_code_config import RemoteCodeConfigRule


def _findings(tmp_path: Path) -> list[tuple[str, str]]:
    rule = RemoteCodeConfigRule()
    return [
        (f.severity.name, f.evidence.summary)
        for f in rule.run(ArtifactTarget(tmp_path), RuleContext())
    ]


def test_auto_map_with_local_module_is_high(tmp_path: Path) -> None:
    # The config points at modeling_evil.py, which ships alongside — the code will
    # run on a trust_remote_code=True load, so this is a firm HIGH finding.
    (tmp_path / "config.json").write_text(
        json.dumps({"auto_map": {"AutoModel": "modeling_evil.EvilModel"}}), encoding="utf-8"
    )
    (tmp_path / "modeling_evil.py").write_text("class EvilModel: ...\n", encoding="utf-8")
    findings = _findings(tmp_path)
    assert len(findings) == 1
    assert findings[0][0] == "HIGH"
    assert "auto_map" in findings[0][1]


def test_auto_map_without_local_module_is_a_medium_lead(tmp_path: Path) -> None:
    # The pointer is present but the module is fetched from the Hub, not shipped —
    # still the RCE-config, but a lead rather than a certainty.
    (tmp_path / "config.json").write_text(
        json.dumps({"auto_map": {"AutoModel": "modeling_remote.Model"}}), encoding="utf-8"
    )
    findings = _findings(tmp_path)
    assert len(findings) == 1
    assert findings[0][0] == "MEDIUM"


def test_custom_pipelines_pointer_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps({"custom_pipelines": {"my-task": {"impl": "pipeline_x.MyPipeline"}}}),
        encoding="utf-8",
    )
    assert _findings(tmp_path)


def test_plain_config_is_clean(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps({"hidden_size": 768, "num_layers": 12, "model_type": "bert"}),
        encoding="utf-8",
    )
    assert _findings(tmp_path) == []


def test_non_config_json_is_ignored(tmp_path: Path) -> None:
    # auto_map in an unrelated JSON file is not a model config — flagging it is noise.
    (tmp_path / "data.json").write_text(json.dumps({"auto_map": {"x": "y.Z"}}), encoding="utf-8")
    assert _findings(tmp_path) == []


def test_malformed_json_config_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{ not valid json", encoding="utf-8")
    assert _findings(tmp_path) == []


def test_flags_the_internal_kernel_field_as_critical(tmp_path: Path) -> None:
    # CVE-2026-4372: any `owner/repo` string in this private field is downloaded
    # from the Hub and imported, and the kernel path sits outside the reach of
    # trust_remote_code=False — the "safe mode" users rely on.
    document = {"model_type": "llama", "_attn_implementation_internal": "attacker/kernel-repo"}
    (tmp_path / "config.json").write_text(json.dumps(document))
    findings = list(RemoteCodeConfigRule().run(ArtifactTarget(tmp_path), RuleContext()))
    assert [f.severity for f in findings] == [Severity.CRITICAL]
    assert findings[0].verdict is None
    assert "CVE-2026-4372" in findings[0].evidence.summary


def test_a_normal_model_reference_is_not_a_kernel_reference(tmp_path: Path) -> None:
    # `_name_or_path` holds an `owner/repo` string in a large share of real
    # configs on the Hub. Matching on shape alone would flag almost every model.
    document = {"model_type": "llama", "_name_or_path": "meta-llama/Meta-Llama-3-8B"}
    (tmp_path / "config.json").write_text(json.dumps(document))
    assert list(RemoteCodeConfigRule().run(ArtifactTarget(tmp_path), RuleContext())) == []


def test_a_builtin_attention_implementation_is_not_flagged(tmp_path: Path) -> None:
    document = {"model_type": "llama", "_attn_implementation_internal": "flash_attention_2"}
    (tmp_path / "config.json").write_text(json.dumps(document))
    assert list(RemoteCodeConfigRule().run(ArtifactTarget(tmp_path), RuleContext())) == []


def test_a_public_kernel_request_is_a_lead(tmp_path: Path) -> None:
    # Asking for a Hub kernel through the documented field is an opt-in, so it is
    # reported the way `trust_remote_code=True` is: a lead, not a compromise.
    document = {"model_type": "llama", "attn_implementation": "kernels-community/flash-attn"}
    (tmp_path / "config.json").write_text(json.dumps(document))
    findings = list(RemoteCodeConfigRule().run(ArtifactTarget(tmp_path), RuleContext()))
    assert [f.severity for f in findings] == [Severity.MEDIUM]
    assert findings[0].verdict is not None


def test_kernel_injection_and_auto_map_are_reported_separately(tmp_path: Path) -> None:
    document = {
        "auto_map": {"AutoModel": "modeling_evil.EvilModel"},
        "_attn_implementation_internal": "attacker/kernel-repo",
    }
    (tmp_path / "config.json").write_text(json.dumps(document))
    findings = list(RemoteCodeConfigRule().run(ArtifactTarget(tmp_path), RuleContext()))
    assert sorted(f.severity for f in findings) == sorted([Severity.MEDIUM, Severity.CRITICAL])


def _unverified(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.verdict is not None and f.verdict.outcome == "inconclusive"]


def _run(tmp_path: Path) -> list[Finding]:
    return list(RemoteCodeConfigRule().run(ArtifactTarget(tmp_path), RuleContext()))


def test_a_config_padded_past_the_read_bound_is_unverified_not_clean(tmp_path: Path) -> None:
    """A loader reads the whole file, so the key behind the padding is applied."""
    document = {"pad": "x" * MAX_SCAN_BYTES, "_attn_implementation_internal": "attacker/kernel"}
    (tmp_path / "config.json").write_text(json.dumps(document), encoding="utf-8")

    findings = _run(tmp_path)

    assert [f.title for f in _unverified(findings)] == ["Model config not scanned"]
    assert "read bound" in findings[0].evidence.summary


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo is POSIX-only")
def test_an_unreadable_config_is_unverified_not_clean(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "config.json")

    assert [f.title for f in _unverified(_run(tmp_path))] == ["Model config not scanned"]


def test_a_config_that_is_not_json_configures_nothing_and_stays_quiet(tmp_path: Path) -> None:
    """`tsconfig.json` allows comments; no model loader reads a file JSON cannot parse."""
    (tmp_path / "tsconfig.json").write_text('{\n  // strict\n  "strict": true\n}\n')

    assert _run(tmp_path) == []
