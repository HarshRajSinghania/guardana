#!/usr/bin/env python3
"""Read what PyPI, GitHub and ghcr publish about Guardana's distribution, for the maintainer.

    uv run python scripts/distribution_signals.py            # print today's signals
    uv run python scripts/distribution_signals.py --record   # also append them to the history
    uv run python scripts/distribution_signals.py --weekly   # per-week downloads of guardana-cli

Guardana itself sends nothing anywhere; every number here is one the registries publish about
the project. They are reach signals, not users: CI jobs, mirrors and the project's own
installs count too, and GitHub keeps traffic for 14 days only, which `--record` turns into a
history in `cache/distribution-signals.csv` (gitignored). A value that could not be read is
"not measured", never zero.

`--weekly` reads ClickPy, the public ClickHouse copy of the PyPI download log, and splits each
week into all downloads, mirrors, CI and pip/uv outside CI; nothing of it is stored.

Exit codes: 0 every signal that exists was read, 2 any not measured. A distribution that is
not on PyPI is "absent", which is a fact rather than a failure.
"""

import argparse
import base64
import csv
import datetime
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from check_repo_settings import DEFAULT_REPO, Api, NotCheckedError, _repository

_ROOT = Path(__file__).resolve().parent.parent
_HISTORY = Path("cache") / "distribution-signals.csv"
DISTRIBUTIONS = (
    "guardana-core",
    "guardana-rules",
    "guardana-cli",
    "guardana-report",
    "guardana-server",
    "guardana-reference-pack",
)
IMAGES = ("guardana", "guardana-collector")
_PYPISTATS = "https://pypistats.org/api/packages/{name}/recent"
_PYPI_PROJECT = "https://pypi.org/pypi/{name}/json"
_GHCR_PAGE = "https://github.com/{repo}/pkgs/container/{image}"
_GHCR_TOTAL = re.compile(r"Total downloads</span>\s*<h3 title=\"(\d+)\">")
_ACTION_USES = '"uses: {repo}@" path:.github/workflows'
_PAUSE_SECONDS = 5.0
"""pypistats.org asks for polite pacing and answers 429 to a burst."""
_BACKOFF_SECONDS = (20.0, 60.0)
"""How long to wait before each retry of a rate-limited request."""
_TIMEOUT_SECONDS = 30
_NOT_FOUND = 404
_RATE_LIMITED = 429
_FIELDS = ("date", "source", "metric", "value", "note")
_PERIODS = {
    "last_day": "downloads_day",
    "last_week": "downloads_week",
    "last_month": "downloads_month",
}
_OK = 200
_CLICKPY = "https://sql-clickhouse.clickhouse.com/"
_CLICKPY_AUTH = "Basic " + base64.b64encode(b"play:").decode("ascii")
"""ClickPy's public read-only account: user `play`, empty password."""
WEEKLY_PROJECT = "guardana-cli"
_WEEKS_DEFAULT = 12
_WEEKS_MAX = 104
# The public account may not turn off ClickHouse's quoting of 64-bit integers in JSON, so the
# counts are cast down; `in_ci` is not called `ci` because that alias would shadow the column.
# ClickPy's replicas can disagree on how far they are loaded, so the dataset's days and the weeks
# come back as one row of one answer, even when no week has a download; `requests` is downloaded
# every day, and `minOrNull` is null rather than 1970-01-01 for a project with no download.
_WEEKLY_SQL = (
    "SELECT (SELECT max(date) FROM pypi.pypi WHERE project = 'requests') AS loaded_through,"
    " (SELECT minOrNull(date) FROM pypi.pypi WHERE project = '{name}') AS first_day,"
    " (SELECT groupArray(CAST((week, all_downloads, mirrors, in_ci, pip_uv_not_ci),"
    " 'Tuple(week Date, all_downloads UInt32, mirrors UInt32, in_ci UInt32,"
    " pip_uv_not_ci UInt32)'))"
    " FROM (SELECT toStartOfWeek(date, 1) AS week,"
    " toUInt32(count()) AS all_downloads,"
    " toUInt32(countIf(installer = 'bandersnatch')) AS mirrors,"
    " toUInt32(countIf(ci = 'true')) AS in_ci,"
    " toUInt32(countIf(installer IN ('pip', 'uv', 'poetry', 'pdm', 'pipenv') AND ci != 'true'))"
    " AS pip_uv_not_ci"
    " FROM pypi.pypi WHERE project = '{name}' AND date >= '{start}' GROUP BY week)) AS weeks"
    " FORMAT JSONEachRow"
)
_WEEK_COLUMNS = ("all_downloads", "mirrors", "in_ci", "pip_uv_not_ci")
_ANSWER_COLUMNS = frozenset({"loaded_through", "first_day", "weeks"})
_WEEKLY_NOTE = (
    "pip/uv outside CI in weeks without a release is the closest to people; "
    "all counts are reach, not users."
)

