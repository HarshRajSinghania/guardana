# MCP and A2A conformance against servers Guardana did not write (v0.39, F7)

Size: L · Started: 2026-10-03 · Owner: main session · Status: building

## Goal

Build [`docs/design/protocol-conformance.md`](../design/protocol-conformance.md): a run-time
`not_offered` skip; MCP servers that fail part-way stop and keep the run; one live negotiation
with version changes as outcomes; the address guard unwrapping NAT64/6to4; a separate discovery
sender; `is_local_address` deprecated; `guardana.mcp.task_identity`, the `issuer` check,
`guardana.mcp.registry_entry`; an A2A v1 target with three rules; fixtures on the `mcp` and
`a2a-sdk` SDKs. Serves ROADMAP "Now" row F7. Non-goals: decision 14 of the design.

## Open questions (the user's to answer)

None. The eight 0.38 behaviours were confirmed as built.

## Decisions

The design's fourteen, reviewed twice before code (an adversarial pass and a pass for
implementer guesses); both sets of findings are folded into it.

## Blast radius

- [x] persisted document → run schema 17 + `migrate_v16`, round-trip registry, `test_run_schema_v17.py`
- [x] exit codes → `docs/exit-codes.md` and the design table agree (`target_changed` → 4)
- [x] CLI flags (`--a2a`, `--a2a-token-env`, `--a2a-other-token-env`, `--mcp-registry-entry`) → `docs/usage-probe.md`, `docs/usage-plan.md`, `docs/index.md`, `FEATURES.md`
- [x] extension contract (`Sender`, `DiscoverySender`, `NotOffered`, `FixtureOutcome`, two capabilities) → isolated example suites `--no-cache`
- [x] collector → envelope unchanged; one round-trip test for a `not_offered` skip
- [x] rules and a target → `add-a-rule` checklist, `docs/generated/` regenerated, B21 ratchet +5
- [x] reader-facing wording → CHANGELOG and ROADMAP lines through `content-model` at release
- [x] dependency surface → `conformance` group justified in `pyproject.toml`, import-linter contract

## Lanes

Integration branch `integration/v0.39` from `main`. Each coder works in its own worktree: first
`git merge --ff-only integration/v0.39`, commit on its own branch, never stage `site/` or
`docs/generated/` (except `site/index.html`). Main cherry-picks, regenerates (`build_site`,
`generate_llms_txt`, `generate_sitemap`, `generate_docs`), amends, runs the full suite without
touching the tree.

| # | lane | files (main ones) | owner | depends on | verify | done |
|---|---|---|---|---|---|---|
| 1 | core: `NotOffered`, `SkipReason.NOT_OFFERED`, `FixtureOutcome.NOT_OFFERED`, `StopReason.TARGET_CHANGED`, `UnreadableReply`, `TargetChanged`, run schema 17 | `core/rule/{__init__,base,fixture,verify}.py`, `core/report/skipped.py`, `core/runner.py`, `core/verify.py`, `core/gate.py`, `core/target/{endpoint,failure}.py`, `core/manifest/{migrations,model}.py`, `core/report/load.py`, `schemas/run-v17.schema.json`, diff stop explanations, `cli/_errors.py` (`EndpointFlag` gains MCP and A2A token flags) | coder | — | `uv run pytest packages/guardana-core packages/guardana-report -q` | [x] |
| 2 | MCP core: decisions 2–6 | `core/target/{_mcp_http,_mcp_client,_mcp_wire,_mcp_authorization,mcp,__init__}.py`, `core/testing/mcp.py`, `cli/_mcp_run.py`, `rules/mcp/session_binding.py`, tests below | coder | 1 | `uv run pytest packages -q -k "mcp or discovery or redirect or url_credentials or probe_cost or verify"` then all | [x] |
| 3 | A2A: decisions 10–11 | `core/target/{a2a,_a2a_view,_a2a_wire,base,protocols,__init__}.py`, `core/testing/{a2a,__init__}.py`, `core/verify.py` (A2A path), `rules/a2a/*`, `cli/{_a2a_run,probe,plan}.py`, tests | coder | 1 | `uv run pytest packages -q -k "a2a or probe_cost or fixture_coverage"` then all | [x] |
| 4 | MCP rules: decisions 7–9 | `core/target/{_mcp_authorization,_mcp_registry,mcp,base,protocols,__init__}.py`, `rules/mcp/{task_identity,_ids,session_binding,authorization_discovery,registry_entry}.py`, `cli/{probe,plan,_mcp_run}.py`, tests | coder | 2, 3 | `uv run pytest packages -q -k "mcp or probe_cost or fixture_coverage"` then all | [ ] |
| 5 | fixtures: decision 12 | `pyproject.toml`, `uv.lock`, import-linter config, `packages/guardana-rules/tests/conformance/*` | coder | 3 (A2A part), 4 (MCP part) | `uv run pytest packages/guardana-rules/tests/conformance -q` | [ ] |
| 6 | docs: five places, design status, generated pages | `docs/{usage-probe,usage-plan,exit-codes,python-api,writing-rules,extending,threat-model,product-status,index}.md`, `FEATURES.md`, `docs/design/protocol-conformance.md` | main | 1–5 | `uv run python scripts/generate_docs.py --check` and the docs tests | [ ] |

