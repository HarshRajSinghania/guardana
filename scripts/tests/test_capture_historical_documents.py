"""The historical capture script, offline: its table, its environment and what it keeps.

The capture itself needs PyPI and installs every release; none of that runs here. What
runs is every decision the script makes about what it ran and what it kept, so a
change to those is caught before the next capture writes a corpus nobody can trust.
"""

import json
import subprocess
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest

import capture_historical_documents as capture
from capture_historical_documents import (
    COMMAND_TABLE,
    Captured,
    CaptureError,
    Corpus,
    Kind,
    Release,
    Selection,
    commands_for,
    key_paths,
    leaked_markers,
    missing_flags,
    scrubbed_env,
    version_key,
)


class _SideEffectError(Exception):
    """Raised by every stubbed way out of the process."""


@pytest.fixture
def acted(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub every way the script reaches outside the process, and record any attempt."""
    attempts: list[str] = []

    def _stub(name: str) -> Callable[..., Any]:
        def _refuse(*args: object, **kwargs: object) -> NoReturn:
            attempts.append(name)
            raise _SideEffectError(name)

        return _refuse

    monkeypatch.setattr(subprocess, "run", _stub("subprocess.run"))
    monkeypatch.setattr(tempfile, "mkdtemp", _stub("tempfile.mkdtemp"))
    monkeypatch.setattr(urllib.request, "urlopen", _stub("urllib.request.urlopen"))
    return attempts


def test_help_prints_usage_and_does_nothing(
    acted: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        capture.main(["--help"])

    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--dry-run", "--release", "--out", "--keep"):
        assert flag in out
    assert acted == []


def test_an_unknown_flag_is_refused_before_anything_runs(
    acted: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        capture.main(["--no-such-flag"])

    assert exit_info.value.code == 2
    assert "--no-such-flag" in capsys.readouterr().err
    assert acted == []


def test_the_command_table_runs_oldest_first_from_0_2_0() -> None:
    firsts = [version_key(row.first) for row in COMMAND_TABLE]

    assert firsts == sorted(firsts)
    assert len(set(firsts)) == len(firsts)
    assert COMMAND_TABLE[0].first == "0.2.0"


@pytest.mark.parametrize(
    ("version", "first"),
    [
        ("0.2.0", "0.2.0"),
        ("0.6.0", "0.2.0"),
        ("0.7.0", "0.7.0"),
        ("0.8.0", "0.7.0"),
        ("0.9.1", "0.9.0"),
        ("0.25.0", "0.9.0"),
        ("0.26.0", "0.26.0"),
        ("0.40.0", "0.26.0"),
        ("1.0.0rc1", "0.26.0"),
    ],
)
def test_each_release_is_driven_by_the_row_of_its_range(version: str, first: str) -> None:
    assert commands_for(version).first == first


def test_a_release_older_than_the_table_is_refused() -> None:
    with pytest.raises(CaptureError, match="older than the command table"):
        commands_for("0.1.3")


def test_only_the_releases_that_cannot_start_alone_get_an_extra_requirement() -> None:
    extras = {row.first: row.extras for row in COMMAND_TABLE if row.extras}

    assert extras == {"0.7.0": ("click",)}
    for row in COMMAND_TABLE:
        assert bool(row.note) is bool(row.extras), row.first


def test_the_pack_comes_from_new_pack_from_0_26_and_is_handwritten_before() -> None:
    assert commands_for("0.25.0").pack == "handwritten"
    assert commands_for("0.25.0").scaffold is None
    assert commands_for("0.26.0").pack == "scaffolded"
    assert commands_for("0.26.0").scaffold is not None


def test_every_command_line_names_only_relative_paths() -> None:
    for row in COMMAND_TABLE:
        invocations = [row.run, row.envelope, row.probe_run, row.profile, row.lock]
        if row.scaffold is not None:
            invocations.append(row.scaffold)
        for invocation in invocations:
            bound = invocation.bound({"endpoint": 8001, "collector": 8002})
            assert bound[0] == "guardana"
            assert not [arg for arg in bound if arg.startswith(("/", "~"))], bound
            assert not [arg for arg in bound if "{" in arg], bound
            if invocation.writes is not None:
                assert not Path(invocation.writes).is_absolute()


def test_the_servers_ports_reach_the_command_line() -> None:
    row = commands_for("0.40.0")

    assert "server://http://127.0.0.1:8002" in row.envelope.bound({"collector": 8002})
    assert "http://127.0.0.1:8001/v1" in row.probe_run.bound({"endpoint": 8001})


def test_a_release_runs_with_nothing_of_the_caller_but_its_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GUARDANA_COLLECTOR_TOKEN", "a-token-the-release-must-not-see")
    monkeypatch.setenv("PATH", "/opt/bin:/usr/bin")

    env = scrubbed_env(tmp_path)

    assert env == {
        "PATH": "/opt/bin:/usr/bin",
        "HOME": str(tmp_path),
        "HTTP_PROXY": capture.REFUSING_PROXY,
        "HTTPS_PROXY": capture.REFUSING_PROXY,
        "NO_PROXY": "127.0.0.1,localhost",
    }


HELP = """
 Usage: guardana scan [OPTIONS] {path}
│ --profile          <path>   guardana.yaml path                     │
│ --format           <fmt>    human|json|sarif|junit                 │
│ --output-dir       <path>   not the flag the table passes          │
│ --reporter         <str>    Collector URL to forward findings to   │
"""


def test_a_flag_absent_from_the_help_is_what_the_release_lacks() -> None:
    assert missing_flags(HELP, ("--format", "--output")) == ["--output"]
    assert missing_flags(HELP, ("--format", "--reporter")) == []


def test_key_paths_name_fields_and_read_ids_and_list_items_as_one_step() -> None:
    document = {
        "schema_version": 2,
        "run": {"rules": {"guardana.prompt.injection": "ab", "acme.secret": "cd"}},
        "findings": [{"rule_id": "x"}, {"rule_id": "y", "taxonomy": ["LLM01"]}],
    }

    assert key_paths(document) == {
        "schema_version",
        "run",
        "run.rules",
        "run.rules.*",
        "findings",
        "findings[].rule_id",
        "findings[].taxonomy",
    }


def test_a_document_is_kept_when_its_shape_or_its_version_changes_and_only_then() -> None:
    selection = Selection()

    assert selection.keep(Kind.RUN, {"schema_version": 1, "rules": {"a.b": 1}})
    assert not selection.keep(Kind.RUN, {"schema_version": 1, "rules": {"c.d": 2, "e.f": 3}})
    assert selection.keep(Kind.RUN, {"schema_version": 1, "rules": {}, "usage": {}})
    assert selection.keep(Kind.PROFILE, {"schema_version": 1, "rules": {"a.b": 1}})
    assert not selection.keep(Kind.RUN, {"rules": {}, "usage": {}, "schema_version": 1})
    assert selection.keep(Kind.RUN, {"rules": {}, "usage": {}, "schema_version": 2})
    assert not selection.keep(Kind.RUN, {"schema_version": 2, "usage": {}, "rules": {}})


def test_a_local_path_is_a_leak_and_a_path_a_rule_sends_is_not() -> None:
    assert leaked_markers('{"ref": "/Users/someone/subject"}') == ["/Users/"]
    assert leaked_markers('{"detail": "The log file /tmp/session-42.log is gone"}') == []
    assert leaked_markers('{"detail": "/tmp/session-42.log and /tmp/x"}') == ["/tmp/"]  # noqa: S108
    assert leaked_markers('{"ref": "D:/w/subject"}', local=("D:/w",)) == ["D:/w"]


def test_release_candidates_order_before_their_release_and_odd_versions_are_refused() -> None:
    ordered = sorted(["1.0.0", "0.40.0", "1.0.0rc2", "1.0.0rc1", "0.9.1"], key=version_key)

    assert ordered == ["0.9.1", "0.40.0", "1.0.0rc1", "1.0.0rc2", "1.0.0"]
    with pytest.raises(CaptureError, match="not one this script can order"):
        version_key("1.0.0.dev1")


def _captured(**documents: str) -> Captured:
    captured = Captured(facts={"collector_migrations": 3})
    for kind in Kind:
        if kind is Kind.DATASET:
            continue
        text = documents.get(kind.name.lower())
        if text is None:
            captured.absent[kind] = "no `pack lock` command"
        else:
            captured.documents[kind] = text
    captured.datasets = {1: None, 2: "dataset format 2 was written by another version"}
    return captured


def test_the_record_says_what_each_release_produced_stored_and_declared() -> None:
    corpus = Corpus()
    run = json.dumps({"schema_version": 4, "run": {"rules": {"a.b": "1"}}})
    release = Release("0.12.0", "2026-08-07T08:17:07Z")

    produced = corpus.add(release, commands_for("0.12.0"), _captured(run=run))

    assert produced == [Kind.RUN, Kind.DATASET]
    record = corpus.releases["0.12.0"]
    assert record["exclude_newer"] == "2026-08-07T08:17:07Z"
    assert record["collector_migrations"] == 3
    kinds = record["kinds"]
    assert isinstance(kinds, dict)
    assert kinds[Kind.RUN] == {"produced": True, "schema_version": 4, "stored": "run/0.12.0.json"}
    assert kinds[Kind.PACK_LOCK] == {"produced": False, "why": "no `pack lock` command"}
    assert kinds[Kind.DATASET]["stored"] == "dataset/0.12.0.jsonl"
    assert kinds[Kind.DATASET]["schema_version"] == [1]
    assert corpus.files["run/0.12.0.json"] == run


def test_a_release_writing_the_same_shape_is_recorded_but_not_stored() -> None:
    corpus = Corpus()
    for version, digest in (("0.12.0", "1"), ("0.13.0", "2")):
        run = json.dumps({"schema_version": 4, "run": {"rules": {"a.b": digest}}})
        corpus.add(Release(version, "t"), commands_for(version), _captured(run=run))

    later = corpus.releases["0.13.0"]["kinds"]
    assert isinstance(later, dict)
    assert later[Kind.RUN] == {"produced": True, "schema_version": 4, "stored": None}
    assert later[Kind.DATASET]["stored"] is None
    assert sorted(corpus.files) == ["dataset/0.12.0.jsonl", "run/0.12.0.json"]


def test_a_dataset_is_stored_with_the_oldest_release_that_reads_it() -> None:
    corpus = Corpus()
    older, newer = _captured(), _captured()
    older.datasets = {1: None, 2: "refused"}
    newer.datasets = {1: None, 2: None}

    corpus.add(Release("0.30.0", "t"), commands_for("0.30.0"), older)
    corpus.add(Release("0.37.0", "t"), commands_for("0.37.0"), newer)

    assert corpus.files["dataset/0.30.0.jsonl"] == capture.DATASETS[1]
    assert corpus.files["dataset/0.37.0.jsonl"] == capture.DATASETS[2]


def test_one_release_first_reading_both_dataset_formats_stops_the_capture() -> None:
    captured = _captured()
    captured.datasets = {1: None, 2: None}

    with pytest.raises(CaptureError, match="first to read dataset formats"):
        Corpus().add(Release("0.37.0", "t"), commands_for("0.37.0"), captured)


def test_a_release_with_no_dataset_reader_says_so() -> None:
    captured = _captured()
    captured.absent[Kind.DATASET] = "no read_dataset (No module named 'guardana.core.dataset')"

    Corpus().add(Release("0.6.0", "t"), commands_for("0.6.0"), captured)


def test_writing_replaces_every_kind_directory_and_the_record(tmp_path: Path) -> None:
    stale = tmp_path / "run" / "0.1.0.json"
    stale.parent.mkdir()
    stale.write_text("{}", encoding="utf-8")
    unrelated = tmp_path / "README.md"
    unrelated.write_text("kept", encoding="utf-8")
    corpus = Corpus()
    run = json.dumps({"schema_version": 4})
    corpus.add(Release("0.12.0", "t"), commands_for("0.12.0"), _captured(run=run))

    corpus.write(tmp_path)

    assert not stale.exists()
    assert unrelated.read_text(encoding="utf-8") == "kept"
    assert (tmp_path / "run" / "0.12.0.json").read_text(encoding="utf-8") == run
    assert "0.12.0" in json.loads((tmp_path / "releases.json").read_text(encoding="utf-8"))


def test_the_synthetic_datasets_declare_the_format_they_are_filed_under() -> None:
    for fmt, text in capture.DATASETS.items():
        header = json.loads(text.splitlines()[0])
        assert header["guardana_dataset"] == fmt


def test_the_collector_keeps_each_envelope_and_the_endpoint_answers_as_openai() -> None:
    servers = capture._Servers()
    with servers.serving():
        ports = servers.ports
        envelope = json.dumps({"schema_version": 8}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{ports['collector']}/findings", data=envelope, method="POST"
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            assert json.load(response)["status"] == "ok"
        chat = urllib.request.Request(
            f"http://127.0.0.1:{ports['endpoint']}/v1/chat/completions",
            data=json.dumps({"model": "scripted", "messages": []}).encode("utf-8"),
            method="POST",
        )
        with urllib.request.urlopen(chat, timeout=10) as response:  # noqa: S310
            reply = json.load(response)

    assert servers.take() == [envelope]
    assert reply["choices"][0]["message"]["role"] == "assistant"
    assert reply["model"] == "scripted"
