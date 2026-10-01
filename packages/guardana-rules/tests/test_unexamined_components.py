"""A model component the run observed and no rule read is a coverage shortfall, never clean.

Every case runs the built-in rules over a real tree through the runner, because the
question is what the run concludes, not what one rule returns.
"""

import io
import os
import pickle
import zipfile
from collections.abc import Iterable
from pathlib import Path

from guardana.core.gate import GateOutcome, gate_outcome
from guardana.core.profile import Policy, Profile
from guardana.core.registry import Registry
from guardana.core.report import Evidence, Finding, ScanResult, ShortfallKind
from guardana.core.rule import Rule, RuleContext, RuleMeta
from guardana.core.runner import Runner
from guardana.core.severity import Severity
from guardana.core.target import ArtifactTarget, Capability, FileReader, Target, TargetKind
from guardana.core.taxonomy import OWASP_LLM03_2025
from guardana.rules import provide_rules


class _Evil:
    def __reduce__(self) -> tuple[object, tuple[str]]:
        return (os.system, ("echo pwned",))


def _torch_zip(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("archive/data.pkl", payload)
        archive.writestr("archive/version", "3")
    return buffer.getvalue()


def _scan(root: Path, profile: Profile | None = None) -> ScanResult:
    return Runner(Registry.discover(), profile or Profile(name="t", policy=Policy())).run(
        ArtifactTarget(root)
    )


def _unexamined(result: ScanResult) -> dict[str, str]:
    return {
        gap.name: gap.detail
        for gap in result.coverage_shortfall
        if gap.kind is ShortfallKind.UNEXAMINED_COMPONENT
    }


def test_a_tflite_model_beside_every_built_in_rule_is_a_shortfall(tmp_path: Path) -> None:
    """Whole-tree rules read every file for secrets; none of them reads TFLite."""
    (tmp_path / "model.tflite").write_bytes(b"\x1c\x00\x00\x00TFL3" + b"\x00" * 64)

    result = _scan(tmp_path)

    assert set(_unexamined(result)) == {"tflite"}
    assert "model.tflite" in _unexamined(result)["tflite"]
    assert gate_outcome(result, Policy()) is GateOutcome.INDETERMINATE


def test_a_malicious_pytorch_model_bin_is_found(tmp_path: Path) -> None:
    (tmp_path / "pytorch_model.bin").write_bytes(_torch_zip(pickle.dumps(_Evil())))

    result = _scan(tmp_path)

    assert [f.rule_id for f in result.findings] == ["guardana.supply_chain.pickle_opcode"]
    assert _unexamined(result) == {}


def test_a_clean_pytorch_model_bin_is_read_and_passes(tmp_path: Path) -> None:
    (tmp_path / "pytorch_model.bin").write_bytes(_torch_zip(pickle.dumps({"w": [1, 2]})))

    result = _scan(tmp_path)

    assert result.findings == ()
    assert _unexamined(result) == {}
    assert [o.attributes["format"] for o in result.observations] == ["pytorch"]


def test_a_protocol_zero_pickle_renamed_to_bin_is_found_without_a_signature(
    tmp_path: Path,
) -> None:
    (tmp_path / "weights.bin").write_bytes(pickle.dumps(_Evil(), protocol=0))

    result = _scan(tmp_path)

    assert [f.rule_id for f in result.findings] == ["guardana.supply_chain.pickle_opcode"]


def test_a_ggml_bin_no_rule_reads_is_a_shortfall(tmp_path: Path) -> None:
    (tmp_path / "ggml-model-q4_0.bin").write_bytes(b"tjgg" + b"\x00" * 64)

    assert set(_unexamined(_scan(tmp_path))) == {"ggml"}


def test_a_bin_that_is_no_model_is_neither_a_component_nor_a_finding(tmp_path: Path) -> None:
    (tmp_path / "firmware.bin").write_bytes(b"\x7fELF" + bytes(range(256)))

    result = _scan(tmp_path)

    assert result.observations == ()
    assert result.findings == ()
    assert result.coverage_shortfall == ()


def test_a_profile_that_leaves_out_the_pickle_rule_does_not_pass_over_a_pickle(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.pkl").write_bytes(pickle.dumps({"w": 1}))
    narrowed = Profile(
        name="narrowed", policy=Policy(exclude=("guardana.supply_chain.pickle_opcode",))
    )

    result = _scan(tmp_path, narrowed)

    assert set(_unexamined(result)) == {"pickle"}
    assert gate_outcome(result, narrowed.policy) is GateOutcome.INDETERMINATE


def test_every_model_suffix_a_built_in_rule_reads_leaves_no_shortfall(tmp_path: Path) -> None:
    """The negative: a component some rule read is not reported as unread."""
    (tmp_path / "model.pkl").write_bytes(pickle.dumps({"w": 1}))
    (tmp_path / "model.dill").write_bytes(pickle.dumps({"w": 1}))
    (tmp_path / "model.keras").write_bytes(b"not a zip")
    (tmp_path / "model.onnx").write_bytes(b"\xff" * 11)

    result = _scan(tmp_path)

    assert _unexamined(result) == {}


class _TfliteChecker(Rule):
    """A third party's rule that reads TFLite and never calls `ctx.examined`."""

    meta = RuleMeta(
        id="acme.tflite_check",
        title="TFLite custom op",
        severity=Severity.HIGH,
        target_kind=TargetKind.ARTIFACT,
        taxonomy=(OWASP_LLM03_2025,),
        required_capabilities=frozenset({Capability.READ_FILES}),
    )

    def run(self, target: Target, ctx: RuleContext) -> Iterable[Finding]:
        if not isinstance(target, FileReader):
            return
        for path in target.iter_files((".tflite",)):
            yield Finding(
                self.meta.id,
                Severity.HIGH,
                "custom op",
                self.meta.taxonomy,
                str(path),
                Evidence(summary="declares a custom op"),
            )


def test_a_file_a_rule_reported_on_counts_as_examined_without_the_call(tmp_path: Path) -> None:
    (tmp_path / "model.tflite").write_bytes(b"TFL3")
    registry = Registry()
    for rule in (*provide_rules(), _TfliteChecker()):
        registry.register_rule(rule)

    result = Runner(registry, Profile(name="t", policy=Policy())).run(ArtifactTarget(tmp_path))

    assert _unexamined(result) == {}
    assert [f.rule_id for f in result.findings] == ["acme.tflite_check"]


def _legacy_torch(payload: object) -> bytes:
    """The legacy `torch.save` layout: magic, protocol, sys info, the object, then data."""
    return (
        pickle.dumps(0x1950A86A20F9469CFC6C, protocol=2)
        + pickle.dumps(1001, protocol=2)
        + pickle.dumps({"little_endian": True}, protocol=2)
        + pickle.dumps(payload, protocol=2)
        + pickle.dumps(["0"], protocol=2)
        + (16).to_bytes(8, "little")
        + b"\x00" * 64
    )


def test_a_payload_in_the_fourth_pickle_of_a_legacy_torch_file_is_found(tmp_path: Path) -> None:
    for name in ("model.pt", "pytorch_model.bin"):
        root = tmp_path / name.replace(".", "_")
        root.mkdir()
        (root / name).write_bytes(_legacy_torch(_Evil()))

        result = _scan(root)

        assert [f.rule_id for f in result.findings] == ["guardana.supply_chain.pickle_opcode"]


def test_a_clean_legacy_torch_file_passes_with_its_trailing_data(tmp_path: Path) -> None:
    (tmp_path / "model.pt").write_bytes(_legacy_torch({"w": [1.0, 2.0]}))

    result = _scan(tmp_path)

    assert result.findings == ()
    assert result.unverified == ()


def test_random_bytes_in_a_bin_raise_nothing(tmp_path: Path) -> None:
    """A few random blobs in a thousand parse as an opcode stream; none may be reported."""
    import random  # noqa: PLC0415

    rng = random.Random(1)  # noqa: S311 — test data, not a secret
    for index in range(300):
        (tmp_path / f"blob{index}.bin").write_bytes(rng.randbytes(4096))

    result = _scan(tmp_path)

    assert result.findings == ()
    assert result.unverified == ()


def test_a_pmml_that_is_no_xml_is_not_read_and_not_clean(tmp_path: Path) -> None:
    (tmp_path / "model.pmml").write_bytes(pickle.dumps(_Evil()))

    result = _scan(tmp_path)

    assert set(_unexamined(result)) == {"pmml"}


def test_a_fifo_named_like_a_model_does_not_hang_the_scan(tmp_path: Path) -> None:
    import threading  # noqa: PLC0415

    os.mkfifo(tmp_path / "weights.bin")
    os.mkfifo(tmp_path / "model.pkl")
    done = threading.Event()

    def scan() -> None:
        _scan(tmp_path)
        done.set()

    threading.Thread(target=scan, daemon=True).start()

    assert done.wait(timeout=60), "the scan blocked on a FIFO"


def test_a_header_less_bin_with_one_junk_import_is_still_found(tmp_path: Path) -> None:
    """An unpickler runs `os.system` before it reaches the import it cannot resolve."""
    (tmp_path / "weights.bin").write_bytes(b"cos\nsystem\n(S'id'\ntR" + b"cx-y\nz\n.")

    result = _scan(tmp_path)

    assert "guardana.supply_chain.pickle_opcode" in {f.rule_id for f in result.findings}


def test_a_header_less_bin_that_hides_its_import_operands_is_not_silent(tmp_path: Path) -> None:
    payload = b"}\x94\x8c\x02os\x94\x8c\x06system\x94h\x01h\x02\x93(S'id'\ntR."
    (tmp_path / "weights.bin").write_bytes(payload)

    result = _scan(tmp_path)

    assert {f.rule_id for f in (*result.findings, *result.unverified)} == {
        "guardana.supply_chain.pickle_opcode"
    }


def test_a_7z_archive_named_bin_is_unscanned_rather_than_ignored(tmp_path: Path) -> None:
    (tmp_path / "weights.bin").write_bytes(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 64)

    result = _scan(tmp_path)

    assert [f.rule_id for f in result.unverified] == ["guardana.supply_chain.pickle_opcode"]


def test_a_legacy_storage_size_that_parses_as_an_opcode_is_data(tmp_path: Path) -> None:
    """A 403-element storage writes 0x93 first, which reads as STACK_GLOBAL with no operands."""
    honest = _legacy_torch({"w": [1.0]}).replace(
        (16).to_bytes(8, "little"), (403).to_bytes(8, "little")
    )
    (tmp_path / "model.pt").write_bytes(honest)

    result = _scan(tmp_path)

    assert result.findings == ()
    assert result.unverified == ()
