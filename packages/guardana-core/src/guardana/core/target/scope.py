"""What a file scan listed and what it left out on purpose.

Recorded on the result so a later reader can tell a file the scan excluded, or no
longer listed at all, from a file it read and found clean. A comparison that cannot
make that distinction reads a moved or ignored file as a fixed one.
"""

from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import Protocol, runtime_checkable

IGNORED_DIRECTORIES: tuple[str, ...] = (
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "node_modules",
    ".tox",
    ".eggs",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "*.egg-info",
)
"""Directory names every file scan skips wherever they occur, matched as glob patterns."""


IGNORE_FILE = ".guardanaignore"
"""The file whose glob patterns a directory scan excludes, read at the scanned root."""


class ExcludeSource(StrEnum):
    """Where an exclude pattern came from, so the person who can change it is named."""

    PROFILE = "profile"
    """`rules.paths_exclude` in the profile the run was given."""

    IGNORE_FILE = "ignore_file"
    """`.guardanaignore` at the scanned root."""


@dataclass(frozen=True, slots=True)
class ExcludePattern:
    """One glob a scan matched against each path relative to its root."""

    pattern: str
    source: ExcludeSource


@dataclass(frozen=True, slots=True)
class FileScope:
    """Every file a scan listed, and the excludes it applied while listing them.

    `files` holds the paths as the run's findings name them, so a finding's location
    and a listed file compare directly. `excludes` is None when the target applied
    excludes it does not report — a third-party file target — which is unknown, never
    "none applied".
    """

    files: tuple[str, ...] = ()
    excludes: tuple[ExcludePattern, ...] | None = ()
    ignored_directories: tuple[str, ...] = ()

    def exclusion_of(self, relative: str) -> str | None:
        """Describe what kept `relative` (a path under the scanned root) out of the scan.

        Mirrors how a scan prunes: a directory leaves everything beneath it out when
        its name is ignored or its path matches an exclude, and a file leaves when its
        own path matches one. None when nothing recorded here excludes the path.
        """
        parts = PurePosixPath(relative).parts
        for depth in range(1, len(parts) + 1):
            prefix = "/".join(parts[:depth])
            is_directory = depth < len(parts)
            if is_directory:
                ignored = next(
                    (name for name in self.ignored_directories if fnmatch(parts[depth - 1], name)),
                    None,
                )
                if ignored is not None:
                    return f"inside '{prefix}', a directory every scan skips"
            for exclude in self.excludes or ():
                if fnmatch(prefix, exclude.pattern):
                    return f"excluded by '{exclude.pattern}' from {_SOURCE_NAMES[exclude.source]}"
        return None


@runtime_checkable
class ReportsFileScope(Protocol):
    """A file target that can say which excludes it applied, beside what it listed.

    Optional. The runner lists any other `FileReader` itself and records its excludes
    as unknown.
    """

    def file_scope(self) -> FileScope:
        """Return every file listed and the excludes applied while listing them."""
        raise NotImplementedError


_SOURCE_NAMES = {
    ExcludeSource.PROFILE: "the profile's rules.paths_exclude",
    ExcludeSource.IGNORE_FILE: ".guardanaignore",
}
