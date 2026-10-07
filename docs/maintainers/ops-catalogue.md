---
title: "Operations catalogue"
nav_order: 11
summary: "One row per script under scripts/: what it writes, its safe mode, what it needs. Exact flags come from each script's own --help or docstring."
status: stable
---

# Operations catalogue

One row per script under `scripts/`. This page answers "which script, is it safe,
what does it need"; exact flags come from the script's own `--help` or module
docstring, never from memory. `scripts/check_ops_catalogue.py` fails the gate
when a script has no row or a row has no script.

Columns: **Writes** = what a default run changes (`-` nothing · `repo` tracked
files · `local` untracked or temporary files · `docker` images and containers ·
`git` commits, tags, pushes). **Safe mode** = the flag that verifies without
writing (`-` = nothing to guard, `NONE` = no such flag, the script always does its
thing). **Net** = network it uses. **Needs** = tools or state it requires.

⚠ prefixes a purpose that pushes, tags, publishes, deletes a tree, or reaches
the network with no safe mode.

## Scripts — `scripts/`

### The gate

Run through `scripts/ci_local.sh --quiet`; the gates below are what it runs, every one of
them on every CI push as well.

| script | purpose | Writes | Safe mode | Net | Needs |
|---|---|---|---|---|---|
| `ci_local.sh` | mirror every CI job, one verdict line per gate; `--fast` reports the slow jobs as NOT RUN | `local` (`cache/ci/`, `.coverage*`, `sbom/`) | `-` | `uv audit`, `uv sync --locked` | docker for PostgreSQL and the images |
| `critical_coverage.py` | per-area coverage floors over a coverage JSON report | `-` | `-` | `-` | `.coverage.json` from pytest |
| `clean_install_check.py` | install the five distributions into an empty venv and run the documented commands | `local` (temp venv outside the repo) | `NONE` (`--help` only; `--keep` leaves the venv) | package resolution | ~40 s |
| `new_pack_check.py` | gate: scaffold a pack, install it isolated, and prove it validates, grades its samples and would notice a manifest that lies | `local` (a temp venv and tree outside the repo) | `--help` | package resolution | `uv`, ~15 s |
| `generate_sbom.py` | one CycloneDX SBOM per distribution, verified against its metadata | `local` (`sbom/`, gitignored) | `--check` (writes to a temp dir), `--help` | `uv export` | — |
| `image_smoke.py` | ⚠ build both container images and run them against the documented behaviour | `docker` | `NONE` (`--help` only; `--no-build` reuses images) | base-image pull | docker running |

### Documentation and the site

Every generated file has a `--check` mode, and `test_generated_truth_is_current`
runs three of them inside pytest.

| script | purpose | Writes | Safe mode | Net | Needs |
|---|---|---|---|---|---|
| `generate_docs.py` | `docs/generated/*` and the built-in pack manifest from the live registry | `repo` | `--check` | `-` | — |
| `sync_site.py` | rewrite the landing page's rule counts from the registry, and its diagrams from the docs' `mermaid` blocks | `repo` (`site/index.html`) | `--check` | `-` | — |
| `build_site.py` | ⚠ delete and rewrite `site/docs/` from `docs/**.md`, `site/notes/` from `notes/*.md` (empty without notes), and `site/schemas/` from `schemas/` | `repo` (`site/docs/`, `site/notes/`, `site/schemas/`) | `--check` | `-` | — |
| `generate_sitemap.py` | `site/sitemap.xml` and `site/robots.txt` from the pages actually built, in the URL form the host serves | `repo` (`site/sitemap.xml`, `site/robots.txt`) | `--check` | `-` | `site/` already built |
| `generate_llms_txt.py` | `site/llms.txt` from `docs/index.md`, `notes/*.md` and `schemas/` | `repo` | `--check` | `-` | — |
| `generate_well_known.py` | `site/favicon.ico` and the Apple touch icons rendered from `site/favicon.svg`, and `site/.well-known/security.txt` from `SECURITY.md` with a generated `Expires` | `repo` | `--check` | `-` | — |
| `api_surface.py` | `docs/generated/api-surface.json`: the supported surface read from source — facade, extension and output contracts, the kit, version constants, CLI flags, exit codes, locator schemes, action inputs, `GUARDANA_*` names; `generate_docs.py` writes it | `repo` | `--check` | `-` | — |
| `first_run_measure.py` | validate the first-run study sheet and print the measure it supports; `generate_docs.py` writes the same text to `docs/generated/first-run.md` | `-` | `-` | `-` | — |
| `adopter_measure.py` | validate the adopter-runs sheet and print the two measures it supports; `row RUN.json` prints one row of counts from a locked application run; `generate_docs.py` writes the measures to `docs/generated/application-measures.md` | `-` | `-` | `-` | — |
| `og_card.html` | the source of `site/og.png`, rendered by hand (`site/README.md`) | `-` | `-` | `-` | a browser |

