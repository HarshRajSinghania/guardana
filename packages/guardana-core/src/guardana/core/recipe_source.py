"""Pin a distribution installed from a directory or a URL by the files it is made of.

A version pin says nothing about such a distribution: its code can change while its
version stays put. An editable install is pinned by the source directory its
`direct_url.json` names; any other direct URL by the hashes its installed `RECORD` lists.
A distribution too large to read, with a symlink leading out of its directory, or with
nothing to read stays unpinned, with the reason. Design:
`docs/design/guarded-applications.md`, decision 8.
"""

import csv
import hashlib
import importlib.metadata
import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import url2pathname

MAX_SOURCE_FILES = 20_000
"""Above this many files a distribution stays unpinned rather than read."""

MAX_SOURCE_BYTES = 256 * 1024 * 1024
"""Above this many bytes in all a distribution stays unpinned rather than read."""

_TREE_TAG = b"guardana-source-tree-v1"
_RECORD_TAG = b"guardana-source-record-v1"

_EXCLUDED_ANYWHERE = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        ".tox",
        ".nox",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)
_EXCLUDED_AT_TOP = frozenset({"venv", "build", "dist"})
"""Names a package of the project could also carry, so they are left out only at the top."""

_DIST_INFO_KEPT = frozenset({"METADATA", "entry_points.txt"})
"""What in a `.dist-info` says what runs: the version and requirements, and what it registers."""
_REQUIREMENT_NAME = re.compile(r"\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")


@dataclass(frozen=True, slots=True)
class SourcePin:
    """What a distribution's files hash to, and how many files that covers."""

    digest: str
    files: int


