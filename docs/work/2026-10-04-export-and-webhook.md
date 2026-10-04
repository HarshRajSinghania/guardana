# An installed package adds one redacted export and one webhook

Size: L · Started: 2026-10-04 · Owner: main session · Status: building

## Goal

`--format <installed>` writes an export and `--reporter <installed>://…` delivers a webhook, both
supplied by an independently installed package, imported only when selected, handed what the
saved run holds, with a delivery line on every path and exit `8` when an installed output fails.
ROADMAP v0.40 / F4, BACKLOG B06, milestone criteria "F4 export and webhook work without a fork" and
"case outcomes and missing evidence survive serialization, redaction and export". Non-goals: diff
renderers, binary formats, several reporters per run, moving the collector onto the delivery line.

The design is `docs/design/export-and-webhook.md` (d4bd2f3f); this file only sequences it. Where a
lane's table and the design's steps disagree, the steps win and the table is corrected in the same
commit.

## Open questions (the user's to answer)

- [ ] Principle 3 names the collector only — default: a reporter in `--reporter` is a destination
  the run names; wording left to the owner (reported at the end).

## Decisions

Recorded in the design (decisions 1–10, "Rejected"). Integration: branch `integration/v0.40`,
worktree `<scratchpad>/int-v040`; each coder runs in an isolated worktree, first
`git merge --ff-only integration/v0.40`, commits on its own branch, never touches `site/` or
`docs/generated/`; main cherry-picks, regenerates (generate_docs, sync_site, build_site,
generate_llms_txt, generate_sitemap), amends, and runs the full gate in the integration worktree.

## Blast radius

- [x] persisted documents: pack manifest schema 3, lock schema 3 (written only with outputs), `schemas/pack-manifest-v3`, `schemas/pack-lock-v3`, round trips and refusals
- [x] exit code 8 → `cli/exit_codes.py`, `docs/exit-codes.md`, its test, design table
- [x] CLI flags `--format` / `--reporter` value sets → usage pages, `docs/index.md`, `FEATURES.md`, `clean_install_check.py`
- [x] extension contract: two entry-point groups → all isolated example suites, `new_pack_check.py`
- [x] a script change → `docs/maintainers/ops-catalogue.md` (ci_local.sh step)
- [x] protected contracts: entry-point groups, exit codes, schemas, CLI flag values → CLAUDE.md and rules updated together
- [ ] collector — not touched; [ ] rule/evaluator/target — none added

## Lanes

| # | lane | files | owner | depends on | verify | done |
|---|---|---|---|---|---|---|
| 1 | output contract, selection, boundary, render, deliver, discovery, `load_verification` | `core/output.py` (new), `core/entrypoints.py`, `core/verify.py`, `core/tests/test_output_*.py`, `guardana-report/tests/test_reserved_renderer_names.py` | coder | — | `uv run pytest packages/guardana-core/tests -q -k output` + mypy + ruff | [ ] |
| 2 | pack manifest 3, `output_api`, lock 3, pack discovery and validate/lock refusals, `new-pack` schema 2 | `core/pack/{model,load,lock,discover}.py`, `cli/pack.py`, `cli/new_pack.py`, `schemas/pack-*-v3.schema.json`, pack tests | coder | 1 | `uv run pytest packages/guardana-core/tests packages/guardana-cli/tests -q -k "pack or lock or new_pack"` | [ ] |
| 3 | CLI: `resolve_format`, `split_reporter`, refusals, emit verbatim, exit 8, delivery line and `not_sent` guard | `cli/{_formats,_reporting,_output,exit_codes,scan,probe,grade,analyze_trace,monitor,import_observations,_mcp_run,_a2a_run,_probe_run}.py`, `docs/exit-codes.md` (row only), `scripts/clean_install_check.py`, cli tests | coder | 1 | `uv run pytest packages/guardana-cli/tests -q` | [ ] |
| 4 | `doctor` states for outputs | `cli/doctor.py`, `cli/tests/test_doctor_*` | coder | 1 | `uv run pytest packages/guardana-cli/tests -q -k doctor` | [ ] |
| 5 | `examples/output_pack` (table, webhook, manifest, README, tests, reference-verifier receiver) and its isolated suite | `examples/output_pack/**`, `scripts/ci_local.sh`, `.github/workflows/ci.yml`, `.claude/rules/examples.md` | coder | 1, 2, 3 | the isolated suite command from ci_local.sh | [ ] |
| 6 | documentation, five places, CLAUDE.md, SECURITY.md, ops catalogue | design "Documentation" list | main | 1–5 | `uv run python scripts/build_site.py --check` + doc tests | [ ] |

Lanes 2, 3 and 4 run in parallel after 1 (disjoint files). Lane 3 owns `docs/exit-codes.md`
only for the row its test pins; lane 6 writes the prose around it.

**Lane 1 traps.** `installed_entry_points` stays the one enumeration (its docstring). Catch
`BaseException` but re-raise `KeyboardInterrupt` everywhere plugin code runs. `deliver` uses a
daemon thread; the test for the deadline injects a short deadline, never sleeps 30 s. `outbound`
redacts `manifest.target.ref` only when `leaves_machine`.

**Lane 2 traps.** Lock schema 2 is still written when nothing pins an output; `_pack` ignores
unknown keys today, so a schema ≤2 lock carrying output keys must be refused explicitly.
`_discover_completely`'s refusal fires on output refusals from metadata before any manifest read.

**Lane 3 traps.** `check_reporter_url` is the first statement of five commands; `split_reporter`
goes before it. Probe has several finishing paths (`_finish_probe`, MCP `--write-mcp-pin`, A2A,
fixtures); the delivery and the `not_sent` guard cover all. A stop keeps 4/6/7 over exit 8.

**Lane 5 traps.** Entry points name the package (`acme_outputs:provide_table`), not a submodule.
The receiver is `http.server.ThreadingHTTPServer`; only `standardwebhooks==1.1.0` is added with
`--with`. The webhook never imports it.

## Done-criteria

- [ ] full gate green, verdict lines read (`scripts/ci_local.sh --quiet`), every isolated suite run
- [ ] `guardana scan` with `acme-table` and `acme-webhook` run against the reference receiver; CSV and delivery line read
- [ ] reviewed (`/review`, at most 3 rounds), then the false-green hunt over the whole diff
- [ ] the five documentation places answered in the same change
- [ ] this file deleted in the shipping commit; leftovers in `BACKLOG.md`

## Handoff

- Done: design d4bd2f3f; decisions commit 2e45e50b (gate green, pg_dump NOT RUN).
- Next: lane 1.
- How to verify where we are: `git log integration/v0.40`; the gate in `<scratchpad>/int-v040`.
- Surprises: —