### Release

`RELEASING.md` is the runbook; the `release` skill is the order that has gone
wrong before.

| script | purpose | Writes | Safe mode | Net | Needs |
|---|---|---|---|---|---|
| `bump_version.py` | set all five versions, every inter-package pin, the Action and image pins, then `uv lock` | `repo` | `--dry-run` | `uv lock` | — |
| `capture_historical_documents.py` | ⚠ install every published release in isolation and keep the documents each one wrote from synthetic inputs, and the profile examples in its own `docs/` that it loaded, with `releases.json` recording each example as loaded, refused, or not tried when it names a file the capture does not provide, under `packages/guardana-core/tests/historical/`; run after a release that changes a document; `--profiles-only` redoes only the profiles of the releases already recorded | `repo` | `--dry-run`, `--help` | PyPI | `uv`, release tags in the clone |
| `release.py` | ⚠ refuses a candidate whose supported surface moved without a changelog section, a final whose surface differs from its candidate, and a final 1.x while `RELEASING.md` says pre-1.0 → gate → bump → changelog roll → commit only the paths it wrote → push `main` without tags → wait for green CI → create and push the tag (PyPI publish) → move the marketplace tag | `git` + `repo` | `--dry-run`, `--help` | `git`, `gh`, PyPI via CI | `gh` authenticated, push rights |

### Security

`docs/maintainers/security-runbook.md` is the runbook; `docs/maintainers/drills.md` records drills.

| script | purpose | Writes | Safe mode | Net | Needs |
|---|---|---|---|---|---|
| `check_repo_settings.py` | read the repository settings the security runbook relies on and print each PRESENT, ABSENT or NOT CHECKED; exit `0`, `1` or `2`. Reading a setting is not a drill | `-` | `-` | GitHub API (read-only) | `gh` authenticated |
| `distribution_signals.py` | read what PyPI (pypistats.org), GitHub (stars, 14-day traffic, release downloads, public uses of the Action) and ghcr publish about the project and print each number, "not measured" or "absent"; exit `0` or `2`. Reach signals, not users; nothing in Guardana itself reports anything | `--record`: appends to `cache/distribution-signals.csv` (gitignored) | default (prints only) | pypistats.org, GitHub API and ghcr pages (read-only) | `gh` authenticated; push access for traffic |

### Agent tooling

Wired in `.claude/settings.json`; never invoked by hand except the checks.

| script | purpose | Writes | Safe mode | Net | Needs |
|---|---|---|---|---|---|
| `ruff_on_edit.py` | PostToolUse hook: `ruff check --fix` + `ruff format` on the file just written | `repo` (that one file) | `-` | `-` | — |
| `guard_hook.py` | PreToolUse hook: deny/ask for the commands a prompt cannot be trusted to hold | `-` | `-` | `-` | — |
| `session_start.sh` | SessionStart hook: work in flight, uncommitted paths, text engines | `-` | `-` | `-` | — |
| `check_claude_setup.py` | gate: frontmatter, rule globs, quoted paths, hook paths, the PreToolUse guard wired for every tool it decides on, nothing gitignored under `.claude/` but harness-local state, CLAUDE.md budget | `-` | `-` | `-` | — |
| `check_ops_catalogue.py` | gate: every script has one row here, every row has a script | `-` | `-` | `-` | — |
| `text_model.py` | the one door to GPT (`codex`) and Gemini (`agy`) for reader-facing wording and verdicts about it | `local` (the `--out` file) | `--detect` | GPT / Gemini | `codex` or `agy` installed |

## For decision

- `og_card.html` is rendered by hand and `site/og.png` is committed; nothing
  checks that the two still agree.
