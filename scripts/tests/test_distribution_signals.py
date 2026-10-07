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


def test_the_pypistats_counts_are_labelled_as_excluding_mirrors() -> None:
    get, pauses = _pypi({"guardana-cli": [(200, _RECENT)]})

    found = signals.pypi_signals(get, pauses.append)

    note = _signal(found, "pypi:guardana-cli", "downloads_week").note
    assert note == "excludes mirrors; includes CI"


_TODAY = datetime.date(2026, 10, 7)
"""A Wednesday, so the current week starts on 2026-10-05."""
_LOADED = "2026-10-06"


def _week(week: str, total: object, mirrors: int = 1, ci: int = 0, people: int = 3) -> object:
    return {
        "week": week,
        "all_downloads": total,
        "mirrors": mirrors,
        "in_ci": ci,
        "pip_uv_not_ci": people,
    }


def _answer(
    weeks: Sequence[object], loaded_through: object = _LOADED, first_day: object = "2026-07-20"
) -> str:
    """ClickPy's one-row answer: the dataset's two days and the weeks with a download."""
    row = {"loaded_through": loaded_through, "first_day": first_day, "weeks": list(weeks)}
    return json.dumps(row) + "\n"


def _clickpy(body: str) -> tuple[signals.Query, list[str]]:
    """Answer every query with `body`, recording the SQL asked."""
    asked: list[str] = []

    def query(sql: str) -> tuple[int, str]:
        asked.append(sql)
        return 200, body

    return query, asked


def _monday(today: datetime.date, weeks_back: int) -> datetime.date:
    return today - datetime.timedelta(days=today.weekday(), weeks=weeks_back)


def test_weekly_downloads_are_one_row_per_week_with_the_open_week_partial() -> None:
    query, asked = _clickpy(_answer([_week("2026-09-28", 40, 10, 5, 20), _week("2026-10-05", 7)]))

    weeks = signals.weekly_downloads(query, "guardana-cli", 2, _TODAY)
    lines = signals.render_weekly("guardana-cli", weeks).splitlines()

    assert [week.start for week in weeks] == [
        datetime.date(2026, 9, 28),
        datetime.date(2026, 10, 5),
    ]
    assert weeks[0].counts == signals.WeekCounts(40, 10, 5, 20)
    assert weeks[0].partial_through is None
    assert weeks[1].partial_through == datetime.date(2026, 10, 6)
    assert not any(week.behind for week in weeks)
    assert lines[2].split() == ["2026-09-28", "40", "10", "5", "20"]
    assert lines[3].endswith("(partial: data through 2026-10-06)")
    assert lines[-1] == (
        "pip/uv outside CI in weeks without a release is the closest to people; "
        "all counts are reach, not users."
    )
    assert len(asked) == 1
    assert "date >= '2026-09-28'" in asked[0]


def test_a_week_with_no_downloads_before_the_last_loaded_day_is_zero_not_a_gap() -> None:
    query, _ = _clickpy(_answer([_week("2026-09-21", 9), _week("2026-10-05", 7)]))

    weeks = signals.weekly_downloads(query, "guardana-cli", 3, _TODAY)
    lines = signals.render_weekly("guardana-cli", weeks).splitlines()

    assert weeks[1].start == datetime.date(2026, 9, 28)
    assert weeks[1].counts == signals.WeekCounts(0, 0, 0, 0)
    assert lines[3].split() == ["2026-09-28", "0", "0", "0", "0"]


def test_weeks_with_no_download_at_all_after_the_first_one_are_zero_not_an_error() -> None:
    query, _ = _clickpy(_answer([], first_day="2026-01-05"))

    weeks = signals.weekly_downloads(query, "guardana-cli", 2, _TODAY)

    assert [week.counts for week in weeks] == [signals.WeekCounts(0, 0, 0, 0)] * 2


def test_weeks_after_the_last_loaded_day_are_not_measured() -> None:
    query, _ = _clickpy(_answer([_week("2026-09-21", 9, 1, 1, 4)], loaded_through="2026-09-27"))

    weeks = signals.weekly_downloads(query, "guardana-cli", 3, _TODAY)
    lines = signals.render_weekly("guardana-cli", weeks).splitlines()

    assert weeks[0].counts == signals.WeekCounts(9, 1, 1, 4)
    assert weeks[0].partial_through is None
    assert [week.counts for week in weeks[1:]] == [None, None]
    for line in lines[3:5]:
        assert "not measured" in line
        assert " 0 " not in line


