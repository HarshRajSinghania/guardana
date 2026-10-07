"""The member list of a tar, and the member a link in it reads as, without extracting.

`tarfile` resolves a link by loading every remaining header, which moves the read
position past the members a caller has not reached yet; so the headers are all read
first, and a link is resolved here against that list.
"""

import bisect
import posixpath
import tarfile
from dataclasses import dataclass, field

TAR_MAX_HEADERS = 1_000_000
"""Headers read from one tar; each costs a 512-byte block, and a checkpoint holds a few."""
_MAX_LINK_HOPS = 32
_END_OF_ARCHIVE_BYTES = 2 * tarfile.BLOCKSIZE
_NOT_FILE_DATA = frozenset({tarfile.DIRTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE})


class TarListingError(Exception):
    """Raised when a tar holds more headers than `TAR_MAX_HEADERS`, or a damaged one."""


def _normalised(name: str) -> str:
    return posixpath.normpath(name)


def _require_end_of_archive(archive: tarfile.TarFile) -> None:
    """Raise `TarListingError` unless the listing stopped at the end of the archive.

    `tarfile` stops listing at a header it cannot parse without raising, while `tar`
    warns and extracts the members after it; so the listing is whole only where the
    file ends or the zero blocks that close an archive begin. A tar cut at a member
    boundary has no member left unlisted, so it is whole.
    """
    handle = archive.fileobj
    if handle is None:
        raise TarListingError("tar could not be read past its headers")
    handle.seek(archive.offset)
    tail = handle.read(_END_OF_ARCHIVE_BYTES)
    if tail.strip(b"\x00"):
        raise TarListingError(f"tar has a damaged header at byte {archive.offset}")


@dataclass(slots=True)
class TarListing:
    """Every header of one tar, in order, with the positions each name occurs at."""

    members: list[tarfile.TarInfo] = field(default_factory=list)
    _positions: dict[str, list[int]] = field(default_factory=dict)

    @classmethod
    def read(cls, archive: tarfile.TarFile) -> "TarListing":
        """Read every header of `archive`, reading no member's data.

        Raises `TarListingError` past `TAR_MAX_HEADERS` or at a damaged header, and
        whatever `tarfile` raises for a malformed first header.
        """
        listing = cls()
        while (entry := archive.next()) is not None:
            if len(listing.members) >= TAR_MAX_HEADERS:
                raise TarListingError(f"tar holds more than {TAR_MAX_HEADERS} headers")
            listing._positions.setdefault(_normalised(entry.name), []).append(len(listing.members))
            listing.members.append(entry)
        _require_end_of_archive(archive)
        return listing

    def resolve(self, index: int) -> tarfile.TarInfo | None:
        """Return the member whose bytes `members[index]` reads as, following links.

        A hard link names a member before it and a symbolic link one relative to its own
        directory, the last of that name, as `tarfile` resolves them. None when a link
        names no member, or the chain is longer than any loader would follow.
        """
        position = index
        for _ in range(_MAX_LINK_HOPS):
            entry = self.members[position]
            if not (entry.islnk() or entry.issym()):
                return entry
            if entry.islnk():
                wanted, before = _normalised(entry.linkname), position
            else:
                joined = "/".join(filter(None, (posixpath.dirname(entry.name), entry.linkname)))
                wanted, before = _normalised(joined), len(self.members)
            positions = self._positions.get(wanted, [])
            earlier = bisect.bisect_left(positions, before)
            if earlier == 0:
                return None
            position = positions[earlier - 1]
        return None


def holds_file_data(entry: tarfile.TarInfo) -> bool:
    """Whether a loader opening `entry` reads bytes from the archive.

    A type `tarfile` does not know is read as a regular file, as `extractfile` reads it.
    """
    return entry.type not in _NOT_FILE_DATA
