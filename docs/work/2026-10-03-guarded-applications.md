# A guarded application, and the outcomes a run states honestly (v0.38)

Size: L · Started: 2026-10-03 · Owner: main session · Status: planning

## Goal

Ship ROADMAP v0.38 and the owner's decisions 1–9 of 2026-10-03 as one release, 0.38.0. The
design, decisions and rejected options: [`docs/design/guarded-applications.md`](../design/guarded-applications.md)
(D1–D13 below refer to its decisions). Non-goals: new protocols, modalities, corpora; the
collector envelope.

## Open questions (the user's to answer)

None — the owner's decisions are fixed. Choices made alone are marked below.

## Decisions

- The design document is the specification; this file only orders the work.
- Integration branch `integration/v0.38` in the main tree. Each coder works in an isolated
  worktree, starts with `git merge --ff-only integration/v0.38`, commits on its own branch, does
  not push. The main session cherry-picks each lane onto the integration branch, then
  regenerates the site and runs the full pytest suite before the next merge.
- decided alone: a rule that attempted cases and graded none is `ungraded_cases` under every
  policy (D6) — reverse by computing the shortfall only when `min_graded_share` is set.
- decided alone: every collector command exits `4` when `connect()` fails, not only `status`
  (D13) — reverse by special-casing `status` in `server/cli/main.py`.
- decided alone: MCP discovery uses no HTTP proxy (D13) — reverse by refusing discovery under a
  proxy instead.
- decided alone: an unreadable `2xx` reply (no `response_path`, not JSON) stops the run as the
  target's failure (D4) — reverse by classifying it with the request-scope `4xx`.

## Blast radius

- [x] persisted documents: run 16, plan 4, recording 3, recipe 3, recipe lock 2 → migrations,
  `schemas/`, round-trip registry
- [x] exit codes → `docs/exit-codes.md`, `docs/design/exit-codes.md`, `test_exit_codes.py`
- [x] CLI flags (`--max-requests-per-minute`) → usage pages, `docs/index.md`, `FEATURES.md`
- [x] extension contract (`Evaluator.read_decline`, `ChatWithMetadata`, `RequestDeclined`) →
  the isolated example suites
- [x] the collector CLI → `docs/usage-collector.md`, PostgreSQL tests
- [x] rules → `docs/generated/` regenerated, `guardana scan packages` at zero
- [x] reader-facing wording → CHANGELOG, ROADMAP "What ships today", the release title via
  content-model at release
- [x] protected contracts on purpose: run schema, exit codes, `pickle_opcode` fingerprints

## Lanes

| # | lane | main files | owner | depends on | verify | done |
|---|---|---|---|---|---|---|
| 1 | schema foundation: run 16, enums, budget field | `gate.py`, `report/shortfall.py`, `assessment.py`, `manifest/*`, `report/load.py`, `budget.py`, `profile/loader.py`, `profile/digest.py`, `diff/compare.py`, `monitor.py`, `schemas/run-v16.schema.json`, renderers | coder | — | `uv run pytest packages/guardana-core packages/guardana-report -q` | [ ] |
| 2 | failure classification, partial run (D4) | `runner.py`, `target/endpoint.py` (`read_with_retry`), `target/failure.py` (new), `verify.py`, `probe.py`, `monitor.py`, `cli/_errors.py`, `cli/probe.py`, `cli/monitor.py` | coder | 1 | `uv run pytest packages/guardana-core packages/guardana-cli -q` | [ ] |
| 3 | adapter keys and transport (D1 matching, D2, D3) | `target/adapter.py`, `target/connection.py`, `target/decline.py` (new), `target/endpoint.py` (`ChatReply`, `EndpointTarget.chat_reply`), `target/protocols.py`, `keeping.py`, `evaluator/config.py` | coder | 1 | `uv run pytest packages/guardana-core/tests/target -q` | [ ] |
| 4 | unread models and pickle findings (D10, D11) | `guardana-rules/.../supply_chain/*`, `report/location.py` | coder | 1 | `uv run pytest packages/guardana-rules -q` | [ ] |
| 5 | recipe target and lock sources (D7, D8) | `core/recipe.py`, `cli/recipe.py`, `schemas/recipe-v3`, `schemas/recipe-lock-v2` | coder | 1 | `uv run pytest packages/guardana-core/tests/test_recipe*.py packages/guardana-cli/tests/test_recipe*.py -q` | [ ] |
| 6 | pack validate owners (D13) | `registry.py`, `pack/discover.py`, `cli/pack.py` | coder | 1 | `uv run pytest -q -k "pack or registry or taxonom"` | [ ] |
| 7 | MCP discovery pinning (D13) | `target/_mcp_http.py`, `target/_mcp_authorization.py` | coder | 1 | `uv run pytest packages/guardana-core/tests/target packages/guardana-rules/tests/mcp -q` | [ ] |
| 8 | collector exit 4 (D13) | `server/cli/main.py`, `server/cli/codes.py` | coder | 1 | `GUARDANA_TEST_DATABASE_URL=… uv run pytest packages/guardana-server -q` | [ ] |
| 9 | pacing (D5) | `usage.py`, `cli/_budget_flags.py`, `core/plan.py`, `cli/plan.py`, `schemas/plan-v4` | coder | 1 | `uv run pytest packages/guardana-core/tests/test_budgets.py packages/guardana-core/tests/test_plan.py packages/guardana-cli -q` | [ ] |
| 10 | decline grading, recording 3 (D1 rest, D3 kept) | `exchange.py`, `evaluator/*.py`, `rule/yaml_rule.py`, `rule/suite_rule.py`, `rule/scenario_rule.py`, `suite.py`, `recording.py`, `target/recorded.py`, `promotion.py`, rules `output/secrets.py`, `seeded/*` | coder | 3 | `uv run pytest packages/guardana-core packages/guardana-rules -q` | [ ] |
| 11 | empty target and graded share (D6, D9) | `runner.py`, `core/plan.py`, `profile/model.py`, `profile/loader.py`, the ~20 pinned tests | coder | 2, 9 | `uv run pytest packages/guardana-core packages/guardana-cli -q` | [ ] |
| 12 | principle 3, docs five places, design accepted | `CLAUDE.md`, `lessons.md`, `CONTRIBUTING.md`, `FEATURES.md`, `docs/*` | main | 2–11 | `uv run pytest packages/guardana-core/tests/test_docs_consistency.py -q`, `build_site.py --check` | [ ] |