def test_weeks_that_ended_before_the_first_download_are_neither_zero_nor_missing() -> None:
    query, _ = _clickpy(_answer([_week("2026-09-28", 5)], first_day="2026-10-01"))

    weeks = signals.weekly_downloads(query, "guardana-cli", 3, _TODAY)
    lines = signals.render_weekly("guardana-cli", weeks).splitlines()

    assert weeks[0].before_first_download
    assert weeks[0].counts is None
    assert not weeks[0].behind
    assert lines[2].split()[1:] == ["before", "the", "first", "download"]
    assert weeks[1].counts == signals.WeekCounts(5, 1, 0, 3)
    assert weeks[2].counts == signals.WeekCounts(0, 0, 0, 0)


def test_an_ended_week_the_dataset_covers_only_in_part_is_behind() -> None:
    query, _ = _clickpy(_answer([_week("2026-09-28", 5)], loaded_through="2026-10-01"))

    weeks = signals.weekly_downloads(query, "guardana-cli", 2, _TODAY)
    lines = signals.render_weekly("guardana-cli", weeks).splitlines()

    assert weeks[0].partial_through == datetime.date(2026, 10, 1)
    assert weeks[0].behind
    assert lines[2].endswith("(partial: data through 2026-10-01; dataset is behind)")
    assert weeks[1].counts is None
    assert not weeks[1].behind


@pytest.mark.parametrize(
    "body",
    [
        "not json\n",
        _answer([_week("2026-10-05", 7)]) + _answer([_week("2026-10-05", 7)]),
        '{"loaded_through": "2026-10-06", "first_day": "2026-07-20"}\n',
        _answer([{"week": "2026-10-05", "all_downloads": 7}]),
        _answer([_week("2026-10-05", "7")]),
        _answer([_week("2026-10-05", True)]),
        _answer([_week("2026-10-05", -1)]),
        _answer([_week("2026-10-06", 7)]),
        _answer([_week("2025-10-06", 7)]),
        _answer([_week("2026-10-05", 7), _week("2026-10-05", 7)]),
        _answer([_week("2026-10-05", 7)], loaded_through="2026-09-30"),
        _answer([_week("2026-09-28", 7)], first_day="2026-10-05"),
        _answer([_week("2026-10-05", 7)]) + '{"exception": "Code: 241. MEMORY_LIMIT_EXCEEDED"}\n',
        _answer([], loaded_through="yesterday"),
        _answer([], first_day="long ago"),
        _answer([], first_day="2026-10-07"),
        _answer("not a list"),
    ],
    ids=[
        "not-json",
        "two-rows",
        "no-weeks-column",
        "missing-week-columns",
        "count-as-text",
        "count-as-bool",
        "negative-count",
        "week-not-a-monday",
        "week-outside-the-window",
        "duplicate-week",
        "week-after-the-last-loaded-day",
        "week-before-the-first-download",
        "exception-after-the-row",
        "loaded-day-not-a-date",
        "first-day-not-a-date",
        "first-day-after-the-last-loaded-day",
        "weeks-not-a-list",
    ],
)
def test_an_answer_that_does_not_parse_strictly_is_not_measured(body: str) -> None:
    query, _ = _clickpy(body)

    with pytest.raises(signals.NotMeasuredError):
        signals.weekly_downloads(query, "guardana-cli", 2, _TODAY)


def test_counts_and_the_dataset_days_come_from_one_request_to_one_table() -> None:
    query, asked = _clickpy(_answer([_week("2026-10-05", 7)]))

    signals.weekly_downloads(query, "guardana-cli", 2, _TODAY)

    assert len(asked) == 1
    assert "(SELECT max(date) FROM pypi.pypi WHERE project = 'requests')" in asked[0]
    assert "(SELECT minOrNull(date) FROM pypi.pypi WHERE project = 'guardana-cli')" in asked[0]
    assert "FROM pypi.pypi WHERE project = 'guardana-cli' AND date >= '2026-09-28'" in asked[0]
    assert "pypi_downloads_per_day" not in asked[0]


