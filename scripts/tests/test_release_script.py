"""The release script refuses twice: it tags only what CI passed, and commits only what it wrote.

Pushing the branch and the tag together races CI against the publish, and a red run
then leaves a publish waiting on the `pypi` approval — a second click, and a cancelled
run in the history that reads as a failed release. Every release from 0.19.0 to 0.21.0
paid that once and 0.20.0 paid it twice, which is why the wait is in the script and not
only in the runbook.

The direction that matters is the refusal. A gate that pushed the tag anyway when it
could not check is the same defect wearing a different hat, so both ways of being unable
to check — no `gh`, and no run to look at — stop before the tag.
"""

import subprocess
import sys

import pytest

import bump_version
import release


def test_a_tag_is_not_pushed_when_ci_cannot_be_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without `gh` there is no way to know, and an unverified tag is the thing avoided."""

    def _no_gh(cmd: list[str], **_: bool) -> str:
        if cmd[0] == "gh":
            raise FileNotFoundError(cmd[0])
        return "cafebabe1234\n"

    monkeypatch.setattr(release, "_run", _no_gh)

    with pytest.raises(SystemExit) as exit_info:
        release._await_green_ci()

    assert exit_info.value.code == 1


def test_a_tag_is_not_pushed_when_no_ci_run_exists_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    """A commit CI has not started on is a commit CI has not passed."""

    def _no_run(cmd: list[str], **_: bool) -> str:
        return "" if cmd[0] == "gh" else "cafebabe1234\n"

    monkeypatch.setattr(release, "_run", _no_run)

    with pytest.raises(SystemExit):
        release._await_green_ci()


def test_a_tag_is_not_pushed_when_ci_is_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gh run watch --exit-status` failing is the whole check, so it has to stop here."""

    def _red(cmd: list[str], **_: bool) -> str:
        if cmd[:3] == ["gh", "run", "watch"]:
            raise subprocess.CalledProcessError(1, cmd)
        return "42\n" if cmd[0] == "gh" else "cafebabe1234\n"

    monkeypatch.setattr(release, "_run", _red)

    with pytest.raises(SystemExit):
        release._await_green_ci()


def test_a_green_run_lets_the_release_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    """The inversion: the same path, green, returns rather than stopping.

    Without this the three refusals above would pass against a gate that refused
    everything, which is a gate nobody could cut a release with.
    """
    watched: list[list[str]] = []

    def _green(cmd: list[str], **_: bool) -> str:
        if cmd[0] == "gh":
            watched.append(cmd)
            return "42\n"
        return "cafebabe1234\n"

    monkeypatch.setattr(release, "_run", _green)

    release._await_green_ci()

    assert ["gh", "run", "watch", "42", "--exit-status"] in watched


_BUMP_PLAN = (
    "0.1.0 -> 0.1.1  (siblings pin ==0.1.1)\n"
    "  would update packages/guardana-core/pyproject.toml\n"
    "  would update docs/install.md\n"
    "dry run: uv.lock not re-locked; no files written.\n"
)
_RELEASED = (
    " M packages/guardana-core/pyproject.toml",
    " M docs/install.md",
    " M CHANGELOG.md",
    " M uv.lock",
    " M site/index.html",
    "?? site/docs/new-page.html",
    " D site/docs/old-page.html",
)


