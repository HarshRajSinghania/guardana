"""A source file the scan could not read must be reported, never silently skipped.

Two ways a `.py` file can fail to become a tree are *not* the file's fault and are
not "nothing to see here": it was too large to read, or it could not be opened.
Both mean the static rules never looked at it, so the run has to say so — an
oversized file that vanishes from the scan is a scanner-bypass anyone can build
by padding a loader with comments.

The other two ways — invalid syntax, undecodable bytes — mean the file is not
runnable Python, so a rule looking for Python constructs has genuinely nothing to
find. Those stay quiet on purpose, and the tests below pin that difference so
neither half drifts.
"""

from pathlib import Path

from guardana.core.profile.model import Policy, Profile
from guardana.core.registry import Registry
from guardana.core.runner import Runner
from guardana.core.source import read_python_source
from guardana.core.target import ArtifactTarget

_SINK = "import os\nos.system('rm -rf /')\n"


def test_an_oversized_file_is_recorded_as_unread(tmp_path: Path) -> None:
    (tmp_path / "huge.py").write_text(_SINK + "# pad\n" * 100, encoding="utf-8")
    target = ArtifactTarget(tmp_path, source_read_limit=32)

    assert target.python_source(tmp_path / "huge.py") is None
    assert [u.path.name for u in target.unread_sources()] == ["huge.py"]
    assert "too large" in target.unread_sources()[0].reason


def test_an_unreadable_file_is_recorded_as_unread(tmp_path: Path) -> None:
    path = tmp_path / "locked.py"
    path.write_text(_SINK, encoding="utf-8")
    path.chmod(0o000)
    try:
        target = ArtifactTarget(tmp_path)
        assert target.python_source(path) is None
        assert [u.path.name for u in target.unread_sources()] == ["locked.py"]
    finally:
        path.chmod(0o644)


def test_unparseable_and_undecodable_files_stay_quiet(tmp_path: Path) -> None:
    # Not runnable Python, so a rule looking for Python constructs has nothing to
    # find — reporting these would be noise on every repo with a Python 2 relic.
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "latin.py").write_bytes(b"# \xff\xfe\nx = 1\n")
    target = ArtifactTarget(tmp_path)
    for name in ("broken.py", "latin.py"):
        assert target.python_source(tmp_path / name) is None
    assert target.unread_sources() == ()


def test_the_same_file_is_reported_once_however_many_rules_asked(tmp_path: Path) -> None:
    (tmp_path / "huge.py").write_text("x = 1\n" * 100, encoding="utf-8")
    target = ArtifactTarget(tmp_path, source_read_limit=8)
    for _ in range(5):
        target.python_source(tmp_path / "huge.py")
    assert len(target.unread_sources()) == 1


def test_a_scan_fails_the_gate_on_an_unread_source(tmp_path: Path) -> None:
    # The whole point: padding a malicious loader past the read limit must not buy
    # a clean report. It lands in `errors`, which fails the gate by default.
    (tmp_path / "loader.py").write_text(_SINK + "# pad\n" * 500, encoding="utf-8")
    target = ArtifactTarget(tmp_path, source_read_limit=64)
    result = Runner(registry=Registry.discover(), profile=Profile(name="t", policy=Policy())).run(
        target
    )
    assert [e.source for e in result.errors] == ["guardana.core.source"]
    assert "loader.py" in result.errors[0].reason


def test_read_python_source_still_returns_none_without_a_target(tmp_path: Path) -> None:
    # The free function stays the simple public entry point third-party rules use.
    (tmp_path / "huge.py").write_text("x = 1\n" * 50, encoding="utf-8")
    assert read_python_source(tmp_path / "huge.py", limit=8) is None


def test_a_directory_that_cannot_be_listed_is_recorded_as_unread(tmp_path: Path) -> None:
    (tmp_path / "seen.py").write_text("x = 1\n", encoding="utf-8")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "model.pkl").write_bytes(b"not a real pickle")
    locked.chmod(0o000)
    try:
        target = ArtifactTarget(tmp_path)
        listed = [path.name for path in target.iter_files()]
        unread = target.unread_sources()
    finally:
        locked.chmod(0o755)

    assert listed == ["seen.py"]
    assert [u.path for u in unread] == [locked]
    assert "locked" in unread[0].reason


def test_a_scan_fails_the_gate_on_a_directory_it_could_not_list(tmp_path: Path) -> None:
    # A subtree nobody could open must not buy a clean report for everything in it.
    locked = tmp_path / "models"
    locked.mkdir()
    (locked / "loader.py").write_text(_SINK, encoding="utf-8")
    locked.chmod(0o000)
    try:
        result = Runner(
            registry=Registry.discover(), profile=Profile(name="t", policy=Policy())
        ).run(ArtifactTarget(tmp_path))
    finally:
        locked.chmod(0o755)

    assert [e.source for e in result.errors] == ["guardana.core.source"]
    assert "models" in result.errors[0].reason


def test_an_excluded_directory_is_not_reported_as_unread(tmp_path: Path) -> None:
    locked = tmp_path / "vendor"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        target = ArtifactTarget(tmp_path, excludes=("vendor",))
        list(target.iter_files())
        unread = target.unread_sources()
    finally:
        locked.chmod(0o755)

    assert unread == ()


def test_a_directory_that_can_be_listed_but_not_entered_does_not_crash_the_scan(
    tmp_path: Path,
) -> None:
    """Its entries cannot be opened or even stat'ed; the run says so instead of failing."""
    from guardana.core.profile import Policy, Profile  # noqa: PLC0415
    from guardana.core.registry import Registry  # noqa: PLC0415
    from guardana.core.runner import Runner  # noqa: PLC0415
    from guardana.core.target import ArtifactTarget  # noqa: PLC0415

    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "model.pkl").write_bytes(b"\x80\x04.")
    locked.chmod(0o400)
    try:
        result = Runner(Registry(), Profile(name="t", policy=Policy())).run(
            ArtifactTarget(tmp_path)
        )
    finally:
        locked.chmod(0o755)

    assert [o.attributes for o in result.observations] == [{"format": "pickle", "read": "failed"}]
