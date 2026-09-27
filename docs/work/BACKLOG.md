# Backlog — open work with no owner right now

Each item says where it stands IN THE CODE, as verified on 2026-09-18 when the agent setup was
rebuilt. An item leaves this file by becoming a work file (`/plan`) or by being dropped with a
reason in the commit message. Priorities live in `ROADMAP.md`; this file is the inventory.
Re-verify an item before starting it — several sessions work in this repo.

## Framework usability triage (2026-09-26)

The inventory below is preserved. This triage was checked against 0.29.0 (`5bed6dc`);
priorities use the IDs in [ROADMAP.md](../../ROADMAP.md).
Rationale: [framework audit](../design/framework-usability-audit.md).
No remote issues were created; the GitHub open-issue query returned zero.

| ID | Concrete work | Roadmap | Acceptance evidence |
|---|---|---|---|
| B04 | Starter and three short task-oriented recipes | F2 | Clean-install offline run, edited custom check and saved artifact; recorded-answer and actual-application paths clearly distinguish their coverage. |
| B05 | Supported Python result facade and parity tests | F3 | Failed and partial results remain accessible; trust, local rules, calibration, redaction, budgets and manifest agree with CLI. |
| B06 | Output extension discovery | F4 | External installed renderer/reporter, namespace collisions, trust refusals, redaction and pack/lock compatibility all exercised. |
| B07 | Recorded answers and regrading | F5 | No target calls; new grading provenance; declared judge traffic/cost; unavailable evidence remains ungraded. |
| B08 | Connection/adapter parity across endpoint commands | F6 | One custom endpoint can be planned, inspected, probed, monitored and calibrated with equivalent settings. |
| B10 | Calibration identity supports several rubric versions and verdict IDs | M1 | Match the actual grader identity. Kept for M1 in 0.30.0: re-keying the store is calibration schema 3 and F5 defines grading identity; the decline already no longer promises an impossible rerun. |
| B11 | Collector measurement envelope and storage | M3 | Independent envelope migration carries measurements, denominator, trials, uncertainty and missingness, with tenant isolation. |
| B12 | Namespaces, declarative packs and ID service | Later | Keep local ID validation; investigate non-executing packs first. An external registry needs evidence of collisions/discovery needs. |
| B13 | Public contributor tasks and adoption checks | F2/F6 | Prepare small issue descriptions from B04/B06/B08; record five developer sessions and two team integrations with consent. Publishing issues is separate maintainer work. |

B01, B02, B03, B09 and B14 shipped in 0.30.0 (ROADMAP F1). Existing lockfile/gitleaks,
ONNX metadata grading, ATLAS provenance and tooling items remain open below. Before
closing any item, rerun its reproduction.

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

The report itself was closed with 0.26.1 (see `CHANGELOG.md`). These two are its remaining
items, held back because each adds surface a patch may not add.

- **`--adapter` exists on `probe` and on nothing else.** `plan probe`, `target inspect`,
  `monitor` and `calibrate` all open a connection and none accepts it, so a guarded endpoint
  — the one most worth pre-flighting, watching and calibrating against — can only be probed
  once, by hand. 0.26.1 stopped the error message naming a flag the command rejects; hoisting
  the flag itself is a new argument on four commands.
- **`guardana pack lock` writes `<rule id>: <16 hex>`**, which is the shape gitleaks'
  `generic-api-key` rule fires on — a key containing "secret" beside a high-entropy value.
  It turned a blocking secret-scan gate red on a file Guardana itself wrote. Nesting the
  digest under `{digest: …}` is the clean fix and costs a lock `schema_version` bump and a
  migration.

## Found while fixing the field report

Each was noticed by the lane working next to it and left alone rather than folded in.

- **`onnx_graph` grades ONNX `metadata_props` on the bare presence of an invisible character**,
  which is the defect 0.26.1 fixed in `hidden_instructions` in miniature. The grading lives in
  the rule rather than in the shared `_injection_markers.py` detector, so fixing one did not
  fix the other.

## Tooling debt