def _cut(
    monkeypatch: pytest.MonkeyPatch,
    status: tuple[str, ...],
    calls: list[list[str]],
    *,
    ci_green: bool = True,
) -> None:
    """Run `release.main`, recording into `calls` every side effect instead of performing it."""

    def _fake(cmd: list[str], **_: bool) -> str:
        calls.append(cmd)
        if "scripts/bump_version.py" in cmd and "--dry-run" in cmd:
            return _BUMP_PLAN
        if cmd[:2] == ["git", "status"]:
            return "".join(f"{line}\0" for line in status)
        return ""

    def _ci() -> None:
        calls.append(["<ci>"])
        if not ci_green:
            raise SystemExit(1)

    monkeypatch.setattr(release, "_run", _fake)
    monkeypatch.setattr(release, "_current_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "_preflight", lambda: None)
    monkeypatch.setattr(release, "_gate", lambda: None)
    monkeypatch.setattr(release, "_roll_changelog", lambda version, dry_run: None)
    monkeypatch.setattr(release, "_await_green_ci", _ci)
    monkeypatch.setattr(release, "_move_marketplace_tag", lambda version, tag: None)
    release.main(["patch"])


def _position(calls: list[list[str]], head: list[str]) -> int:
    return next(i for i, cmd in enumerate(calls) if cmd[: len(head)] == head)


def test_the_tag_is_created_only_after_ci_is_green(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tag that exists before CI is green leaves with any push that follows tags."""
    calls: list[list[str]] = []
    _cut(monkeypatch, _RELEASED, calls)

    push_main = calls[_position(calls, ["git", "push"])]
    assert "--no-follow-tags" in push_main
    assert push_main[-1] == "main"
    assert _position(calls, ["git", "push"]) < _position(calls, ["<ci>"])
    assert _position(calls, ["<ci>"]) < _position(calls, ["git", "tag", "-a"])
    assert calls[-1] == ["git", "push", "origin", "refs/tags/v0.1.1"]


def test_a_red_ci_leaves_no_tag_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    with pytest.raises(SystemExit):
        _cut(monkeypatch, _RELEASED, calls, ci_green=False)

    assert ["<ci>"] in calls
    assert not [cmd for cmd in calls if cmd[:2] == ["git", "tag"]]


def test_the_release_stages_exactly_the_paths_it_wrote(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _cut(monkeypatch, _RELEASED, calls)

    (stage,) = [cmd for cmd in calls if cmd[:2] == ["git", "add"]]
    assert stage[:3] == ["git", "add", "--"]
    assert sorted(stage[3:]) == sorted(line[3:] for line in _RELEASED)
    assert _position(calls, ["git", "add"]) < _position(calls, ["git", "commit"])


@pytest.mark.parametrize(
    "stray",
    [
        " M packages/guardana-core/src/guardana/core/gate.py",
        "?? notes.txt",
        "M  docs/how-it-works.md",
        "R  docs/a.md\0docs/generated/b.md",
    ],
)
def test_a_change_the_release_did_not_write_stops_it_before_the_commit(
    monkeypatch: pytest.MonkeyPatch, stray: str
) -> None:
    """Another session's edit made during the gate is not part of the release."""
    calls: list[list[str]] = []
    with pytest.raises(SystemExit) as exit_info:
        _cut(monkeypatch, (*_RELEASED, stray), calls)

    assert "did not write" in str(exit_info.value.code)
    assert calls[-1][:2] == ["git", "status"]
    assert not [cmd for cmd in calls if cmd[:2] in (["git", "add"], ["git", "commit"])]


def test_the_real_bump_plan_names_every_file_the_bump_rewrites(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The two scripts agree on the plan's format, or the release refuses its own bump."""
    monkeypatch.setattr(sys, "argv", ["bump_version.py", "patch", "--dry-run"])
    assert bump_version.main() == 0

    named = release._bump_writes(capsys.readouterr().out)

    assert {f"packages/{p}/pyproject.toml" for p in bump_version._PACKAGES} <= named
    assert bump_version._DUNDER_PATH.as_posix() in named
    assert {"action.yml", "README.md", "docs/install.md"} <= named


def test_a_bump_plan_names_the_files_the_bump_writes() -> None:
    assert release._bump_writes(_BUMP_PLAN) == frozenset(
        {"packages/guardana-core/pyproject.toml", "docs/install.md"}
    )


def test_the_runbook_moves_the_minor_tag_the_way_the_script_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The moving tag is a lightweight pointer at the release commit, by hand or by script."""
    calls: list[list[str]] = []

    def _record(cmd: list[str], **_: bool) -> str:
        calls.append(cmd)
        return ""

    monkeypatch.setattr(release, "_run", _record)
    release._move_marketplace_tag("0.1.1", "v0.1.1")
    runbook = (release._ROOT / "RELEASING.md").read_text(encoding="utf-8").splitlines()
    by_hand = [line for line in runbook if line.startswith("git tag") and " vX.Y " in line]

    assert calls[0] == ["git", "tag", "-f", "v0.1", "v0.1.1^{commit}"]
    assert by_hand
    assert all(" -a " not in line and "^{commit}" in line for line in by_hand), by_hand