**Lane 1.** `NotOffered` raised before any yield → `SkippedRule(…, NOT_OFFERED, missing, "<ref>:
<detail>")`, out of `rules_run`, `_RuleOutcome.ran` false; after a yield → `CheckError`. Both
catch sites (`runner._run_rule`, `verify.py`). `verify_rule` observes `NOT_OFFERED`; `_gaps`
unchanged in what it demands. `describe_failure` quotes `UnreadableReply` and `TargetChanged`
verbatim; `failure_scope` returns TARGET for both. `TARGET_CHANGED` → exit 4, outranked by
`TARGET_UNAVAILABLE`, outranking `BUDGET_EXHAUSTED`, in `Runner.run` and `ScanResult.merged`.
Tests: a fake rule raising `NotOffered` (skip recorded, gap, `fail_on_skipped` refuses, release
preset exit 2); raising after a yield (error); fixture outcome; schema 16 → 17 migration and
round-trip; collector round-trip of a `not_offered` reason (server tests); stop outranking.

**Lane 2.** Decision 2's table at exactly two sites (`HttpMcpTransport.request` and stdio,
`_Probe._call`); `_fetch` unchanged. Remembered request-scoped failures; one re-open on a legacy
`404`; `negotiate` fallback excludes `BudgetExhausted`; stdio increasing ids and discarded stale
replies. Decision 3: one live `Negotiation` and cached opening shared with the view; every
handshake checks its revision; `TargetChanged` after settlement; the legacy probe;
`notifications/initialized`; `legacy_wire` only `LEGACY_WIRE`. Decision 4 in one function.
Decision 5 (`ValueError` for a lone `sender`). Decision 6. `Sessions.sampling_error`;
`session_binding` inconclusive for it and for an unsettled legacy offer. `write_pin` catches the
new classes; `run_mcp_probe` passes remedies; session ids join `sent_secrets()` and `Verifier`
re-reads secrets after the run. Tests that move: `core/tests/target/test_mcp_{authorization,
discovery_pinning,negotiation,refusal_statuses}.py`, `test_url_credentials_are_never_shown.py`,
`core/tests/test_verify_{grades_recordings,hands_rules_the_calibrations}.py`,
`rules/tests/mcp/{mcp_fixtures,test_cache_scope,test_discovery_target,test_review_findings,
test_unreachable_server}.py`, `rules/tests/test_probe_cost.py`, `cli/tests/test_mcp_cli.py`,
`cli/tests/test_url_credentials_never_leave_the_run.py`, any test calling `is_local_address`.
New: each table row (conversation and probe), a dead server via the CLI (exit 4, `run.json`),
version change mid-run, `2025-06-18` answer, dual-era detection by the legacy probe, every
address form of decision 4, a lone `sender` raising, a socket guard for MCP unit tests.

**Lane 3.** Decisions 10–11 whole. `ScriptedA2aAgent` serves a card, JSON-RPC answers per
caller, tasks per owner, refusals. Tests: every answer class, origin refusal (nothing sent),
bearer only to bearer-capable requirements, equal tokens refused, both credentials redacted,
learned task ids withheld from `run.json`, three-outcome fixtures per rule, `not_offered`.

**Lane 4.** Decisions 7–9. `tasks` section (one anonymous `tasks/list`, `Anonymous.session`,
`offer` precedence); `_ids.py` with `ordered`; issuer absent/mismatch; `RegistryEntry` loading,
URL comparison with `{variable}`, version half; `REGISTRY_ENTRY` in `CAPABILITY_SURFACE`.
Existing fixtures gain `issuer`. Three-outcome fixtures for both new rules.

**Lane 5.** `conformance` group pinned (`mcp==2.3.0`, `a2a-sdk[http-server]==1.2.1`, `uvicorn`),
in `default-groups`, justified; forbidden contract with `include_external_packages = true`;
harness (socket on port 0, uvicorn in a thread, shut down per test module); the design's fixture
table, one test per row. CI and `scripts/ci_local.sh` install it through `uv sync`; the clean
install and example suites do not.

## Done-criteria

- [ ] full gate green, verdict lines read (`scripts/ci_local.sh --quiet`; only `pg_dump` NOT RUN allowed)
- [ ] `FORCE_COLOR=1 GITHUB_ACTIONS=true uv run pytest packages/guardana-cli`
- [ ] `probe --mcp` and `probe --a2a` run against an SDK fixture, `run.json` read
- [ ] reviewed per lane group, then a false-green hunt over the whole diff
- [ ] five documentation places answered; design status moved
- [ ] this file deleted in the release commit; leftovers in `BACKLOG.md`

## Handoff

- Done: lanes 1, 2, 3 and the SDK fixture servers (lane 5, first half) merged on
  `integration/v0.39`; full gate green but for `pg_dump` (NOT RUN, allowed). The MCP request
  ceiling in `test_probe_cost.py` is 72: `notifications/initialized` and the legacy probe are
  metered, as decision 3 says.
- Next: lane 4 (with lane 5's MCP rows and the `--allow-exec` exit fix), then lane 6, review,
  false-green hunt, release.
- How to verify where we are: `git log --oneline main..integration/v0.39`; the integration
  worktree runs `scripts/ci_local.sh --quiet`.
- Surprises: an `mcp` SDK server lists only modern revisions in `server/discover` yet answers
  `initialize` (decision 3's legacy probe).
