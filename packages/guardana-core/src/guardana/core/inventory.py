"""Build the component inventory for one target — independent of which rules ran.

Independence is the point. If the inventory came from the rules, then excluding a
rule would quietly shrink the list of components, and a narrowed profile would
under-report what is actually deployed. So this walks the target itself, reuses
the listing the scan already has, and asks nothing of the registry.

It stays shallow on purpose: a name, a location, a format, a size. Anything
deeper (a model's architecture, a manifest's resolved versions) costs reads that
a scan should not pay for twice, and belongs to whoever needs the depth.
"""

from collections.abc import Iterable, Iterator
from pathlib import Path

from guardana.core.observation import Observation, ObservationKind
from guardana.core.target import Target
from guardana.core.target.protocols import ChatEndpoint, FileReader

_MODEL_SUFFIXES: dict[str, str] = {
    ".gguf": "gguf",
    ".safetensors": "safetensors",
    ".onnx": "onnx",
    ".pt": "pytorch",
    ".pth": "pytorch",
    ".ckpt": "pytorch",
    ".h5": "keras-hdf5",
    ".hdf5": "keras-hdf5",
    ".keras": "keras",
    ".pkl": "pickle",
    ".pickle": "pickle",
    ".dill": "pickle",
    ".joblib": "joblib",
    ".pmml": "pmml",
    ".tflite": "tflite",
}
_MANIFEST_NAMES = frozenset(
    {
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "uv.lock",
        "pipfile",
        "pipfile.lock",
        "environment.yml",
        "conda.yaml",
    }
)
_BIN_SUFFIX = ".bin"
_BIN_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "pytorch"),
    (b"\x80\x02", "pickle"),
    (b"\x80\x03", "pickle"),
    (b"\x80\x04", "pickle"),
    (b"\x80\x05", "pickle"),
    (b"GGUF", "gguf"),
    (b"lmgg", "ggml"),
    (b"fmgg", "ggml"),
    (b"tjgg", "ggml"),
)
"""What a `.bin` holds when it is a model, by its first bytes.

`.bin` names model weights, firmware and test data alike, so it is a component only
when its first bytes say which model container it is; one that says nothing is not
listed."""
_DATASET_SUFFIXES = frozenset({".parquet", ".jsonl", ".arrow"})
_MANIFEST_PREFIX = "requirements"


def _size_attributes(path: Path) -> dict[str, str]:
    # Opened, not just `stat`ed. `stat()` needs only traverse permission on the
    # parent, so it happily reports a size for a file whose contents nobody can
    # read — and the component would then sit in the report wearing that size,
    # looking examined, while every rule had silently skipped it. Listed anyway
    # when the open fails: an inventory that drops what it could not read lies by
    # omission, which is the same failure as a check reporting clean.
    if not _regular_file(path):
        # A FIFO or a device named like a model blocks a plain open for ever.
        return {"read": "failed"}
    try:
        with path.open("rb"):
            return {"size_bytes": str(path.stat().st_size)}
    except OSError:
        return {"read": "failed"}


def _regular_file(path: Path) -> bool:
    """Whether `path` is a regular file this process may open; False when it cannot tell.

    `is_file` raises for an entry inside a directory that can be listed and not entered.
    """
    try:
        return path.is_file()
    except OSError:
        return False


def _bin_format(path: Path) -> str | None:
    if not _regular_file(path):
        return None
    try:
        with path.open("rb") as handle:
            head = handle.read(4)
    except OSError:
        return None
    return next((name for magic, name in _BIN_SIGNATURES if head.startswith(magic)), None)


def _classify(path: Path) -> tuple[ObservationKind, dict[str, str]] | None:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in _MODEL_SUFFIXES:
        return ObservationKind.MODEL, {"format": _MODEL_SUFFIXES[suffix]}
    if suffix == _BIN_SUFFIX:
        bin_format = _bin_format(path)
        return None if bin_format is None else (ObservationKind.MODEL, {"format": bin_format})
    if name in _MANIFEST_NAMES or (name.startswith(_MANIFEST_PREFIX) and suffix == ".txt"):
        return ObservationKind.DEPENDENCY_MANIFEST, {}
    if suffix in _DATASET_SUFFIXES:
        return ObservationKind.DATASET, {"format": suffix.lstrip(".")}
    if suffix == ".ipynb":
        return ObservationKind.NOTEBOOK, {}
    return None


def _observe_artifacts(target: FileReader, files: Iterable[Path] | None) -> Iterator[Observation]:
    for path in target.iter_files() if files is None else files:
        classified = _classify(path)
        if classified is None:
            continue
        kind, attributes = classified
        yield Observation(
            kind=kind,
            name=path.name,
            ref=str(path),
            attributes={**attributes, **_size_attributes(path)},
        )


def observe(target: Target, files: Iterable[Path] | None = None) -> tuple[Observation, ...]:
    """Return every component this target exposes, in a stable order.

    `files` is the target's listing when the caller already took it, so a file target
    that does not cache its listing is walked once.

    Returns nothing for a target type it does not recognise, which is the honest
    answer: a custom `Target` knows its own components and can report them, but
    this must never invent an inventory for one it cannot see into.
    """
    if isinstance(target, FileReader):
        return tuple(_observe_artifacts(target, files))
    if isinstance(target, ChatEndpoint):
        return (Observation(kind=ObservationKind.MODEL, name=target.model, ref=target.ref),)
    return ()
