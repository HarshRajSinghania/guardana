"""Pin a distribution installed from a directory or a URL by the files it is made of.

A version pin says nothing about such a distribution: its code can change while its
version stays put. An editable install is pinned by the source directory its
`direct_url.json` names; any other direct URL by the hashes its installed `RECORD` lists.
An editable install whose path file or finder loads code from outside that directory, or
whose path file runs a hook other than a setuptools finder read here, stays unpinned with
the reason; so does a distribution too large to read, with a symlink leading out of its
directory, or with nothing to read. Design: `docs/design/guarded-applications.md`.
"""

import ast
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
        ".idea",
        ".vscode",
    }
)
_EXCLUDED_AT_TOP = frozenset({"venv", "build", "dist", "htmlcov"})
"""Names a package of the project could also carry, so they are left out only at the top."""

_FILES_EXCLUDED_ANYWHERE = frozenset({".DS_Store"})
_FILES_EXCLUDED_AT_TOP = frozenset({".coverage", ".env"})
_COVERAGE_PART = ".coverage."
"""The prefix of a coverage database one parallel test process writes."""

_DIST_INFO_KEPT = frozenset({"METADATA", "entry_points.txt"})
"""What in a `.dist-info` says what runs: the version and requirements, and what it registers."""
_REQUIREMENT_NAME = re.compile(r"\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")
_FINDER_TABLES = frozenset({"MAPPING", "NAMESPACES"})
_PTH_IMPORT = ("import ", "import\t")
"""The prefixes `site` executes, rather than adds to `sys.path`, in a path file."""


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


def pin_distribution_source(
    distribution: str, *, leave_out: Iterable[Path] = ()
) -> SourcePin | str:
    """Pin an installed distribution by its files, or return why it stays unpinned.

    `leave_out` names files and directories an editable tree may hold that are not its
    code, such as the lock and the output of a recipe kept inside it.
    """
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
        return _editable_pin(found, direct.get("url"), leave_out)
    return record_pin(found.read_text("RECORD"))


def _editable_pin(
    found: importlib.metadata.Distribution, url: object, leave_out: Iterable[Path]
) -> SourcePin | str:
    if not isinstance(url, str):
        return "its editable install names no directory"
    parts = urlsplit(url)
    if parts.scheme != "file":
        return "its editable install names no local directory"
    root = Path(url2pathname(parts.path))
    if not root.is_dir():
        return "the directory its editable install names does not exist"
    escaped = _loaded_from_outside(found, root)
    if escaped is not None:
        return escaped
    return tree_pin(root, leave_out=leave_out)


def _loaded_from_outside(found: importlib.metadata.Distribution, root: Path) -> str | None:
    """Why the install imports code its directory does not hold; None when it imports none.

    The path files and setuptools finders its `RECORD` lists are what make an editable
    install importable, so a path one of them names outside `root`, or a hook a path
    file runs other than a finder read here, is code no tree pin covers.
    """
    files = found.files
    if files is None:
        return "it has no RECORD to read"
    inside = root.resolve()
    finders = frozenset(
        entry.stem for entry in files if _is_finder(entry.name) and str(entry) == entry.name
    )
    for entry in files:
        name = entry.name
        finder = _is_finder(name)
        if not finder and not name.endswith(".pth"):
            continue
        located = Path(str(entry.locate()))
        try:
            text = located.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return f"its {name} cannot be read"
        hook = None if finder else _unread_hook(text, finders)
        if hook is not None:
            return f"its {name} runs {hook}, which Guardana cannot read"
        paths = _finder_paths(text) if finder else _path_file_paths(text)
        if paths is None:
            return f"its {name} maps its packages in a way Guardana cannot read"
        for path in paths:
            if not (located.parent / path).resolve().is_relative_to(inside):
                return (
                    f"its {name} loads code from {path}, outside the directory it was "
                    f"installed from"
                )
    return None


def _is_finder(name: str) -> bool:
    """Whether a file name is that of a setuptools editable finder."""
    return name.startswith("__editable__") and name.endswith("finder.py")


def _unread_hook(text: str, finders: frozenset[str]) -> str | None:
    """Name what a `.pth` file runs beyond installing a finder in `finders`; None when nothing.

    `site` executes every `import` line of a path file, so only importing a finder whose
    mapping is read here and calling its `install()` leaves the loaded code known.
    """
    for line in text.splitlines():
        if not line.startswith(_PTH_IMPORT):
            continue
        try:
            statements = ast.parse(line).body
        except (SyntaxError, ValueError):
            return "a line that is not Python"
        for statement in statements:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    if alias.name not in finders or alias.asname is not None:
                        return alias.name
            elif not _installs_finder(statement, finders):
                return "a statement beside its finder"
    return None


def _installs_finder(statement: ast.stmt, finders: frozenset[str]) -> bool:
    """Whether a statement is exactly `<finder>.install()` for a finder in `finders`."""
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    call = statement.value
    target = call.func
    return (
        not call.args
        and not call.keywords
        and isinstance(target, ast.Attribute)
        and target.attr == "install"
        and isinstance(target.value, ast.Name)
        and target.value.id in finders
    )