Fetch = Callable[[str], tuple[int, str]]
Query = Callable[[str], tuple[int, str]]
"""Send one SQL statement to ClickPy and return its status and body; a network failure is 0."""
Sleep = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class Signal:
    """One published number, or why it could not be read."""

    source: str
    metric: str
    value: int | None
    note: str = ""
    absent: bool = False
    """The thing measured does not exist yet (a distribution not on PyPI), so nothing failed."""

    @property
    def missing(self) -> bool:
        """Whether a number that should exist could not be read."""
        return self.value is None and not self.absent


def fetch(url: str) -> tuple[int, str]:
    """GET `url` and return its status and body; a network failure is status 0."""
    request = urllib.request.Request(url, headers={"User-Agent": "guardana-distribution-signals"})  # noqa: S310 — fixed https URLs
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as answer:  # noqa: S310 — fixed https URLs
            return answer.status, answer.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, ""
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as error:
        return 0, str(error)


def pypi_signals(get: Fetch, pause: Sleep) -> list[Signal]:
    """Read each distribution's downloads over the last day, week and month from pypistats.org."""
    signals: list[Signal] = []
    for index, name in enumerate(DISTRIBUTIONS):
        if index:
            pause(_PAUSE_SECONDS)
        source = f"pypi:{name}"
        status, body = get(_PYPISTATS.format(name=name))
        for wait in _BACKOFF_SECONDS:
            if status != _RATE_LIMITED:
                break
            pause(wait)
            status, body = get(_PYPISTATS.format(name=name))
        if status == _NOT_FOUND:
            confirmed, _ = get(_PYPI_PROJECT.format(name=name))
            if confirmed == _NOT_FOUND:
                signals.extend(
                    Signal(source, metric, None, "not on PyPI", absent=True)
                    for metric in _PERIODS.values()
                )
                continue
        why = _pypi_failure(status, body)
        recent = _recent(body) if why is None else None
        if recent is None:
            why = why or "pypistats.org answered something other than its recent counts"
            signals.extend(Signal(source, metric, None, why) for metric in _PERIODS.values())
            continue
        signals.extend(
            Signal(source, metric, recent[key], "excludes mirrors; includes CI")
            for key, metric in _PERIODS.items()
        )
    return signals


def _pypi_failure(status: int, body: str) -> str | None:
    if status == _NOT_FOUND:
        return "pypistats.org has no counts for a project PyPI has, or PyPI could not confirm"
    if status == _RATE_LIMITED:
        return "rate limited by pypistats.org; run again later"
    if status != _OK:
        return f"pypistats.org answered {status}" if status else f"no answer: {body}"
    return None


