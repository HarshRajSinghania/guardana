#!/usr/bin/env python3
"""Read what PyPI, GitHub and ghcr publish about Guardana's distribution, for the maintainer.

    uv run python scripts/distribution_signals.py            # print today's signals
    uv run python scripts/distribution_signals.py --record   # also append them to the history

Guardana itself sends nothing anywhere; every number here is one the registries publish about
the project. They are reach signals, not users: CI jobs, mirrors and the project's own
installs count too, and GitHub keeps traffic for 14 days only, which `--record` turns into a
history in `cache/distribution-signals.csv` (gitignored). A value that could not be read is
"not measured", never zero.

Exit codes: 0 every signal that exists was read, 2 any not measured. A distribution that is
not on PyPI is "absent", which is a fact rather than a failure.
"""

import argparse
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

Fetch = Callable[[str], tuple[int, str]]
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
            Signal(source, metric, recent[key], "includes CI and mirrors")
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--repo", type=_repository, default=DEFAULT_REPO, help="OWNER/NAME (default: %(default)s)"
    )
    parser.add_argument(
        "--record", action="store_true", help=f"also append the signals to {_HISTORY}"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print the signals, append them when asked, and exit 2 when any was not measured."""
    args = _parser().parse_args(argv)
    signals = collect(Api(), fetch, time.sleep, args.repo)
    print(render(signals))
    if args.record:
        history = _ROOT / _HISTORY
        record(signals, history, datetime.datetime.now(tz=datetime.UTC).date())
        print(f"appended {len(signals)} rows to {history}")
    return 2 if any(s.missing for s in signals) else 0


if __name__ == "__main__":
    sys.exit(main())