Wave 1: lane 1. Wave 2, in parallel: lanes 2–9. Wave 3: lanes 10 and 11. Then lane 12, the
full gate, review, false-green hunt, release.

Each coder lane updates the docs its behaviour changes (usage pages, `docs/providers.md`,
`docs/profiles.md`, `docs/exit-codes.md`, `docs/python-api.md`, `docs/threat-model.md`) in
its own commit, technical text restating the code; no CHANGELOG edits (lane 12 and the
release write those).

### Per lane

- **2 (D4).** `target/failure.py` (new): `describe_failure`, `FailureRemedies`, the request/target
  classification. `endpoint.py`: `EndpointUnreachable`, `read_with_retry` timeouts. `runner.py`:
  `_run_rule` (re-raise `JudgeUnavailableError` first), `_RuleOutcome` stop + error, `Runner.run`
  precedence, quoting from new `Runner` fields. `verify.py` (`secrets`, `remedies`, stopped
  result), `probe.py` (`run_target_probe` stops), `monitor.py`, `evaluator/config.py`
  (`Judge.ask` names `EndpointUnreachable`), `cli/_errors.py`, `cli/probe.py`, `cli/monitor.py`,
  `cli/recipe.py` (partial artifact). Tests that move: `test_errors_cli.py` (400 → 2),
  `test_exit_codes.py`, `test_probe_cli.py`, `test_monitor_cli.py`, `test_runner_concurrency.py`,
  `test_verify_surface.py`, `test_provider_conformance.py` (timeout). Docs: `exit-codes.md`,
  `design/exit-codes.md`, `usage-probe.md`, `providers.md` ("Every HTTP transport"),
  `python-api.md`, `usage-monitor.md`, `profiles.md` (beside `fail_on_error`).
- **3 (D1 matching, D2, D3).** `target/decline.py` (new: `Decline`, `DeclineReading`,
  `RequestDeclined`), `adapter.py` (`AdapterConfig` keys, `Fetch` → status and body, matching,
  `HTTPError` re-raised over the read body, `send_with_metadata`), `connection.py`
  (`_ADAPTER_KEYS`, `load_adapter(for_judge=)`), `endpoint.py` (`ChatReply.meta`,
  `MetadataReportingTransport`, `EndpointTarget.chat_reply`), `protocols.py`
  (`ChatWithMetadata`), `evaluator/config.py` (judge adapter refuses the two keys), the fake
  provider's adapter shape. Keeping and recordings are lane 10's. Docs: `usage-probe.md`
  (guarded endpoint), `providers.md` (retried statuses), `profiles.md` (judge `adapter:`).
