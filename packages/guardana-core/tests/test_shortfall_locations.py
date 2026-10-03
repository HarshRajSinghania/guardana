"""A shortfall that names a file names it the way the findings beside it do.

A saved run made on a laptop and one made in CI must name the same unread model the
same way, or comparing them reads every unread file as changed.
"""

from pathlib import Path

from guardana.core.report import CoverageShortfall, ScanResult, ShortfallKind
from guardana.core.report.location import relativize_findings


def _relativized(base: Path, *gaps: CoverageShortfall) -> tuple[CoverageShortfall, ...]:
    result = ScanResult((), (), (), coverage_shortfall=gaps)
    return relativize_findings(result, base).coverage_shortfall


def test_an_unread_component_is_named_relative_to_the_scan_root(tmp_path: Path) -> None:
    model = tmp_path / "models" / "model.onnx"
    gap = CoverageShortfall(
        ShortfallKind.UNEXAMINED_COMPONENT,
        name=str(model),
        detail=f"guardana.supply_chain.onnx_graph could not read it: cannot open {model}",
    )

    (moved,) = _relativized(tmp_path, gap)

    assert moved.name == "models/model.onnx"
    assert moved.detail == (
        "guardana.supply_chain.onnx_graph could not read it: cannot open models/model.onnx"
    )


def test_the_resolved_spelling_of_the_root_is_stripped_too(tmp_path: Path) -> None:
    resolved = tmp_path.resolve() / "model.pkl"
    gap = CoverageShortfall(
        ShortfallKind.UNEXAMINED_COMPONENT, name=str(resolved), detail=f"read {resolved}"
    )

    (moved,) = _relativized(tmp_path, gap)

    assert (moved.name, moved.detail) == ("model.pkl", "read model.pkl")


def test_an_empty_target_is_named_relative_to_the_scan_root(tmp_path: Path) -> None:
    gap = CoverageShortfall(
        ShortfallKind.EMPTY_TARGET, name=str(tmp_path / "empty"), detail="holds no file to scan"
    )

    (moved,) = _relativized(tmp_path, gap)

    assert moved.name == "empty"


def test_a_format_name_passes_unchanged_and_its_listing_loses_the_root(tmp_path: Path) -> None:
    gap = CoverageShortfall(
        ShortfallKind.UNEXAMINED_COMPONENT,
        name="tflite",
        detail=f"1 tflite model component(s) that no rule which ran reads: {tmp_path}/m.tflite",
    )

    (moved,) = _relativized(tmp_path, gap)

    assert moved.name == "tflite"
    assert moved.detail == "1 tflite model component(s) that no rule which ran reads: m.tflite"


def test_a_scan_from_the_filesystem_root_keeps_every_separator_in_the_detail() -> None:
    gap = CoverageShortfall(
        ShortfallKind.UNEXAMINED_COMPONENT, name="srv/m/model.pkl", detail="read srv/m/model.pkl"
    )

    (moved,) = _relativized(Path("/"), gap)

    assert moved.detail == "read srv/m/model.pkl"


def test_a_path_outside_the_root_and_another_kind_are_left_as_they_are(tmp_path: Path) -> None:
    outside = CoverageShortfall(
        ShortfallKind.UNEXAMINED_COMPONENT, name="/elsewhere/model.pkl", detail="/elsewhere/x"
    )
    demanded = CoverageShortfall(
        ShortfallKind.MISSING_DIMENSION, name=str(tmp_path / "a"), detail=str(tmp_path / "a")
    )

    assert _relativized(tmp_path, outside, demanded) == (outside, demanded)