def _path_file_paths(text: str) -> list[str]:
    """Return the paths a `.pth` file adds to `sys.path`, relative to its own directory.

    Lines are read as `site` reads them. An `import` line runs code rather than naming a
    path, and `_unread_hook` decides whether that code is known.
    """
    return [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.startswith(("#", *_PTH_IMPORT))
    ]


def _finder_paths(text: str) -> list[str] | None:
    """Every path a setuptools editable finder maps a package to; None when it cannot be read."""
    try:
        module = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    tables: dict[str, object] = {}
    for statement in module.body:
        name, value = _assigned(statement)
        if name not in _FINDER_TABLES or value is None:
            continue
        try:
            tables[name] = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError, RecursionError):
            return None
    mapping, namespaces = tables.get("MAPPING"), tables.get("NAMESPACES", {})
    if not isinstance(mapping, dict) or not isinstance(namespaces, dict):
        return None
    paths: list[object] = [*mapping.values()]
    for listed in namespaces.values():
        if not isinstance(listed, list):
            return None
        paths.extend(listed)
    named = [path for path in paths if isinstance(path, str)]
    return named if len(named) == len(paths) else None


def _assigned(statement: ast.stmt) -> tuple[str | None, ast.expr | None]:
    """Return the name a top-level assignment binds and its value; None for anything else."""
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return statement.target.id, statement.value
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ):
        return statement.targets[0].id, statement.value
    return None, None


def tree_pin(root: Path, *, leave_out: Iterable[Path] = ()) -> SourcePin | str:
    """Pin a source directory: every file but the excluded ones, by path and content.

    Untracked files count, since an editable install imports what the directory holds.
    Symlinks are followed, so a linked file is pinned by what it holds, and one that
    leads outside `root` leaves the directory unpinned. `leave_out` names files and
    directories under `root` that are not pinned.
    """
    try:
        listed = _listed(root.resolve(), frozenset(path.resolve() for path in leave_out))
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


def _listed(root: Path, leave_out: frozenset[Path]) -> list[tuple[str, Path]] | str:
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
        top = here == root
        if real in visited or (real in leave_out and not top):
            directories[:] = []
            continue
        visited.add(real)
        directories[:] = sorted(name for name in directories if not _excluded(name, top=top))
        for name in names:
            if _excluded_file(name, top=top):
                continue
            path = here / name
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                return "a symlink leads outside its directory"
            if resolved in leave_out:
                continue
            total += resolved.stat().st_size
            files.append((PurePosixPath(*path.relative_to(root).parts).as_posix(), path))
            above = _above_bounds(len(files), total)
            if above is not None:
                return above
    return files


def _above_bounds(files: int, total: int) -> str | None:
    """Why a distribution of `files` files and `total` bytes is too large to pin; None if not."""
    if files > MAX_SOURCE_FILES:
        return f"it holds more than {MAX_SOURCE_FILES} files"
    if total > MAX_SOURCE_BYTES:
        return f"it holds more than {MAX_SOURCE_BYTES // (1024 * 1024)} MiB"
    return None


def _excluded(name: str, *, top: bool) -> bool:
    return (
        name in _EXCLUDED_ANYWHERE
        or name.endswith(".egg-info")
        or (top and name in _EXCLUDED_AT_TOP)
    )


def _excluded_file(name: str, *, top: bool) -> bool:
    return name in _FILES_EXCLUDED_ANYWHERE or (
        top and (name in _FILES_EXCLUDED_AT_TOP or name.startswith(_COVERAGE_PART))
    )


def record_pin(record: str | None) -> SourcePin | str:
    """Pin a distribution by its installed `RECORD`: every entry's path and recorded hash.

    Bytecode under `__pycache__/`, the installer's bookkeeping — every file of the
    distribution's own `.dist-info` but `METADATA` and `entry_points.txt` — and the
    scripts it generated outside the install root are left out, so installing the same
    code again, into any environment, pins the same; any other entry without a hash
    leaves the distribution unpinned.
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
        above = _above_bounds(len(entries), total)
        if above is not None:
            return above
    return _pin(_RECORD_TAG, entries)


def _installer_own(path: str) -> bool:
    """Whether a `RECORD` entry records the install rather than the code it installed.

    A generated console script embeds the interpreter of the environment it was installed
    into; `entry_points.txt`, which is pinned, says what it calls.
    """
    entry = PurePosixPath(path)
    parts = entry.parts
    if not parts or entry.is_absolute() or parts[0] == "..":
        return True
    if entry.suffix == ".pyc" and "__pycache__" in parts:
        return True
    if parts[0].endswith(".data") and parts[1:2] == ("scripts",):
        return True
    if not parts[0].endswith(".dist-info"):
        return False
    return "/".join(parts[1:]) not in _DIST_INFO_KEPT


def _pin(tag: bytes, entries: list[tuple[bytes, str]]) -> SourcePin:
    digest = hashlib.sha256(tag + b"\x00")
    for path, content in sorted(entries):
        digest.update(path + b"\x00" + content.encode("utf-8") + b"\n")
    return SourcePin(digest=f"sha256:{digest.hexdigest()}", files=len(entries))
