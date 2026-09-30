# Backlog — open work with no owner right now

Each item says where it stands IN THE CODE, as verified on 2026-09-18 when the agent setup was
rebuilt. An item leaves this file by becoming a work file (`/plan`) or by being dropped with a
reason in the commit message. Priorities live in `ROADMAP.md`; this file is the inventory.
Re-verify an item before starting it — several sessions work in this repo.

## Triage (2026-09-30, after the direction audit)

The inventory below is preserved. Priorities use the IDs in [ROADMAP.md](../../ROADMAP.md);
the order and its evidence are in the [direction audit](../design/audit-0.31-direction.md),
which supersedes the [framework audit](../design/framework-usability-audit.md)'s order.
No remote issues were created; the GitHub open-issue query returned zero.

| ID | Concrete work | Roadmap | Acceptance evidence |
|---|---|---|---|
| B04 | Starter and three short task-oriented recipes | F2 | Clean-install offline run, edited custom check and saved artifact; recorded-answer and actual-application paths clearly distinguish their coverage. |
| B05 | Supported Python result facade and parity tests | F3 | Failed and partial results remain accessible; trust, local rules, calibration, redaction, budgets and manifest agree with CLI. |
| B06 | One redacted export and one webhook | F4 | An independently installed package provides both through the common redaction boundary, collision checks, trust modes and locks; delivery status observable; offline use sends nothing. The general plugin contract is deferred. |
| B07 | Recorded answers and regrading | F5 | No target calls; new grading provenance; declared judge traffic/cost; unavailable evidence remains ungraded. |
| B08 | Connection/adapter parity across endpoint commands | F6 | One custom endpoint can be planned, inspected, probed, monitored and calibrated with equivalent settings. |
| B10 | Calibration identity supports several rubric versions and verdict IDs | M1 | Match the actual grader identity. Kept for M1 in 0.30.0: re-keying the store is calibration schema 3 and F5 defines grading identity; the decline already no longer promises an impossible rerun. |
| B11 | Collector measurement envelope and storage | M3 | Independent envelope migration carries measurements, denominator, trials, uncertainty and missingness, with tenant isolation. |
| B12 | Non-executing declarative packs | parallel lane, decided before F2 | Keep local ID validation. Decide whether a pack can ship checks that execute no Python. The public extension-ID service is dropped (direction audit). |
| B13 | Public contributor tasks and adoption checks | F2/F6 | Prepare small issue descriptions from B04/B06/B08; record five developer sessions and two team integrations with consent. Publishing issues is separate maintainer work. |
| B15 | Result-state matrix across renderers | Q1 | One shared test renders stopped, interrupted, verified-nothing, unverified, errored and shortfall runs through human, JSON, SARIF and JUnit and asserts they agree; JUnit's stopped run shipped in 0.31.0. |
| B16 | Trace document digest over content | Q1 | `core/trace/load.py::_size_and_name` replaced by a digest of the bytes read in the one bounded pass; the saved run says which kind it carries; a same-size edit changes it. |
| B17 | Strict release-gate preset | Q1 | A named preset fails on a skipped or unverified selected check (`fail_on_skipped`, `fail_on_inconclusive`); documented beside the existing presets; `plan` agrees with it. |
| B18 | Detection limits per rule family | Q1 | A generated page separates tested invariants, heuristic leads and framework mappings per rule family, from rule metadata, never hand-written. |
| B19 | MCP and A2A conformance fixtures | F7 | Both MCP revisions against independent server fixtures (authorization, task identity, cache scope, registry metadata, version change) and one A2A v1 fixture; unsupported capability recorded as missing coverage. |
| B20 | Live retrieval pilot | F6 | One retrieval target catches a poisoned document and a tenant-filter failure without an uncontrolled side effect. |
| B21 | Three-outcome fixtures for every built-in | 1.0 | The ratchet in `test_builtin_fixture_coverage.py` (12 of 51 at 0.31.0) reaches every rule that can decline. |
| B22 | A time bound for `regex` | Later | A crafted reply can make an author's backtracking pattern run for a very long time; the 65,536-character bound limits input, not time. Any fix that adds a dependency needs principle 6's justification. |