def normalized_name(distribution: str) -> str:
    """Return the PEP 503 form of a distribution name, so one project has one name."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


def installed_requirements(distribution: str) -> tuple[str, ...]:
    """Return the installed distributions `distribution` requires, by their normalised names.

    Every `Requires-Dist` counts, markers and extras ignored: an over-approximation, so a
    helper that only an extra pulls in is pinned rather than missed.
    """
    try:
        found = importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError:
        return ()
    names: set[str] = set()
    for requirement in found.requires or ():
        match = _REQUIREMENT_NAME.match(requirement)
        if match is None:
            continue
        name = normalized_name(match.group(1))
        if _installed(name):
            names.add(name)
    return tuple(sorted(names))


def _installed(name: str) -> bool:
    try:
        importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def requirement_closure(
    roots: Iterable[str], requires: Callable[[str], Iterable[str]]
) -> frozenset[str]:
    """Return every normalised name reachable from `roots` through `requires`, roots included."""
    seen: set[str] = set()
    pending = [normalized_name(root) for root in roots]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(normalized_name(required) for required in requires(name))
    return frozenset(seen)


def pin_distribution_source(distribution: str) -> SourcePin | str:
    """Pin an installed distribution by its files, or return why it stays unpinned."""
    try:
        found = importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "it is not installed"
    raw = found.read_text("direct_url.json")
    if raw is None:
        return "it names no direct URL to pin by its files"
    try:
        direct = json.loads(raw)
    except ValueError:
        return "its direct_url.json is not JSON"
    if not isinstance(direct, dict):
        return "its direct_url.json is not an object"
    info = direct.get("dir_info")
    if isinstance(info, dict) and info.get("editable") is True:
        return _editable_pin(direct.get("url"))
    return record_pin(found.read_text("RECORD"))


def _editable_pin(url: object) -> SourcePin | str:
    if not isinstance(url, str):
        return "its editable install names no directory"
    parts = urlsplit(url)
    if parts.scheme != "file":
        return "its editable install names no local directory"
    root = Path(url2pathname(parts.path))
    if not root.is_dir():
        return "the directory its editable install names does not exist"
    return tree_pin(root)


def tree_pin(root: Path) -> SourcePin | str:
    """Pin a source directory: every file but the excluded ones, by path and content.

    Symlinks are followed, so a linked file is pinned by what it holds, and one that
    leads outside `root` leaves the directory unpinned.
    """
    try:
        listed = _listed(root.resolve())
    except OSError as exc:
        return f"its directory cannot be read: {exc.strerror or type(exc).__name__}"
    if isinstance(listed, str):
        return listed
    entries: list[tuple[bytes, str]] = []
    for relative, path in listed:
        try:
            with path.open("rb") as handle:
                content = hashlib.file_digest(handle, "sha256").hexdigest()
        except OSError:
            return f"{relative} cannot be read"
        entries.append((os.fsencode(relative), content))
    return _pin(_TREE_TAG, entries)


def _listed(root: Path) -> list[tuple[str, Path]] | str:
    """Every file to pin under `root`, by POSIX relative path, or why the tree stays unpinned."""
    files: list[tuple[str, Path]] = []
    total = 0
    visited: set[Path] = set()

    def refuse(error: OSError) -> None:
        raise error

    for current, directories, names in os.walk(root, onerror=refuse, followlinks=True):
        here = Path(current)
        real = here.resolve()
        if not real.is_relative_to(root):
            return "a symlink leads outside its directory"
        if real in visited:
            directories[:] = []
            continue
        visited.add(real)
        top = here == root
        directories[:] = sorted(name for name in directories if not _excluded(name, top=top))
        for name in names:
            if name.endswith(".pyc"):
                continue
            path = here / name
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                return "a symlink leads outside its directory"
            total += resolved.stat().st_size
            files.append((PurePosixPath(*path.relative_to(root).parts).as_posix(), path))
            if len(files) > MAX_SOURCE_FILES:
                return f"it holds more than {MAX_SOURCE_FILES} files"
            if total > MAX_SOURCE_BYTES:
                return f"it holds more than {MAX_SOURCE_BYTES // (1024 * 1024)} MiB"
    return files


def _excluded(name: str, *, top: bool) -> bool:
    return (
        name in _EXCLUDED_ANYWHERE
        or name.endswith(".egg-info")
        or (top and name in _EXCLUDED_AT_TOP)
    )


def record_pin(record: str | None) -> SourcePin | str:
    """Pin a distribution by its installed `RECORD`: every entry's path and recorded hash.

    Compiled bytecode and the installer's bookkeeping — every file of the distribution's
    own `.dist-info` but `METADATA` and `entry_points.txt` — are left out, so installing
    the same code again pins the same; any other entry without a hash leaves the
    distribution unpinned.
    """
    if record is None:
        return "it has no RECORD to read"
    entries: list[tuple[bytes, str]] = []
    total = 0
    for row in csv.reader(record.splitlines()):
        if not row:
            continue
        path, recorded, size = (*row, "", "")[:3]
        if _installer_own(path):
            continue
        if not recorded:
            return f"its RECORD lists {path} without a hash"
        total += int(size) if size.isdigit() else 0
        entries.append((path.encode("utf-8"), recorded))
        if len(entries) > MAX_SOURCE_FILES:
            return f"it holds more than {MAX_SOURCE_FILES} files"
        if total > MAX_SOURCE_BYTES:
            return f"it holds more than {MAX_SOURCE_BYTES // (1024 * 1024)} MiB"
    return _pin(_RECORD_TAG, entries)


def _installer_own(path: str) -> bool:
    if path.endswith(".pyc"):
        return True
    parts = PurePosixPath(path).parts
    if not parts or not parts[0].endswith(".dist-info"):
        return False
    return "/".join(parts[1:]) not in _DIST_INFO_KEPT


def _pin(tag: bytes, entries: list[tuple[bytes, str]]) -> SourcePin:
    digest = hashlib.sha256(tag + b"\x00")
    for path, content in sorted(entries):
        digest.update(path + b"\x00" + content.encode("utf-8") + b"\n")
    return SourcePin(digest=f"sha256:{digest.hexdigest()}", files=len(entries))
