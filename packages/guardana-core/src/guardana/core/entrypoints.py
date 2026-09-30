"""Every Guardana entry point installed on this system, listed without importing any of them.

One enumeration, walked by every consumer that decides trust: `Registry.discover`,
the pack commands and anything that reports what an installed pack would execute.
A second walk would be a second answer to "what is installed", and the day the two
disagree is the day an entry point listed as refused is imported anyway.

Reading `importlib.metadata` imports nothing; only `InstalledEntryPoint.load` does.
"""

from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points

TAXONOMY_GROUP = "guardana.taxonomies"
RULE_GROUP = "guardana.rules"
EVALUATOR_GROUP = "guardana.evaluators"
TARGET_GROUP = "guardana.targets"

GROUPS = (TAXONOMY_GROUP, RULE_GROUP, EVALUATOR_GROUP, TARGET_GROUP)
"""The four entry-point groups, in the order discovery loads them.

Taxonomies first: a rule can only name a framework that is already registered.
"""


@dataclass(frozen=True, slots=True)
class InstalledEntryPoint:
    """One advertised entry point, and the distribution that advertised it."""

    group: str
    name: str
    value: str
    """The `module:attr` reference as written in the distribution's metadata."""

    module: str
    """The module `load()` imports: the part of `value` before the colon."""

    distribution: str | None
    """The distribution's name as spelled in its metadata; None when it cannot say.

    An entry point with no distribution is treated as third-party by every trust
    mode that is not `all`, so this is never guessed from the module name.
    """

    version: str | None
    entry_point: EntryPoint = field(compare=False, repr=False)
    """The `importlib.metadata` handle `load()` goes through."""

    def load(self) -> object:
        """Import the module and return the object this entry point names."""
        return self.entry_point.load()


def installed_entry_points() -> tuple[InstalledEntryPoint, ...]:
    """List every entry point of the four Guardana groups, in load order, importing none."""
    return tuple(
        _record(group, entry_point) for group in GROUPS for entry_point in entry_points(group=group)
    )


def _record(group: str, entry_point: EntryPoint) -> InstalledEntryPoint:
    dist = entry_point.dist
    name = getattr(dist, "name", None)
    version = getattr(dist, "version", None)
    return InstalledEntryPoint(
        group=group,
        name=entry_point.name,
        value=entry_point.value,
        module=entry_point.value.split(":", 1)[0].strip(),
        distribution=str(name) if name else None,
        version=str(version) if version else None,
        entry_point=entry_point,
    )
