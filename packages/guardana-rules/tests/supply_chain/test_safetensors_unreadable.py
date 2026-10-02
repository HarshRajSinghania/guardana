"""A safetensors file nobody could read is not scanned, never a structural verdict."""

from pathlib import Path

from guardana.rules.supply_chain.model_format import _scan_safetensors


def test_a_file_that_cannot_be_opened_is_reported_as_not_scanned(tmp_path: Path) -> None:
    (finding,) = _scan_safetensors(tmp_path / "gone.safetensors")

    assert finding.verdict is not None
    assert finding.verdict.outcome == "inconclusive"
    assert "not scanned" in finding.title


def test_a_malformed_header_is_still_a_structural_finding(tmp_path: Path) -> None:
    path = tmp_path / "bad.safetensors"
    path.write_bytes(b"\x01\x00")

    (finding,) = _scan_safetensors(path)

    assert finding.verdict is None
    assert finding.title == "Malformed safetensors header"
