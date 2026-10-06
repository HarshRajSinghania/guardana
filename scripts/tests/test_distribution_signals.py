"""Distribution signals are read from published numbers only, and a missing one is never zero."""

import csv
import datetime
import http.client
import json
import subprocess
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import pytest

import distribution_signals as signals
from check_repo_settings import Api
from distribution_signals import Signal

_RECENT = json.dumps({"data": {"last_day": 3, "last_week": 21, "last_month": 90}})


_UNPUBLISHED = frozenset({"guardana-reference-pack"})


def _pypi(
    answers: dict[str, list[tuple[int, str]]], unpublished: frozenset[str] = _UNPUBLISHED
) -> tuple[signals.Fetch, list[float]]:
    """Answer pypistats from a queue of (status, body) per name and PyPI from `unpublished`."""
    pauses: list[float] = []

    def get(url: str) -> tuple[int, str]:
        if url.startswith("https://pypi.org/pypi/"):
            name = url.removeprefix("https://pypi.org/pypi/").split("/", 1)[0]
            return (404, "") if name in unpublished else (200, "{}")
        name = url.split("/packages/", 1)[1].split("/", 1)[0]
        queue = answers.get(name, [(404, "")])
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return get, pauses


def _signal(found: Sequence[Signal], source: str, metric: str) -> Signal:
    return next(s for s in found if s.source == source and s.metric == metric)


def test_published_downloads_are_read_per_distribution_and_period() -> None:
    get, pauses = _pypi({"guardana-cli": [(200, _RECENT)]})

    found = signals.pypi_signals(get, pauses.append)

    assert _signal(found, "pypi:guardana-cli", "downloads_week").value == 21
    assert _signal(found, "pypi:guardana-cli", "downloads_month").value == 90
    assert pauses == [signals._PAUSE_SECONDS] * (len(signals.DISTRIBUTIONS) - 1)


def test_a_distribution_pypi_does_not_have_is_absent_rather_than_zero_or_missing() -> None:
    get, pauses = _pypi({})

    found = signals.pypi_signals(get, pauses.append)

    reference = _signal(found, "pypi:guardana-reference-pack", "downloads_month")
    assert reference.value is None
    assert reference.absent
    assert not reference.missing
    assert reference.note == "not on PyPI"


def test_pypistats_answering_404_for_projects_pypi_has_is_not_measured() -> None:
    """A moved route answers 404 for everything; that must not read as "nothing published"."""
    get, pauses = _pypi({}, unpublished=frozenset())

    found = signals.pypi_signals(get, pauses.append)

    assert all(s.missing for s in found)
    assert not any(s.absent for s in found)


def test_a_rate_limited_request_is_retried_and_then_read() -> None:
    get, pauses = _pypi({"guardana-core": [(429, ""), (200, _RECENT)]})

    found = signals.pypi_signals(get, pauses.append)

    assert _signal(found, "pypi:guardana-core", "downloads_day").value == 3
    assert signals._BACKOFF_SECONDS[0] in pauses


def test_a_request_that_stays_rate_limited_is_not_measured() -> None:
    get, pauses = _pypi({"guardana-core": [(429, "")]})

    found = signals.pypi_signals(get, pauses.append)

    core = _signal(found, "pypi:guardana-core", "downloads_day")
    assert core.value is None
    assert "rate limited" in core.note


@pytest.mark.parametrize("day", ["3", True, None])
def test_an_answer_without_its_counts_is_not_measured(day: object) -> None:
    body = json.dumps({"data": {"last_day": day, "last_week": 1, "last_month": 1}})
    get, pauses = _pypi({"guardana-cli": [(200, body)]})

    found = signals.pypi_signals(get, pauses.append)

    assert _signal(found, "pypi:guardana-cli", "downloads_day").value is None


def _gh(answers: dict[str, object]) -> Api:
    """An `Api` whose `gh api` answers each path from `answers`, or 403 for any other."""

    def run(args: Sequence[str]) -> "subprocess.CompletedProcess[str]":
        path = args[-1]
        if path in answers:
            return subprocess.CompletedProcess(list(args), 0, json.dumps(answers[path]), "")
        message = "gh: Must have push access to view repository traffic (HTTP 403)"
        return subprocess.CompletedProcess(list(args), 1, "", message)

    return Api(run)