def test_a_distribution_with_no_download_in_the_dataset_is_not_measured_not_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    query, _ = _clickpy(_answer([], first_day=None))
    monkeypatch.setattr(signals, "clickpy", query)

    with pytest.raises(signals.NotMeasuredError, match="no download of guardana-reference-pack"):
        signals.weekly_downloads(query, "guardana-reference-pack", 2, _TODAY)
    assert signals.main(["--weekly", "--project", "guardana-reference-pack"]) == 2
    out = capsys.readouterr().out
    assert "no download of guardana-reference-pack in the dataset; is it on PyPI?" in out
    assert " 0 " not in out


def test_a_project_outside_the_distributions_never_reaches_the_query() -> None:
    query, asked = _clickpy("")

    with pytest.raises(ValueError, match="not a Guardana distribution"):
        signals.weekly_downloads(query, "x' OR 1=1 --", 2, _TODAY)
    assert asked == []


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ((500, '{"exception": "Code: 201. QUOTA_EXCEEDED"}'), "ClickPy answered 500"),
        ((200, "<html>maintenance</html>"), "ClickPy answered something"),
        ((0, "[Errno 8] nodename nor servname provided"), "no answer"),
    ],
    ids=["non-200", "bad-json", "network"],
)
def test_a_failed_weekly_read_prints_not_measured_and_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    answer: tuple[int, str],
    reason: str,
) -> None:
    monkeypatch.setattr(signals, "clickpy", lambda _sql: answer)

    assert signals.main(["--weekly"]) == 2

    out = capsys.readouterr().out
    assert out.startswith("guardana-cli weekly downloads: not measured")
    assert reason in out
    assert len(out.strip().splitlines()) == 1


def test_a_weekly_read_exits_0_and_prints_every_week_asked(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    yesterday = (today - datetime.timedelta(days=1)).isoformat()
    first = _monday(today, 3).isoformat()
    query, asked = _clickpy(_answer([_week(first, 5)], yesterday, first))
    monkeypatch.setattr(signals, "clickpy", query)

    assert signals.main(["--weekly", "--weeks", "4", "--project", "guardana-core"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("guardana-core weekly downloads")
    assert len([line for line in out.splitlines() if line[:4].isdigit()]) == 4
    assert "project = 'guardana-core'" in asked[0]


def test_a_week_that_ended_without_loaded_data_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    first = _monday(today, 2)
    sunday = (first + datetime.timedelta(days=6)).isoformat()
    query, _ = _clickpy(_answer([_week(first.isoformat(), 5)], sunday, first.isoformat()))
    monkeypatch.setattr(signals, "clickpy", query)

    assert signals.main(["--weekly", "--weeks", "3"]) == 2
    out = capsys.readouterr().out
    assert "not measured  (not loaded yet; dataset is behind)" in out
    assert out.count("not measured") == 2


def test_an_ended_week_loaded_only_in_part_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    previous = _monday(today, 1)
    thursday = (previous + datetime.timedelta(days=3)).isoformat()
    query, _ = _clickpy(_answer([_week(previous.isoformat(), 5)], thursday, previous.isoformat()))
    monkeypatch.setattr(signals, "clickpy", query)

    assert signals.main(["--weekly", "--weeks", "2"]) == 2
    assert f"(partial: data through {thursday}; dataset is behind)" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--weekly", "--record"],
        ["--weekly", "--project", "requests"],
        ["--weekly", "--weeks", "0"],
        ["--weekly", "--weeks", "105"],
        ["--weeks", "4"],
        ["--project", "guardana-core"],
    ],
)
def test_weekly_options_out_of_bounds_are_refused(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    query, asked = _clickpy("")
    monkeypatch.setattr(signals, "clickpy", query)
    monkeypatch.setattr(signals, "collect", lambda *_args: pytest.fail("collected"))

    with pytest.raises(SystemExit) as exit_info:
        signals.main(argv)

    assert exit_info.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert asked == []


def test_the_clickpy_request_posts_the_sql_as_the_public_play_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[urllib.request.Request] = []

    class _Answer:
        status = 200

        def __enter__(self) -> "_Answer":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"weeks": []}'

    def urlopen(request: urllib.request.Request, timeout: float) -> _Answer:
        sent.append(request)
        return _Answer()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    assert signals.clickpy("SELECT 1") == (200, '{"weeks": []}')
    assert sent[0].full_url == "https://sql-clickhouse.clickhouse.com/"
    assert sent[0].get_method() == "POST"
    assert sent[0].data == b"SELECT 1"
    assert sent[0].get_header("Authorization") == "Basic cGxheTo="