B01, B02, B03, B09 and B14 shipped in 0.30.0 (ROADMAP F1). The lockfile/gitleaks and
script-parser items shipped in 0.31.0; ONNX metadata grading, ATLAS provenance and the other
items remain open below. Before closing any item, rerun its reproduction.

## Accepted designs the roadmap does not carry

`proposed`, written as cycle 5 of the extensibility program (`docs/design/audit-0.22.md`),
with no code behind it. It is not in the "Now" table of `ROADMAP.md`, so it is neither
scheduled nor rejected — a decision, then either a roadmap row or a `superseded by` line.
(`docs/design/attack-techniques.md`, cycle 4, left this list when `ROADMAP.md` placed it under
"Researched after the foundations", behind repeated trials and judge-error correction —
`docs/design/audit-0.26-measurement.md`.)

- `docs/design/namespaced-extension-ids.md` — an open id registry for third-party extensions;
  the `guardana.*` reservation is enforced, the registry is not built.

## Deferred by the declarative fixtures design

- A single-turn rule with several `prompts:` scripts one `reply:`, and the double
  repeats it, so every prompt is graded against the same answer and `rule test` counts
  one passing sample per fixture whatever the prompt list holds. That is a coherent
  double — a model that answers this way to anything — and it is not what a reader of
  "3 fixture(s) passed" necessarily assumes. `_scenario_script` refuses the analogous
  mismatch for steps because there the order matters. Either the single-turn parser
  gains a way to say which prompt a sample is about, or the vocabulary says plainly
  that one reply answers them all.
- A way for a fixture to say *why* a rule must decline or *which* turn must fire —
  `verify_rule` folds every result into one of three outcomes, for Python fixtures too. An
  additive field on `RuleFixture`, so a change to the contract every fixture shares.
- Corpus rows for multi-step scenario and agent-run fixtures: the graded prefix is the rule's
  knowledge and a `tool_call` verdict has no column in the corpus format.

## Taxonomy currency

- The MITRE ATLAS catalogue records `version: 5.6.0`, which is the ATLAS *data format* release
  and not the *content* release its eighteen entries were transcribed from. ATLAS publishes the
  two on separate tracks, and content releases have landed since that format version. The
  provenance field is the first fix; mapping the agent-facing techniques the newest releases add
  is rule work for the parallel contributor lane. See `docs/design/audit-0.25-market.md`.

## From the first field report (0.26.0), still open

The report itself was closed with 0.26.1 (see `CHANGELOG.md`); the lock layout shipped in
0.31.0. This one remains, held back because it adds surface a patch may not add.

- **`--adapter` exists on `probe` and on nothing else.** `plan probe`, `target inspect`,
  `monitor` and `calibrate` all open a connection and none accepts it, so a guarded endpoint
  — the one most worth pre-flighting, watching and calibrating against — can only be probed
  once, by hand. 0.26.1 stopped the error message naming a flag the command rejects; hoisting
  the flag itself is a new argument on four commands.

## Found while fixing the field report

- **`onnx_graph` grades ONNX `metadata_props` HIGH on the bare presence of an invisible
  character.** Grading it by the payload shape `hidden_instructions` uses was tried for 0.31.0
  and withdrawn before release: one zero-width character that splits an override phrase
  (`ig<U+200B>nore previous instructions`) matches no phrase and graded LOW, a key and a value
  graded apart missed a phrase in one beside a character in the other, and scattered
  characters below a run of eight graded LOW. ONNX metadata is written by an exporter, so the
  PDF-extraction reason for leniency may not apply. `hidden_instructions` has the same
  split-phrase gap: `OVERRIDE_PHRASE` does not match across a zero-width character.

## Tooling debt

- `site/og.png` is rendered by hand from `scripts/og_card.html` and nothing checks the two agree.

## Judge-error correction (found shipping `docs/design/judge-error-correction.md`)

Found on 2026-09-24 by the pre-ship review of ROADMAP row 1, lane 2.

- One calibration per evaluator id per file (`calibration/store.py`, keyed by the registry
  id), so two rubric versions of `llm_judge` cannot both be recorded; a run graded by the
  other one refuses with "calibration is for …".
- An evaluator whose verdicts carry several ids is recorded without per-class counts
  (`cli/calibrate.py::_record`), so no rate it grades can be corrected. The decline says
  so; counting per assessor id is B10, in M1.

