"""A distribution installed from a directory or a URL is pinned by its files, or says why not.

Each test installs a fake distribution into a directory of its own on `sys.path`: a
`dist-info` with the `direct_url.json` an editable or a directory install writes, and a
`RECORD`. The pins are then read through `importlib.metadata`, as `recipe lock` reads them.
"""

import importlib
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from guardana.core import recipe_source
from guardana.core.recipe import moves_under_one_version
from guardana.core.recipe_source import (
    SourcePin,
    installed_requirements,
    pin_distribution_source,
    record_pin,
    requirement_closure,
    tree_pin,
)

_EMPTY = "sha256=47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A directory on `sys.path` that fake distributions are installed into."""
    packages = tmp_path / "site-packages"
    packages.mkdir()
    monkeypatch.syspath_prepend(str(packages))
    importlib.invalidate_caches()
    yield packages
    importlib.invalidate_caches()


def _install(
    site: Path,
    name: str,
    *,
    direct_url: Mapping[str, object] | None = None,
    record: str | None = "",
    requires: tuple[str, ...] = (),
) -> Path:
    info = site / f"{name.replace('-', '_')}-1.0.dist-info"
    info.mkdir()
    metadata = [f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n"]
    metadata.extend(f"Requires-Dist: {requirement}\n" for requirement in requires)
    (info / "METADATA").write_text("".join(metadata), encoding="utf-8")
    if direct_url is not None:
        (info / "direct_url.json").write_text(json.dumps(direct_url), encoding="utf-8")
    if record is not None:
        (info / "RECORD").write_text(record, encoding="utf-8")
    importlib.invalidate_caches()
    return info


def _source_tree(root: Path) -> Path:
    """A project directory with code, package data, and everything a pin leaves out."""
    files = {
        "pyproject.toml": "[project]\nname = 'acme-pack'\n",
        "src/acme_pack/__init__.py": "CHECK = 'refuses'\n",
        "src/acme_pack/rules/refuses.yaml": "id: acme.refuses\n",
        "src/acme_pack/build/__init__.py": "NESTED = True\n",
        "src/acme_pack/__pycache__/__init__.cpython-313.pyc": "bytecode",
        "src/acme_pack/stale.pyc": "bytecode",
        "src/acme_pack.egg-info/PKG-INFO": "Name: acme-pack\n",
        ".git/HEAD": "ref: refs/heads/main\n",
        ".venv/lib/site.py": "venv\n",
        "venv/lib/site.py": "venv\n",
        "build/lib/acme_pack/__init__.py": "old build\n",
        "dist/acme_pack-1.0.tar.gz": "archive",
        "node_modules/x/index.js": "x\n",
        ".mypy_cache/x.json": "{}",
        ".ruff_cache/x": "x",
        ".pytest_cache/x": "x",
        ".tox/x": "x",
        ".nox/x": "x",
        ".DS_Store": "finder",
        "src/acme_pack/.DS_Store": "finder",
        ".idea/workspace.xml": "<project/>",
        ".vscode/settings.json": "{}",
        ".coverage": "coverage",
        ".coverage.host.1.x": "coverage",
        "htmlcov/index.html": "<html/>",
        ".env": "TOKEN=local\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _editable(site: Path, root: Path) -> None:
    _install(
        site,
        "acme-pack",
        direct_url={"url": root.as_uri(), "dir_info": {"editable": True}},
        record="acme_pack-1.0.dist-info/RECORD,,\n",
    )


def test_an_editable_install_is_pinned_by_its_source_files_and_nothing_else(
    tmp_path: Path, site: Path
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    _editable(site, root)

    pinned = pin_distribution_source("acme-pack")

    assert pinned == SourcePin(
        digest="sha256:d88dbd444d175cf6d68fe1d26a432cf639315c153c419647b682377123dace4e", files=5
    )


def test_the_digest_holds_until_a_pinned_file_changes(tmp_path: Path, site: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    _editable(site, root)
    first = pin_distribution_source("acme-pack")

    for excluded in (
        "src/acme_pack/__pycache__/__init__.cpython-313.pyc",
        "src/acme_pack.egg-info/PKG-INFO",
        ".git/HEAD",
        "build/lib/acme_pack/__init__.py",
        "dist/acme_pack-1.0.tar.gz",
        "node_modules/x/index.js",
        "venv/lib/site.py",
        ".DS_Store",
        "src/acme_pack/.DS_Store",
        ".idea/workspace.xml",
        ".vscode/settings.json",
        ".coverage",
        ".coverage.host.1.x",
        "htmlcov/index.html",
        ".env",
    ):
        (root / excluded).write_text("edited", encoding="utf-8")
    unchanged = pin_distribution_source("acme-pack")
    (root / "src/acme_pack/build/__init__.py").write_text("NESTED = False\n", encoding="utf-8")
    edited = pin_distribution_source("acme-pack")
    (root / "src/acme_pack/extra.py").write_text("", encoding="utf-8")
    added = pin_distribution_source("acme-pack")

    assert isinstance(first, SourcePin)
    assert unchanged == first
    assert isinstance(edited, SourcePin)
    assert edited.digest != first.digest
    assert edited.files == first.files
    assert isinstance(added, SourcePin)
    assert added.files == first.files + 1


def test_a_renamed_file_moves_the_digest(tmp_path: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    first = tree_pin(root)
    (root / "src/acme_pack/rules/refuses.yaml").rename(root / "src/acme_pack/rules/other.yaml")

    moved = tree_pin(root)

    assert isinstance(first, SourcePin)
    assert isinstance(moved, SourcePin)
    assert moved.digest != first.digest


def test_a_tree_above_the_bounds_stays_unpinned_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _source_tree(tmp_path / "acme-pack")

    monkeypatch.setattr(recipe_source, "MAX_SOURCE_FILES", 3)
    too_many = tree_pin(root)
    monkeypatch.setattr(recipe_source, "MAX_SOURCE_FILES", 20_000)
    monkeypatch.setattr(recipe_source, "MAX_SOURCE_BYTES", 16)
    too_large = tree_pin(root)

    assert too_many == "it holds more than 3 files"
    assert isinstance(too_large, str)
    assert too_large.startswith("it holds more than")


def test_a_symlink_leading_outside_the_directory_leaves_it_unpinned(tmp_path: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "helper.py").write_text("secret = 1\n", encoding="utf-8")

    (root / "src/acme_pack/helper.py").symlink_to(outside / "helper.py")
    linked_file = tree_pin(root)
    (root / "src/acme_pack/helper.py").unlink()
    (root / "src/acme_pack/vendored").symlink_to(outside, target_is_directory=True)
    linked_directory = tree_pin(root)

    assert linked_file == "a symlink leads outside its directory"
    assert linked_directory == "a symlink leads outside its directory"


def test_a_symlink_inside_the_directory_is_pinned_by_what_it_holds(tmp_path: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    (root / "src/acme_pack/alias.py").symlink_to(root / "src/acme_pack/__init__.py")
    (root / "src/acme_pack/loop").symlink_to(root / "src", target_is_directory=True)
    first = tree_pin(root)

    (root / "src/acme_pack/__init__.py").write_text("CHECK = 'complies'\n", encoding="utf-8")
    edited = tree_pin(root)

    assert isinstance(first, SourcePin)
    assert first.files == 6
    assert isinstance(edited, SourcePin)
    assert edited.digest != first.digest


def _record(*rows: str) -> str:
    return "".join(f"{row}\n" for row in rows)


_RECORD = _record(
    "acme_pack/__init__.py,sha256=AAAA,18",
    "acme_pack/rules/refuses.yaml,sha256=BBBB,17",
    "acme_pack/__pycache__/__init__.cpython-313.pyc,,",
    f"acme_pack-1.0.dist-info/INSTALLER,{_EMPTY},0",
    f"acme_pack-1.0.dist-info/direct_url.json,{_EMPTY},0",
    f"acme_pack-1.0.dist-info/METADATA,{_EMPTY},0",
    "acme_pack-1.0.dist-info/RECORD,,",
)


def test_a_directory_install_is_pinned_by_its_record(site: Path) -> None:
    _install(
        site,
        "acme-pack",
        direct_url={"url": "file:///src/acme-pack", "dir_info": {}},
        record=_RECORD,
    )

    pinned = pin_distribution_source("acme-pack")

    assert pinned == SourcePin(
        digest="sha256:c28dbf3f3540166a5102cb043e8006dddb2d3839bffc2e82cdd788ca9312b7f2", files=3
    )


def test_installer_bookkeeping_leaves_the_record_pin_where_the_code_leaves_it() -> None:
    def installed(*, cache: str, module: str = "AAAA", entry_points: str = "FFFF") -> str:
        return _record(
            f"acme_pack/__init__.py,sha256={module},18",
            f"acme_pack-1.0.dist-info/METADATA,{_EMPTY},0",
            f"acme_pack-1.0.dist-info/entry_points.txt,sha256={entry_points},40",
            f"acme_pack-1.0.dist-info/uv_cache.json,sha256={cache},194",
            f"acme_pack-1.0.dist-info/REQUESTED,{_EMPTY},0",
            f"acme_pack-1.0.dist-info/WHEEL,sha256={cache},87",
            f"acme_pack-1.0.dist-info/licenses/LICENSE,sha256={cache},11",
            "acme_pack-1.0.dist-info/RECORD,,",
        )

    first = record_pin(installed(cache="1111"))
    reinstalled = record_pin(installed(cache="2222"))
    edited = record_pin(installed(cache="1111", module="CCCC"))
    reregistered = record_pin(installed(cache="1111", entry_points="EEEE"))

    assert isinstance(first, SourcePin)
    assert first.files == 3
    assert reinstalled == first
    assert isinstance(edited, SourcePin)
    assert edited.digest != first.digest
    assert isinstance(reregistered, SourcePin)
    assert reregistered.digest != first.digest


def test_a_record_pin_moves_with_a_recorded_hash_and_ignores_the_install_record() -> None:
    first = record_pin(_RECORD)

    rehashed = record_pin(_RECORD.replace("sha256=AAAA", "sha256=CCCC"))
    reinstalled = record_pin(
        _RECORD.replace(f"INSTALLER,{_EMPTY}", "INSTALLER,sha256=DDDD").replace(
            f"direct_url.json,{_EMPTY}", "direct_url.json,sha256=EEEE"
        )
    )

    assert isinstance(first, SourcePin)
    assert isinstance(rehashed, SourcePin)
    assert rehashed.digest != first.digest
    assert reinstalled == first


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (None, "it has no RECORD to read"),
        (_RECORD + "acme_pack/data.bin,,\n", "its RECORD lists acme_pack/data.bin without a hash"),
    ],
)
def test_a_record_that_cannot_vouch_for_a_file_leaves_it_unpinned(
    record: str | None, reason: str
) -> None:
    assert record_pin(record) == reason


def test_a_record_above_the_bounds_stays_unpinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recipe_source, "MAX_SOURCE_FILES", 2)
    assert record_pin(_RECORD) == "it holds more than 2 files"


def test_a_vcs_or_archive_install_without_a_record_stays_unpinned(site: Path) -> None:
    _install(
        site,
        "acme-pack",
        direct_url={"url": "https://example.test/acme.zip", "archive_info": {}},
        record=None,
    )

    assert pin_distribution_source("acme-pack") == "it has no RECORD to read"


def test_an_editable_install_naming_no_directory_stays_unpinned(site: Path, tmp_path: Path) -> None:
    _install(
        site,
        "acme-pack",
        direct_url={"url": (tmp_path / "gone").as_uri(), "dir_info": {"editable": True}},
    )

    assert pin_distribution_source("acme-pack") == (
        "the directory its editable install names does not exist"
    )


def test_only_a_direct_url_install_moves_under_one_version(site: Path) -> None:
    _install(site, "acme-pack", direct_url={"url": "file:///src", "dir_info": {}})
    _install(site, "acme-index", record=_RECORD)

    assert moves_under_one_version("acme-pack") is True
    assert moves_under_one_version("acme-index") is False
    assert moves_under_one_version("acme-absent") is False


def test_a_legacy_checkout_on_the_path_moves_and_stays_unpinned_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`setup.py develop` and an `.egg-info` checkout write no `direct_url.json`."""
    checkout = tmp_path / "acme-legacy"
    info = checkout / "acme_legacy.egg-info"
    info.mkdir(parents=True)
    (info / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: acme-legacy\nVersion: 1.0\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(checkout))
    importlib.invalidate_caches()

    assert moves_under_one_version("acme-legacy") is True
    assert pin_distribution_source("acme-legacy") == "it names no direct URL to pin by its files"


def test_an_installed_distribution_without_a_record_moves_under_one_version(site: Path) -> None:
    _install(site, "acme-unrecorded", record=None)

    assert moves_under_one_version("acme-unrecorded") is True
    assert pin_distribution_source("acme-unrecorded") == (
        "it names no direct URL to pin by its files"
    )


def test_requirements_are_followed_by_their_normalised_name_markers_and_extras_ignored(
    site: Path,
) -> None:
    _install(
        site,
        "acme-pack",
        requires=(
            "Acme_Helpers[fast] (>=1.0) ; python_version < '3'",
            "acme.base>=2",
            "acme-absent",
        ),
    )
    _install(site, "acme-helpers", requires=("acme-pack",))
    _install(site, "acme-base")

    found = installed_requirements("acme-pack")
    closure = requirement_closure(["Acme_Pack"], installed_requirements)

    assert found == ("acme-base", "acme-helpers")
    assert closure == frozenset({"acme-pack", "acme-helpers", "acme-base"})
    assert installed_requirements("acme-absent") == ()


def test_bytecode_outside_a_cache_directory_is_pinned(tmp_path: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    first = tree_pin(root)

    (root / "src/acme_pack/stale.pyc").write_text("other bytecode", encoding="utf-8")
    edited = tree_pin(root)

    assert isinstance(first, SourcePin)
    assert isinstance(edited, SourcePin)
    assert edited.digest != first.digest


def test_what_a_recipe_run_writes_inside_the_editable_directory_is_left_out(
    tmp_path: Path, site: Path
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    _editable(site, root)
    lock = root / "checks" / "guardana-recipe.lock.yaml"
    output = root / "checks" / "guardana-artifact"
    first = pin_distribution_source("acme-pack", leave_out=(lock, output))

    lock.parent.mkdir()
    lock.write_text("schema_version: 2\n", encoding="utf-8")
    output.mkdir()
    (output / "run.json").write_text("{}", encoding="utf-8")
    held = pin_distribution_source("acme-pack", leave_out=(lock, output))
    counted = pin_distribution_source("acme-pack")

    assert held == first
    assert isinstance(first, SourcePin)
    assert isinstance(counted, SourcePin)
    assert counted.files == first.files + 2


_OUTSIDE = {
    "../bin/acme": "#!/venv-one/bin/python\nfrom acme_pack import main\nmain()\n",
    "../bin/acme-tool": "#!/venv-one/bin/python\nprint('tool')\n",
    "../share/acme/table.txt": "rows\n",
    "acme_pack-1.0.data/scripts/acme-setup": "#!python\nprint('setup')\n",
}


def _with_installed_files(site: Path, files: Mapping[str, str]) -> None:
    """Install `acme-pack` from a directory, with `files` written where its RECORD says."""
    for path, text in files.items():
        (site / path).parent.mkdir(parents=True, exist_ok=True)
        (site / path).write_text(text, encoding="utf-8")
    info = _install(
        site,
        "acme-pack",
        direct_url={"url": "file:///src/acme-pack", "dir_info": {}},
        record=_RECORD
        + _record(
            "acme_pack-1.0.dist-info/entry_points.txt,sha256=FFFF,40",
            *(f"{path},sha256=ZZZZ,1" for path in _OUTSIDE),
        ),
    )
    (info / "entry_points.txt").write_text(
        "[console_scripts]\nacme = acme_pack:main\n", encoding="utf-8"
    )


_ENV_ONE = "/venv-one/bin/python3"
_ENV_TWO = "/venv two/bin/python3"
_TRAMPOLINE = "#!/bin/sh\n'''exec' {exe} \"$0\" \"$@\"\n' '''\n"


@pytest.mark.parametrize(
    ("path", "text", "pinned_in", "moves"),
    [
        (
            "../bin/acme-tool",
            "#!/venv-two/bin/python\nprint('tool')\n",
            "/venv-two/bin/python3",
            False,
        ),
        (
            "../bin/acme-tool",
            _TRAMPOLINE.format(exe="'/venv two/bin/python'") + "print('tool')\n",
            _ENV_TWO,
            False,
        ),
        ("../bin/acme-tool", "#!/venv-one/bin/python\nprint('other')\n", _ENV_ONE, True),
        ("../bin/acme-tool", "#!/venv-one/bin/python -E\nprint('tool')\n", _ENV_ONE, True),
        (
            "../bin/acme-tool",
            "#!/usr/bin/env -S python3 -c \"import os; os.system('id')\"\nprint('tool')\n",
            _ENV_ONE,
            True,
        ),
        ("../bin/acme-tool", "#!/venv-two/bin/python\nprint('tool')\n", _ENV_ONE, True),
        (
            "../bin/acme-tool",
            _TRAMPOLINE.format(exe="'/elsewhere/bin/python'") + "print('tool')\n",
            _ENV_ONE,
            True,
        ),
        ("../share/acme/table.txt", "other rows\n", _ENV_ONE, True),
        ("acme_pack-1.0.data/scripts/acme-setup", "#!python\nprint('other')\n", _ENV_ONE, True),
        (
            "../bin/acme",
            "#!/venv-two/bin/python\nfrom elsewhere import main\nmain()\n",
            _ENV_ONE,
            False,
        ),
    ],
    ids=[
        "another-environment",
        "trampoline-in-another-environment",
        "script",
        "interpreter-arguments",
        "foreign-first-line",
        "interpreter-of-another-environment",
        "trampoline-to-another-interpreter",
        "data",
        "data-scripts",
        "generated",
    ],
)
def test_files_installed_outside_the_package_are_pinned_by_content_but_the_interpreter_path(  # noqa: PLR0913 — the fixtures and one case
    site: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    text: str,
    pinned_in: str,
    *,
    moves: bool,
) -> None:
    """Only the path an installer writes for this environment's interpreter is left out.

    A console script is what `entry_points.txt` declares, and that file is pinned.
    """
    monkeypatch.setattr(sys, "executable", _ENV_ONE)
    _with_installed_files(site, _OUTSIDE)
    first = pin_distribution_source("acme-pack")

    (site / path).write_text(text, encoding="utf-8")
    monkeypatch.setattr(sys, "executable", pinned_in)
    second = pin_distribution_source("acme-pack")

    assert isinstance(first, SourcePin)
    assert first.files == 7
    assert (second != first) is moves


def test_a_file_installed_outside_the_package_that_cannot_be_read_leaves_it_unpinned(
    site: Path,
) -> None:
    _with_installed_files(site, _OUTSIDE)
    (site / "../share/acme/table.txt").unlink()

    assert pin_distribution_source("acme-pack") == "its ../share/acme/table.txt cannot be read"


def test_bytecode_a_record_lists_outside_a_cache_directory_is_pinned() -> None:
    shipped = _RECORD + "acme_pack/compiled.pyc,sha256=GGGG,90\n"

    first = record_pin(shipped)
    rebuilt = record_pin(shipped.replace("sha256=GGGG", "sha256=HHHH"))

    assert isinstance(first, SourcePin)
    assert first.files == 4
    assert isinstance(rebuilt, SourcePin)
    assert rebuilt.digest != first.digest


def _editable_with(site: Path, root: Path, files: Mapping[str, str]) -> None:
    """Install `acme-pack` editable from `root`, with `files` beside it in site-packages."""
    for name, text in files.items():
        (site / name).write_text(text, encoding="utf-8")
    listed = "".join(f"{name},sha256=AAAA,1\n" for name in files)
    _install(
        site,
        "acme-pack",
        direct_url={"url": root.as_uri(), "dir_info": {"editable": True}},
        record=f"{listed}acme_pack-1.0.dist-info/RECORD,,\n",
    )


def _finder(mapping: Mapping[str, str], namespaces: Mapping[str, list[str]]) -> str:
    return (
        "import sys\n"
        f"MAPPING: dict[str, str] = {dict(mapping)!r}\n"
        f"NAMESPACES: dict[str, list[str]] = {dict(namespaces)!r}\n"
        "def install():\n    pass\n"
    )


_FINDER = "__editable___acme_pack_1_0_finder"


def test_an_editable_path_file_inside_its_directory_is_pinned(tmp_path: Path, site: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    finder = _finder({"acme_pack": str(root / "src" / "acme_pack")}, {})
    _editable_with(
        site,
        root,
        {
            "_acme_pack.pth": (
                f"# comment\n\n{root / 'src'}\nimport {_FINDER}; {_FINDER}.install()\n"
            ),
            f"{_FINDER}.py": finder,
        },
    )

    assert isinstance(pin_distribution_source("acme-pack"), SourcePin)


@pytest.mark.parametrize(
    ("line", "hook"),
    [
        ("import _editable_impl_acme_pack", "_editable_impl_acme_pack"),
        (f"import {_FINDER}, acme_hook; {_FINDER}.install()", "acme_hook"),
        (f"import {_FINDER} as alias; alias.install()", _FINDER),
        (f"import {_FINDER}; {_FINDER}.install(); exec('x')", "a statement beside its finder"),
        (f"import {_FINDER}; {_FINDER}.install(", "a line that is not Python"),
    ],
    ids=["other-hook", "finder-and-hook", "renamed-finder", "extra-statement", "not-python"],
)
def test_an_editable_path_file_running_a_hook_that_is_not_a_read_finder_leaves_it_unpinned(
    tmp_path: Path, site: Path, line: str, hook: str
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    finder = _finder({"acme_pack": str(root / "src" / "acme_pack")}, {})
    _editable_with(
        site,
        root,
        {"_acme_pack.pth": f"{root / 'src'}\n{line}\n", f"{_FINDER}.py": finder},
    )

    assert pin_distribution_source("acme-pack") == (
        f"its _acme_pack.pth runs {hook}, which Guardana cannot read"
    )


def test_an_editable_path_file_importing_a_finder_its_record_does_not_list_leaves_it_unpinned(
    tmp_path: Path, site: Path
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    _editable_with(site, root, {"_acme_pack.pth": f"import {_FINDER}; {_FINDER}.install()\n"})

    assert pin_distribution_source("acme-pack") == (
        f"its _acme_pack.pth runs {_FINDER}, which Guardana cannot read"
    )


def test_an_editable_path_file_reaching_outside_its_directory_leaves_it_unpinned(
    tmp_path: Path, site: Path
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    _editable_with(site, root, {"_acme_pack.pth": f"{root / 'src'}\n{outside}\n"})

    assert pin_distribution_source("acme-pack") == (
        f"its _acme_pack.pth loads code from {outside}, outside the directory it was installed from"
    )


@pytest.mark.parametrize("field", ["mapping", "namespaces"])
def test_an_editable_finder_mapping_outside_its_directory_leaves_it_unpinned(
    tmp_path: Path, site: Path, field: str
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    outside = tmp_path / "elsewhere"
    inside = {"acme_pack": str(root / "src" / "acme_pack")}
    finder = (
        _finder({**inside, "acme_helpers": str(outside)}, {})
        if field == "mapping"
        else _finder(inside, {"acme_ns": [str(root / "src"), str(outside)]})
    )
    name = "__editable___acme_pack_1_0_finder.py"
    _editable_with(site, root, {name: finder})

    assert pin_distribution_source("acme-pack") == (
        f"its {name} loads code from {outside}, outside the directory it was installed from"
    )


def test_an_editable_finder_mapping_inside_its_directory_is_pinned(
    tmp_path: Path, site: Path
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    finder = _finder(
        {"acme_pack": str(root / "src" / "acme_pack")}, {"acme_ns": [str(root / "src")]}
    )
    _editable_with(site, root, {"__editable___acme_pack_1_0_finder.py": finder})

    assert isinstance(pin_distribution_source("acme-pack"), SourcePin)


@pytest.mark.parametrize(
    "finder",
    ["MAPPING = {'acme_pack': SRC}\n", "def broken(:\n", "MAPPING = ['not', 'a', 'mapping']\n"],
    ids=["not-a-literal", "not-python", "not-a-mapping"],
)
def test_an_editable_finder_that_cannot_be_read_leaves_it_unpinned(
    tmp_path: Path, site: Path, finder: str
) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    name = "__editable___acme_pack_1_0_finder.py"
    _editable_with(site, root, {name: finder})

    assert pin_distribution_source("acme-pack") == (
        f"its {name} maps its packages in a way Guardana cannot read"
    )


def test_an_editable_install_without_a_record_stays_unpinned(tmp_path: Path, site: Path) -> None:
    root = _source_tree(tmp_path / "acme-pack")
    _install(
        site,
        "acme-pack",
        direct_url={"url": root.as_uri(), "dir_info": {"editable": True}},
        record=None,
    )

    assert pin_distribution_source("acme-pack") == "it has no RECORD to read"