- **4 (D10, D11).** `supply_chain/{notebook_payload,pickle_opcode,onnx_graph,keras_lambda,
  chat_template,model_format,saved_model_ops}.py`, `report/location.py`. Tests:
  `test_unexamined_components.py`, `test_pickle_opcode.py`, `test_pickle_archive_budget.py`,
  `test_suffix_case.py`, the per-format unreadable tests. Docs: `usage-scan.md`,
  `model-formats.md`, `usage-testing.md` (pickle summary), `FEATURES.md` lines on unscanned
  files; `generate_docs.py`; `guardana scan packages` stays at zero.
- **5 (D7, D8).** `core/recipe.py`, `cli/recipe.py`, `schemas/recipe-v3.schema.json`,
  `schemas/recipe-lock-v2.schema.json`, `test_recipe*.py`, `test_recipe_documents.py`, the
  round-trip registry. Docs: `usage-recipe.md`.
- **6 (D13 packs).** `registry.py` (taxonomy owners, snapshot), `pack/discover.py`
  (`Registered.taxonomy_owners`, `check_pack`), `cli/pack.py` (`_registered`). Docs:
  `usage-pack.md`.
- **7 (D13 MCP).** `_mcp_http.py` (pinned connection, discovery-only flag,
  `AddressRefusedError`), `_mcp_authorization.py` (`_fetch`, local decided once). Tests with a
  local server and a patched resolver. Docs: `threat-model.md` (the rebinding residual risk).
- **8 (D13 collector).** `server/cli/main.py`, `server/cli/codes.py`, `test_collector_cli.py`.
  Docs: `usage-collector.md`.
- **9 (D5).** `usage.py` (`reserve` pacing, `sleep=`), the `apply_budgets` that refuse
  ceilings, `cli/_budget_flags.py`, `cli/config.py`, `core/plan.py` and `cli/plan.py` (floor,
  refusal), `schemas/plan-v4.schema.json` and the plan schema constant. Docs: `profiles.md`
  (budgets), `usage-probe.md`, `usage-plan.md`, `usage-monitor.md`, `usage-grade.md` (flags).
- **10 (D1 grading, D3 kept).** `exchange.py` (`decline`), `evaluator/base.py` (`grade`,
  `grade_decline`, `read_decline`), the six overriding evaluators, `assessment.from_verdict`
  (`reason=`), `rule/{yaml_rule,suite_rule,scenario_rule}.py`, `suite.py` (correction), rules
  `output/secrets.py` and `seeded/*`, `keeping.py`, `recording.py` (format 3,
  `schemas/recording-v3.schema.json`), `target/recorded.py`, `promotion.py`, `cli/case.py`,
  `core/inspect.py`. Docs: `writing-rules.md`, `extending.md` (evaluators), `usage-probe.md`,
  `usage-grade.md`, `usage-case.md`, `usage-target.md`. Example suites (`custom_rule`) green.
- **11 (D6, D9).** `runner.py` (empty target and graded share, one function each that
  `build_plan` also calls for the empty target), `core/plan.py`, `profile/model.py`
  (`FailOn.min_graded_share`, `OMITTED_WHEN_DEFAULT`), `profile/loader.py`, `cli/plan.py`
  (note), `cli/config.py`. Tests flipped: the empty-directory tests in `test_scan_cli.py`,
  `test_exit_codes.py`, `test_output_warns_about_format.py`, `test_plugin_trust_default.py`,
  `test_plan_refuses_a_run_that_cannot_pass.py`, `test_diff_left_scan_cli.py`,
  `test_assert_secure.py`, `test_file_scope.py`. Docs: `profiles.md`, `usage-scan.md`,
  `usage-plan.md`, `README.md` (empty directory line), `product-status.md`.

## Done-criteria

- [ ] full gate green, verdict lines read (`scripts/ci_local.sh --quiet`)
- [ ] `probe --adapter` against the local fake provider with a declined, a `400`, a `429` and a
  slow reply; `scan` of an empty directory; the saved runs read
- [ ] reviewed (at most three rounds), false-green hunt on the whole diff
- [ ] the five documentation places answered
- [ ] this file deleted in the release; leftovers in `BACKLOG.md`

## Handoff

- Done: research (five code maps), design written and reviewed once (round 1: 2 blockers,
  14 major, all folded in).
- Next: design review round 2, then lane 1.
- How to verify where we are: `git log --oneline integration/v0.38 ^main`.
- Surprises: `JudgeUnavailableError` is an `EndpointError`; an editable install's `RECORD`
  lists no source file.