def _github_answers() -> dict[str, object]:
    query = urllib.parse.quote(signals._ACTION_USES.format(repo="acme/tool"))
    return {
        "repos/acme/tool": {"stargazers_count": 5, "forks_count": 1, "subscribers_count": 2},
        "repos/acme/tool/traffic/views": {"count": 40, "uniques": 9},
        "repos/acme/tool/releases?per_page=100": [
            {"assets": [{"download_count": 4}, {"download_count": 6}]},
            {"assets": []},
        ],
        f"search/code?q={query}": {"total_count": 0, "incomplete_results": False},
    }


def test_github_reach_is_read_and_release_downloads_are_summed() -> None:
    found = signals.github_signals(_gh(_github_answers()), "acme/tool")

    assert _signal(found, "github", "stars").value == 5
    assert _signal(found, "github", "views_14d_unique").value == 9
    assert _signal(found, "github", "release_asset_downloads").value == 10
    assert _signal(found, "github", "workflows_using_the_action").value == 0


def test_traffic_the_token_may_not_read_is_not_measured_under_its_own_names() -> None:
    found = signals.github_signals(_gh(_github_answers()), "acme/tool")

    for metric in ("clones_14d", "clones_14d_unique"):
        clones = _signal(found, "github", metric)
        assert clones.value is None
        assert "push access" in clones.note


def test_a_code_search_that_did_not_finish_is_not_a_count() -> None:
    answers = _github_answers()
    query = urllib.parse.quote(signals._ACTION_USES.format(repo="acme/tool"))
    answers[f"search/code?q={query}"] = {"total_count": 3, "incomplete_results": True}

    found = signals.github_signals(_gh(answers), "acme/tool")

    assert _signal(found, "github", "workflows_using_the_action").value is None


def test_a_broken_http_answer_is_a_failed_read_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_args: object, **_kwargs: object) -> NoReturn:
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(urllib.request, "urlopen", broken)

    status, body = signals.fetch("https://pypistats.org/api/packages/x/recent")

    assert status == 0
    assert "IncompleteRead" in body or "partial" in body


def test_a_repository_that_is_not_owner_slash_name_is_refused() -> None:
    with pytest.raises(SystemExit):
        signals._parser().parse_args(["--repo", "acme/tool; rm -rf"])


_PAGE = 'x <span class="d">Total downloads</span> <h3 title="131">131</h3> y'


def test_an_image_total_is_read_from_its_package_page() -> None:
    found = signals.ghcr_signals(lambda _url: (200, _PAGE), "acme/tool")

    assert [s.value for s in found] == [131, 131]


@pytest.mark.parametrize(("status", "body"), [(200, "<html>moved</html>"), (500, ""), (0, "")])
def test_an_image_total_the_page_does_not_show_is_not_measured(status: int, body: str) -> None:
    found = signals.ghcr_signals(lambda _url: (status, body), "acme/tool")

    assert all(s.value is None for s in found)
    assert all(s.note for s in found)


def test_a_signal_not_measured_is_printed_as_such_and_counted() -> None:
    shown = signals.render([Signal("pypi:x", "downloads_day", None, "rate limited")])

    line = shown.splitlines()[0]
    assert "not measured" in line
    assert " 0 " not in line
    assert "1 signals: 0 measured, 1 not measured, 0 absent" in shown


def test_the_history_gets_its_header_once_and_an_empty_value_for_the_unmeasured(
    tmp_path: Path,
) -> None:
    history = tmp_path / "cache" / "distribution-signals.csv"
    first = [Signal("github", "stars", 5)]
    second = [Signal("pypi:x", "downloads_day", None, "rate limited")]

    signals.record(first, history, datetime.date(2026, 10, 6))
    signals.record(second, history, datetime.date(2026, 10, 7))

    rows = list(csv.reader(history.read_text(encoding="utf-8").splitlines()))
    assert rows == [
        list(signals._FIELDS),
        ["2026-10-06", "github", "stars", "5", ""],
        ["2026-10-07", "pypi:x", "downloads_day", "", "rate limited"],
    ]


def test_the_run_exits_2_when_any_signal_was_not_measured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        signals, "collect", lambda *_args: [Signal("github", "stars", 5), Signal("x", "y", None)]
    )

    assert signals.main([]) == 2
    assert "not measured" in capsys.readouterr().out


def test_the_run_exits_0_when_every_signal_was_read_and_records_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    read = [Signal("github", "stars", 5), Signal("pypi:x", "downloads_day", None, absent=True)]
    monkeypatch.setattr(signals, "collect", lambda *_args: read)
    monkeypatch.setattr(signals, "_ROOT", tmp_path)

    assert signals.main([]) == 0
    assert not (tmp_path / "cache").exists()
    assert signals.main(["--record"]) == 0
    assert (tmp_path / "cache" / "distribution-signals.csv").is_file()
