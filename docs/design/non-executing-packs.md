---
title: "Non-executing packs and the default plugin trust"
nav_order: 85
summary: "whether a pack can ship checks that execute no Python, and which plugin trust a command starts with when the user says nothing"
status: accepted
---

# Non-executing declarative packs

**Status:** accepted, not yet implemented (built-in plugin trust by default shipped in 0.33.0) · **Written:** 2026-09-30 · **Decided:** 2026-09-30 by the
maintainer · **Serves:** ROADMAP F2, backlog B12 · **Follows:** [the direction audit](audit-0.31-direction.md)

## Decision

- **Decision 1: B, data-only distributions.** Designed and built in the parallel contributor lane
  after F2's starter; F2's custom check is a local YAML file.
- **Decision 2: the CLI starts with `builtins` from 0.33**, stated as breaking in the CHANGELOG,
  with a `plugins:` key in `guardana.yaml` so a team states its trust once.
- **Data-only content loads under `builtins` by default.** It executes nothing, so the default
  trust admits it; any Python provider stays behind `--plugins`.

The analysis below is what the decision was made from.

## The two questions

1. Can a pack ship checks that execute no Python, installed and locked like any other pack?
2. Which plugin trust does a command start with when the user says nothing?

The roadmap asks for this before F2 ships: the first-run starter runs with built-in trust only
and shows what an installed pack would execute, and today installing a pack means running its
author's code.

## What the code does today

- **Every pack is a Python distribution.** `Registry.discover` walks the four entry-point
  groups and calls `ep.load()()` for each provider (`core/registry.py:249-306`). The pack
  manifest is found through `importlib.resources.files(module)`, which imports the package
  (`core/pack/discover.py:179-205`). A pack's YAML catalogue is read by its own Python
  (`pack_templates/package_init.py.tmpl`), and so is the built-in one (`rules/__init__.py`).
- **Trust is decided before the import**, per distribution (`core/plugins.py:47-62`); a refused
  entry point is recorded as a `discovery` error, so a refused pack makes the run
  indeterminate rather than quietly smaller. The default mode was `all` for `scan`, `probe`
  and `plan` when this was written; since 0.33.0 it is `builtins` for every command
  (`cli/_plugins.py`), and a profile's `plugins:` key sets it.
- **Declarative rules already run without third-party code**: `--rules` and `rules.paths` read
  YAML from disk (`Registry.load_yaml_rule_dirs`), and `--plugins builtins` keeps the built-in
  evaluators. What is missing is packaging: such a directory has no version, no install path
  and no lock entry.
- **Nothing reads rule files out of an installed distribution without importing it.**
  `importlib.metadata` is used for entry points and versions only.
- `pack lock` pins each pack's distribution and version, its rules by `Rule.digest()`, its
  evaluators and targets by id (`core/pack/lock.py`).

## Decision 1: can a pack execute nothing?

| Option | What it is | Cost | What it leaves open |
|---|---|---|---|
| A. Keep directories | Declarative checks travel as directories passed to `--rules`; packs stay Python | none | no version, install, lock or discovery story for shared checks; teams copy directories |
| **B. Data-only distributions** | A wheel declares its YAML catalogue in a new entry-point group whose value is a path inside the distribution; Guardana reads it through `importlib.metadata` (`dist.files`, `locate_file`) and imports nothing. Rules may name built-in evaluators only | a fifth entry-point group and a pack manifest schema 3 (protected contracts), a loader, lock entries by digest, docs | a rule needing a third-party evaluator still needs that pack's Python |
| C. Pack archives | `guardana pack add PATH` copies a digested directory into a project store listed in the profile | a store, a profile key and versioning semantics Guardana would own; a download path would break offline-by-default | duplicates what pip, uv and private indexes already do for teams |

**Recommendation: B**, designed and built in the parallel lane after F2's starter, not
blocking F2. It keeps pip and uv as the channel teams already pin, mirror and audit, adds no
network path, and lets a pack say "this executes nothing" as a fact Guardana checks rather
than a promise. Trust follows from it: data-only content can be loaded under `builtins` while
any Python provider stays behind `--plugins`. F2 itself needs only A — its custom check is a
local YAML file.

## Decision 2: the default plugin trust

| Option | Effect | Risk |
|---|---|---|
| Keep `all` | every installed provider is imported on every run, as today | a first run imports code the user never chose to trust, which F2's promise contradicts |
| **Switch to `builtins` in 0.33, with F2** | a run imports only `guardana-core`, `guardana-rules` and `guardana-report`; `--plugins all` or an allowlist opts in | **breaking** for a team relying on an installed pack; loud, not silent: each refused entry point is a `discovery` error and the run is indeterminate under `fail_on_error`, with a message naming `--plugins all` |
| `builtins` for the starter only | the starter command passes `builtins`; every other command keeps `all` | two defaults to explain; the first real `scan` after the starter imports everything again |

**Recommendation: switch the default to `builtins` in 0.33**, stated as breaking in the
CHANGELOG, with a profile key (`plugins:`) so a team states its trust once instead of on every
command. Pre-1.0 is when a default like this can move; after 1.0 it cannot.

## What was open

The three choices above, each answered in "Decision". Until they were, F2 planned for A and for
built-in trust in the starter.