## Quality suites (found shipping ROADMAP row 1)

Found on 2026-09-26 while building and reviewing the suites
(`docs/design/quality-suites.md`).

- The collector trend cannot see K: a rate over one trial and a rate over five share a
  chart (the "Assessments in the collector" row).

## Found while building F1 (0.30.0), still open after 0.31.0

- **`keyword` at a scenario's conversation level grades the final reply only.** In an agent run
  a closing refusal after a reply without one is `inconclusive` (0.31.0); in a scenario the
  earlier replies answer earlier messages, so a warm-up without a refusal says nothing. A
  scenario grades the escalated ask with a step-level `keyword`, and the docs say so.
- **The collector envelope (8) sends the target's requests only**; `usage.judge` stays in the
  run document. Part of M3.
- **An MCP server that cannot be reached exits `2`, not `4`.** Every MCP rule records it as
  unverified or as an error, so the run is indeterminate; an endpoint probe exits `4`. MCP
  rules call no judge, so the judge-failure traceback this item used to name cannot occur, and
  `--write-mcp-pin` exits `4` since 0.31.0.
- **Server-supplied URLs in MCP authorization documents** (`resource_metadata`, `issuer`) are
  shown as the server gave them; a target URL is cleaned by `display_url` since 0.31.0.
- **`monitor` writes no run document**, so what its judges spend per cycle is metered and
  bounded but recorded nowhere.
- **`dataset_integrity` does not follow a loader across modules** (a re-export through the
  user's own module), a `revision` passed by position, or a name rebound after it was bound
  to the loader: aliases are tracked per file, in document order, without scopes.
- **A suite that never started because an earlier rule spent the budget leaves no record**,
  like any unstarted rule; the run exits `6`, but its planned cases appear nowhere.
- **A repeating rule stopped by the budget keeps no `trial_summary`.** The terminal says its
  count ends at the stop (0.31.0); recording the cut-off rule, like a never-started one above,
  needs run schema 11.
- **An interrupted command writes nothing it had not already written.** Ctrl-C exits `7` since
  0.31.0; keeping the partial run of a `probe` as evidence is a feature, not a fix.
- **A crash while `guardana.cli.main` is being imported exits `1` with a traceback**: it happens
  before `main()` maps crashes to `5`. An `EOFError` outside a rule (a prompt reading a closed
  stdin) becomes Typer's `Abort` and exits `1` too.
- **`dataset_integrity` still misses** a module aliased by assignment (`ds = datasets`), a
  loader wrapped in `functools.partial`, and `importlib.import_module("datasets")`.

## From the quality and extensibility review (0.31.0)

An independent review (codex, read-only, 2026-09-30) found these; each was checked in the code.
Its JUnit finding shipped in 0.31.0, and its two documentation findings were corrected.

- **A trace's `document_digest` identifies name and size, not content** — B16, in Q1.
- **Built-in three-outcome fixtures are a ratchet at 12 of 51 rules** — B21, a 1.0 criterion.
- **A strict CI policy is one profile away, not a preset** — B17, in Q1.
- Its claim that generated-documentation checks run only locally was refuted: pytest runs
  every generator's `--check`, and CI runs pytest.

## Guardana Control on guardana.dev, and the product line

Left open when the site shipped on 2026-09-25 with Control in coming-soon mode
(`docs/design/guardana-and-control.md`, decision 7); Control's own site answered on 2026-09-30.

- When `control.guardana.dev/llms.txt` answers, list it in `site/llms.txt` and turn
  `test_llms_txt_names_no_control_resource_that_does_not_answer` around; the site itself is
  linked since it answered.
- Control's `softwareVersion` in the landing page's JSON-LD is written by hand (`0.2.0-alpha`):
  update it with each Control release, or have `scripts/sync_site.py` read the latest release.
- `scripts/generate_llms_txt.py` quotes Control's README tagline and "Status: alpha" by hand;
  re-read Control's README when its status changes.
- For the `control` repository, not this one: a site generator for `control.guardana.dev`
  that vendors `site/assets/brand/v1/` and checks it against its `SHA256SUMS`; and its
  `docs/foundation/12_INTEGRATION_WITH_GUARDANA.md` and product spec still describe a
  coupling its ADR-0024 refuses.