- Four scripts have no argument parser and run for real when handed `--help`:
  `scripts/release.py` (fetches from origin, runs the whole gate), `scripts/clean_install_check.py`,
  `scripts/generate_sbom.py`, `scripts/image_smoke.py`. A few lines of `argparse` each; the
  `guard_hook.py` `ask` on `release.py` is the interim guard.
- `site/og.png` is rendered by hand from `scripts/og_card.html` and nothing checks the two agree.
- `.github/workflows/ci.yml` has no job for `scripts/check_claude_setup.py` and
  `scripts/check_ops_catalogue.py`; they run locally through `scripts/ci_local.sh` only. Adding
  them to the `test` job is a two-line change, deferred so the setup lands without touching CI.

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

## Found while building F1 (0.30.0)

- **An uncaught exception exits `1` (`POLICY_FAILED`), not `5`.** `ExitCode.INTERNAL_ERROR`
  is defined and documented in `docs/exit-codes.md` and never raised: `guardana.cli.main:app`
  has no top-level handler, so a crash reads as "the policy failed".
- **Text evaluators other than `canary` read only the final reply of an agent run or a
  scenario's conversation grade** (`keyword`, `contains` with `contains_none`, `regex` with
  `must_match: false`, `guard`): a model that complies in step 1 and refuses in step 2 passes
  `keyword`. Per-step grades exist for scenarios, not for trajectory rules.
- **A canary leak in a scenario is reported once per later canary grade**, because each step
  grades the conversation so far; the rationale names the turn that leaked.
- **The collector envelope (8) sends the target's requests only**; `usage.judge` stays in the
  run document. Part of M3.
- **Target URLs are printed raw in endpoint errors** (`core/target/endpoint.py`, `EndpointError`
  and `apply_budgets` messages); judge URLs are cleaned of userinfo, query and fragment, a
  target URL carrying a credential is not.
- **An MCP probe does not route through `run_against_endpoint`**, so a judge failure during an
  MCP probe ends in a traceback.
- **`monitor` writes no run document**, so what its judges spend per cycle is metered and
  bounded but recorded nowhere.
- **`rules.paths` in a profile still resolves against the working directory**, unlike
  `contracts:` and `calibrations:`; from another directory `plan probe` prints a load warning
  and "0 rule(s) would run" with exit 0.
- **`dataset_integrity` misses indirect calls** (`loader = datasets.load_dataset; loader(...)`,
  `getattr(datasets, "load_dataset")(...)`), besides re-exports through the user's own module.
- **`dataset_integrity` treats any `revision=` as pinned**: `revision="main"`, a branch name,
  `None` or a variable suppress the lead, though only a commit SHA pins the data.
- **A suite that never started because an earlier rule spent the budget leaves no record**,
  like any unstarted rule; the run exits `6`, but its planned cases appear nowhere.
- **A repeating rule stopped by the budget keeps no `trial_summary`, and the terminal counts
  only the cases it reached**: a 10-prompt rule at K=3 with `--max-requests 14` prints
  "5/5 case(s) measured". The run exits `6`; a suite in the same position now keeps its
  declined summary, a rule does not.

## Guardana Control on guardana.dev, and the product line

Left open when the site shipped on 2026-09-25 with Control in coming-soon mode
(`docs/design/guardana-and-control.md`, decision 7).

- When `control.guardana.dev` answers: point the landing page's Control links at it, add
  `control.guardana.dev/llms.txt` to `site/llms.txt`, name Control's released version in its
  JSON-LD, and update `test_nothing_links_to_control_guardana_dev_before_it_answers` and
  `test_guardana_control_is_described_where_its_code_is_public` in the same change.
- `scripts/generate_llms_txt.py` quotes Control's README tagline and "Status: alpha" by hand;
  re-read Control's README when its status changes.
- For the `control` repository, not this one: a site generator for `control.guardana.dev`
  that vendors `site/assets/brand/v1/` and checks it against its `SHA256SUMS`; and its
  `docs/foundation/12_INTEGRATION_WITH_GUARDANA.md` and product spec still describe a
  coupling its ADR-0024 refuses.