def _recent(body: str) -> dict[str, int] | None:
    try:
        data = json.loads(body)["data"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    counts = {key: _count(data.get(key)) for key in _PERIODS}
    if any(value is None for value in counts.values()):
        return None
    return {key: value for key, value in counts.items() if value is not None}


def github_signals(api: Api, repo: str) -> list[Signal]:
    """Read stars, forks, watchers, 14-day traffic, release downloads and public Action uses."""
    signals: list[Signal] = []
    signals.extend(_read(api, f"repos/{repo}", _REPOSITORY_METRICS, _repository_counts))
    for kind in ("views", "clones"):
        metrics = (f"{kind}_14d", f"{kind}_14d_unique")
        signals.extend(_read(api, f"repos/{repo}/traffic/{kind}", metrics, _traffic(kind)))
    releases = f"repos/{repo}/releases?per_page=100"
    signals.extend(_read(api, releases, ("release_asset_downloads",), _release_assets))
    query = _ACTION_USES.format(repo=repo)
    signals.extend(
        _read(
            api,
            f"search/code?q={urllib.parse.quote(query)}",
            ("workflows_using_the_action",),
            _action_uses,
        )
    )
    return signals


def _read(
    api: Api, path: str, metrics: Sequence[str], parse: Callable[[object], list[Signal]]
) -> list[Signal]:
    try:
        return parse(api.get(path))
    except NotCheckedError as error:
        return [Signal("github", metric, None, f"{path}: {error}") for metric in metrics]


_REPOSITORY_METRICS = ("stars", "forks", "watchers")


def _repository_counts(answer: object) -> list[Signal]:
    if not isinstance(answer, dict):
        raise NotCheckedError("the repository answer is not an object")
    return [
        Signal("github", metric, _count(answer.get(key)), note)
        for key, metric, note in (
            ("stargazers_count", "stars", ""),
            ("forks_count", "forks", ""),
            ("subscribers_count", "watchers", ""),
        )
    ]


def _traffic(kind: str) -> Callable[[object], list[Signal]]:
    def parse(answer: object) -> list[Signal]:
        if not isinstance(answer, dict):
            raise NotCheckedError(f"the {kind} answer is not an object")
        return [
            Signal("github", f"{kind}_14d", _count(answer.get("count")), "the last 14 days"),
            Signal(
                "github", f"{kind}_14d_unique", _count(answer.get("uniques")), "the last 14 days"
            ),
        ]

    return parse


def _release_assets(answer: object) -> list[Signal]:
    if not isinstance(answer, list):
        raise NotCheckedError("the releases answer is not a list")
    total = 0
    for release in answer:
        assets = release.get("assets") if isinstance(release, dict) else None
        if not isinstance(assets, list):
            raise NotCheckedError("a release without an asset list")
        for asset in assets:
            count = _count(asset.get("download_count") if isinstance(asset, dict) else None)
            if count is None:
                raise NotCheckedError("an asset without a download count")
            total += count
    note = "SBOMs and the reference pack; the 100 newest releases"
    return [Signal("github", "release_asset_downloads", total, note)]


def _action_uses(answer: object) -> list[Signal]:
    if not isinstance(answer, dict):
        raise NotCheckedError("the code search answer is not an object")
    if answer.get("incomplete_results") is not False:
        note = "the code search did not finish, so its count is partial"
        return [Signal("github", "workflows_using_the_action", None, note)]
    note = "public repositories only; private workflows are invisible"
    return [Signal("github", "workflows_using_the_action", _count(answer.get("total_count")), note)]


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def ghcr_signals(get: Fetch, repo: str) -> list[Signal]:
    """Read each image's total downloads as its public package page states them."""
    signals: list[Signal] = []
    for image in IMAGES:
        source = f"ghcr:{image}"
        status, body = get(_GHCR_PAGE.format(repo=repo, image=image))
        if status != _OK:
            why = f"the package page answered {status or 'nothing'}"
            signals.append(Signal(source, "downloads_total", None, why))
            continue
        found = _GHCR_TOTAL.search(body)
        if found is None:
            why = "the package page no longer shows a total where it used to"
            signals.append(Signal(source, "downloads_total", None, why))
            continue
        signals.append(Signal(source, "downloads_total", int(found.group(1)), "page counter"))
    return signals


def collect(api: Api, get: Fetch, pause: Sleep, repo: str) -> list[Signal]:
    """Return every signal, in a stable order."""
    return [*pypi_signals(get, pause), *github_signals(api, repo), *ghcr_signals(get, repo)]


def render(signals: Sequence[Signal]) -> str:
    """Return one line per signal, then how many were measured."""
    width = max((len(f"{s.source} {s.metric}") for s in signals), default=0)
    lines = []
    for signal in signals:
        shown = str(signal.value)
        if signal.value is None:
            shown = "absent" if signal.absent else "not measured"
        label = f"{signal.source} {signal.metric}".ljust(width)
        lines.append(f"{label}  {shown:>12}  {signal.note}".rstrip())
    missing = sum(1 for s in signals if s.missing)
    absent = sum(1 for s in signals if s.absent)
    measured = len(signals) - missing - absent
    lines.append(
        f"{len(signals)} signals: {measured} measured, {missing} not measured, {absent} absent"
    )
    lines.append("These are reach signals, not users; see the module docstring.")
    return "\n".join(lines)


def record(signals: Sequence[Signal], path: Path, today: datetime.date) -> None:
    """Append today's signals to the CSV at `path`, writing its header once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(_FIELDS)
        for signal in signals:
            value = "" if signal.value is None else signal.value
            writer.writerow((today.isoformat(), signal.source, signal.metric, value, signal.note))


class NotMeasuredError(Exception):
    """ClickPy could not be read, so no week can be stated."""


@dataclass(frozen=True, slots=True)
class WeekCounts:
    """One week's downloads, split the ways the download log can tell apart."""

    all_downloads: int
    mirrors: int
    ci: int
    pip_uv_not_ci: int


_NO_DOWNLOADS = WeekCounts(0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class Week:
    """One week starting on Monday, with its counts or None where there is nothing to count."""

    start: datetime.date
    counts: WeekCounts | None
    partial_through: datetime.date | None = None
    """The last loaded day when it falls inside this week, so the week is not complete."""
    before_first_download: bool = False
    """The week ended before the project's first download, so it has no counts and lacks none."""
    behind: bool = False
    """The week has ended but the dataset does not cover all of it: the data is stale."""


def clickpy(sql: str) -> tuple[int, str]:
    """POST `sql` to ClickPy as its public user and return status and body; no answer is 0."""
    request = urllib.request.Request(
        _CLICKPY,
        data=sql.encode("utf-8"),
        method="POST",
        headers={
            "Authorization": _CLICKPY_AUTH,
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "guardana-distribution-signals",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as answer:  # noqa: S310 — a fixed https URL
            return answer.status, answer.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        try:
            return error.code, error.read().decode("utf-8", errors="replace")
        except (http.client.HTTPException, OSError):
            return error.code, ""
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as error:
        return 0, str(error)


def weekly_downloads(query: Query, project: str, weeks: int, today: datetime.date) -> list[Week]:
    """Return `weeks` weeks of `project`'s downloads, the last one being the week of `today`.

    A week the dataset covers without a download had none, so it counts 0; a week that ended
    before the first download has no counts; a week the dataset does not cover has no counts
    and, once it has ended, is `behind`. Raises ValueError for a project outside DISTRIBUTIONS
    or a count outside 1..104, and NotMeasuredError when ClickPy cannot be read or has never
    seen the project.
    """
    if project not in DISTRIBUTIONS:
        raise ValueError(f"{project!r} is not a Guardana distribution")
    if not 1 <= weeks <= _WEEKS_MAX:
        raise ValueError(f"{weeks} weeks is outside 1..{_WEEKS_MAX}")
    current = today - datetime.timedelta(days=today.weekday())
    starts = [current - datetime.timedelta(weeks=back) for back in range(weeks - 1, -1, -1)]
    sql = _WEEKLY_SQL.format(name=project, start=starts[0].isoformat())
    loaded, first_day, rows = _answer(project, _rows(_ask(query, sql)))
    counts = _week_counts(rows, frozenset(starts), first_day, loaded)
    result: list[Week] = []
    for start in starts:
        end = start + datetime.timedelta(days=6)
        if end < first_day:
            result.append(Week(start, None, before_first_download=True))
        elif start > loaded:
            result.append(Week(start, None, behind=end < today))
        else:
            partial = loaded if loaded < end else None
            behind = partial is not None and end < today
            result.append(Week(start, counts.get(start, _NO_DOWNLOADS), partial, behind=behind))
    return result


def _ask(query: Query, sql: str) -> str:
    status, body = query(sql)
    if status == 0:
        raise NotMeasuredError(f"no answer: {body}")
    if status != _OK:
        first = body.strip().splitlines()[0][:200] if body.strip() else "no body"
        raise NotMeasuredError(f"ClickPy answered {status}: {first}")
    return body


def _rows(body: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = None
        if not isinstance(row, dict):
            raise NotMeasuredError("ClickPy answered something other than JSON rows")
        rows.append(row)
    return rows


def _answer(
    project: str, rows: Sequence[dict[str, object]]
) -> tuple[datetime.date, datetime.date, list[object]]:
    """Return the last loaded day, the first download day and the week rows of the one row."""
    if len(rows) != 1 or set(rows[0]) != _ANSWER_COLUMNS:
        raise NotMeasuredError("ClickPy answered something other than one row of the query")
    row = rows[0]
    if row["first_day"] is None:
        raise NotMeasuredError(f"no download of {project} in the dataset; is it on PyPI?")
    loaded, first_day, weeks = _date(row["loaded_through"]), _date(row["first_day"]), row["weeks"]
    if loaded is None or first_day is None or not isinstance(weeks, list):
        raise NotMeasuredError("ClickPy did not say which days its data covers")
    if first_day > loaded:
        raise NotMeasuredError("ClickPy says the first download came after its last loaded day")
    return loaded, first_day, weeks


def _week_counts(
    rows: Sequence[object],
    starts: frozenset[datetime.date],
    first_day: datetime.date,
    loaded: datetime.date,
) -> dict[datetime.date, WeekCounts]:
    counts: dict[datetime.date, WeekCounts] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"week", *_WEEK_COLUMNS}:
            raise NotMeasuredError(f"ClickPy answered a week that is not one: {row}")
        start = _date(row["week"])
        if start not in starts or start in counts:
            raise NotMeasuredError(f"ClickPy answered a week the query did not ask: {row['week']}")
        if start > loaded or start + datetime.timedelta(days=6) < first_day:
            raise NotMeasuredError(f"ClickPy answered a week outside its own days: {start}")
        values = [_count(row[column]) for column in _WEEK_COLUMNS]
        numbers = [value for value in values if value is not None and value >= 0]
        if len(numbers) != len(_WEEK_COLUMNS):
            raise NotMeasuredError(f"ClickPy answered a count that is not one: {row}")
        counts[start] = WeekCounts(*numbers)
    return counts


def _date(value: object) -> datetime.date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def render_weekly(project: str, weeks: Sequence[Week]) -> str:
    """Return the weekly table; a week the dataset does not cover is shown as not measured."""
    lines = [
        f"{project} weekly downloads from ClickPy (weeks start on Monday)",
        f"{'week':<10}  {'all':>7}  {'mirrors':>7}  {'CI':>7}  {'pip/uv not CI':>13}",
    ]
    for week in weeks:
        behind = "; dataset is behind" if week.behind else ""
        if week.before_first_download:
            lines.append(f"{week.start.isoformat():<10}  before the first download")
            continue
        if week.counts is None:
            lines.append(f"{week.start.isoformat():<10}  not measured  (not loaded yet{behind})")
            continue
        counts = week.counts
        line = (
            f"{week.start.isoformat():<10}  {counts.all_downloads:>7}  {counts.mirrors:>7}"
            f"  {counts.ci:>7}  {counts.pip_uv_not_ci:>13}"
        )
        if week.partial_through is not None:
            line += f"  (partial: data through {week.partial_through.isoformat()}{behind})"
        lines.append(line)
    lines.append(_WEEKLY_NOTE)
    return "\n".join(lines)


def _weeks(value: str) -> int:
    try:
        weeks = int(value)
    except ValueError:
        weeks = 0
    if not 1 <= weeks <= _WEEKS_MAX:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a whole number of weeks in 1..{_WEEKS_MAX}"
        )
    return weeks


def _weekly(project: str, weeks: int) -> int:
    today = datetime.datetime.now(tz=datetime.UTC).date()
    try:
        found = weekly_downloads(clickpy, project, weeks, today)
    except NotMeasuredError as error:
        print(f"{project} weekly downloads: not measured ({error})")
        return 2
    print(render_weekly(project, found))
    return 2 if any(week.behind for week in found) else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--repo", type=_repository, default=DEFAULT_REPO, help="OWNER/NAME (default: %(default)s)"
    )
    parser.add_argument(
        "--record", action="store_true", help=f"also append the signals to {_HISTORY}"
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="print per-week downloads from ClickPy instead of today's signals; stores nothing",
    )
    parser.add_argument(
        "--weeks",
        type=_weeks,
        help=f"with --weekly, how many weeks (default: {_WEEKS_DEFAULT}, at most {_WEEKS_MAX})",
    )
    parser.add_argument(
        "--project",
        choices=DISTRIBUTIONS,
        help=f"with --weekly, the distribution to count (default: {WEEKLY_PROJECT})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print the signals or the weekly table, and exit 2 when anything was not measured."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.weekly and args.record:
        parser.error("--weekly stores nothing, so it does not take --record")
    if not args.weekly and (args.weeks is not None or args.project is not None):
        parser.error("--weeks and --project apply only with --weekly")
    if args.weekly:
        return _weekly(args.project or WEEKLY_PROJECT, args.weeks or _WEEKS_DEFAULT)
    signals = collect(Api(), fetch, time.sleep, args.repo)
    print(render(signals))
    if args.record:
        history = _ROOT / _HISTORY
        record(signals, history, datetime.datetime.now(tz=datetime.UTC).date())
        print(f"appended {len(signals)} rows to {history}")
    return 2 if any(s.missing for s in signals) else 0


if __name__ == "__main__":
    sys.exit(main())
