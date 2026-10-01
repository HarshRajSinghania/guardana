"""A file run records every file it listed and the excludes it applied, with their source."""

from collections.abc import Iterator
from pathlib import Path

from guardana.core.plugins import PluginMode, PluginTrust
from guardana.core.profile import default_profile
from guardana.core.registry import Registry
from guardana.core.report import ScanResult
from guardana.core.report.location import relativize_findings
from guardana.core.runner import Runner
from guardana.core.source import PythonSource, UnreadSource
from guardana.core.target import ArtifactTarget, Capability, Target, TargetKind
from guardana.core.target.scope import ExcludePattern, ExcludeSource, FileScope


def _run(target: Target) -> ScanResult:
    return Runner(Registry(), default_profile()).run(target)


def test_a_directory_scan_records_its_listing_and_where_each_exclude_came_from(
    tmp_path: Path,
) -> None:
    (tmp_path / "kept.txt").write_text("x")
    (tmp_path / "ignored.pkl").write_text("x")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "hidden.pkl").write_text("x")
    (tmp_path / ".guardanaignore").write_text("# comment\nignored.pkl\n")

    scope = _run(ArtifactTarget(tmp_path, excludes=("vendor/*",))).scope

    assert scope is not None
    assert scope.files == (str(tmp_path / ".guardanaignore"), str(tmp_path / "kept.txt"))
    assert scope.excludes == (
        ExcludePattern("vendor/*", ExcludeSource.PROFILE),
        ExcludePattern("ignored.pkl", ExcludeSource.IGNORE_FILE),
    )
    assert "build" in scope.ignored_directories


def test_the_scope_names_what_kept_a_path_out(tmp_path: Path) -> None:
    (tmp_path / ".guardanaignore").write_text("model/*.pkl\n")
    scope = _run(ArtifactTarget(tmp_path, excludes=("vendor",))).scope

    assert scope is not None
    assert scope.exclusion_of("model/weights.pkl") == (
        "excluded by 'model/*.pkl' from .guardanaignore"
    )
    assert scope.exclusion_of("vendor/lib/x.py") == (
        "excluded by 'vendor' from the profile's rules.paths_exclude"
    )
    assert scope.exclusion_of("model/build/weights.pkl") == (
        "inside 'model/build', a directory every scan skips"
    )
    assert scope.exclusion_of("pkg.egg-info/x") == (
        "inside 'pkg.egg-info', a directory every scan skips"
    )
    assert scope.exclusion_of("model/weights.safetensors") is None


def test_a_single_file_root_records_no_excludes_because_none_applies(tmp_path: Path) -> None:
    model = tmp_path / "model.pkl"
    model.write_text("x")

    scope = _run(ArtifactTarget(model, excludes=("*.pkl",))).scope

    assert scope == FileScope(files=(str(model),), excludes=(), ignored_directories=())


class _ThirdPartyFiles(Target):
    """A file target that applies its own filtering and does not report it."""

    kind = TargetKind.ARTIFACT

    def __init__(self, root: Path) -> None:
        self._root = root

    def capabilities(self) -> set[Capability]:
        return {Capability.READ_FILES}

    @property
    def ref(self) -> str:
        return str(self._root)

    def iter_files(self, suffixes: tuple[str, ...] | None = None) -> Iterator[Path]:
        wanted = None if suffixes is None else {s.lower() for s in suffixes}
        for path in sorted(self._root.iterdir()):
            if wanted is None or path.suffix.lower() in wanted:
                yield path

    def python_source(self, path: Path) -> PythonSource | None:
        return None

    def unread_sources(self) -> tuple[UnreadSource, ...]:
        return ()


class _CountingFiles(_ThirdPartyFiles):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.walks = 0

    def iter_files(self, suffixes: tuple[str, ...] | None = None) -> Iterator[Path]:
        if suffixes is None:
            self.walks += 1
        return super().iter_files(suffixes)


def test_a_third_party_file_target_is_listed_once_for_the_scope_and_the_inventory(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.onnx").write_text("x")
    target = _CountingFiles(tmp_path)

    result = _run(target)

    assert target.walks == 1
    assert [o.name for o in result.observations] == ["model.onnx"]


def test_a_third_party_file_target_is_listed_with_its_excludes_unknown(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")

    scope = _run(_ThirdPartyFiles(tmp_path)).scope

    assert scope == FileScope(files=(str(tmp_path / "a.py"),), excludes=None)


def test_the_listing_is_relativized_like_the_findings(tmp_path: Path) -> None:
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "a.py").write_text("x")

    result = relativize_findings(_run(ArtifactTarget(tmp_path / "model")), tmp_path)

    assert result.scope is not None
    assert result.scope.files == ("model/a.py",)


def test_a_merged_result_keeps_unknown_excludes_unknown() -> None:
    known = ScanResult((), ("r",), (), scope=FileScope(files=("a",), excludes=()))
    unknown = ScanResult((), ("r",), (), scope=FileScope(files=("b",), excludes=None))

    merged = ScanResult.merged([known, unknown])

    assert merged.scope == FileScope(files=("a", "b"), excludes=None)


def test_a_run_against_no_files_records_no_scope() -> None:
    assert ScanResult.merged([ScanResult((), ("r",), ())]).scope is None


def test_the_registry_reports_the_trust_it_discovered_under() -> None:
    trust = PluginTrust(mode=PluginMode.BUILTINS)

    assert Registry.discover(trust).trust == trust
    assert Registry().trust is None
    assert Registry.discover(trust).empty_with_load_state().trust == trust
