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
| B01 | Remaining suite gaps after 0.29.0 | F1 | Each item under "Quality suites" below reproduced, then fixed or kept as a stated limit: `plan` prices judge calls or says they are unknown, judge calls reach the usage block, `run inspect` counts suites, `dataset_integrity` reports only Hugging Face `datasets.load_dataset`, `regex` has a bound. The released suite is not rebuilt. |
| B02 | Earlier-turn canary leak and tool-argument scope correctness | F1 | Leak then final clean prose still fails; the requested exact file passes while a wider path fails; inspect decoded argument values rather than matching JSON keys. |
| B03 | Memory poisoning evidence and delivered_by payload validation | F1 | Unrelated stored text cannot prove a poisoning test clean; missing delivery payload is refused or explicitly unsupported. |
| B04 | Starter and three short task-oriented recipes | F2 | Clean-install offline run, edited custom check and saved artifact; recorded-answer and actual-application paths clearly distinguish their coverage. |
| B05 | Supported Python result facade and parity tests | F3 | Failed and partial results remain accessible; trust, local rules, calibration, redaction, budgets and manifest agree with CLI. |
| B06 | Output extension discovery | F4 | External installed renderer/reporter, namespace collisions, trust refusals, redaction and pack/lock compatibility all exercised. |
| B07 | Recorded answers and regrading | F5 | No target calls; new grading provenance; declared judge traffic/cost; unavailable evidence remains ungraded. |
| B08 | Connection/adapter parity across endpoint commands | F6 | One custom endpoint can be planned, inspected, probed, monitored and calibrated with equivalent settings. |
| B09 | Profile-relative calibration paths and readable calibration failures | F1/F3 | Same profile resolves from another cwd; unauthorized endpoint has a documented exit rather than an unhandled traceback. |
| B10 | Calibration identity supports several rubric versions and verdict IDs | F1/M1 | Match the actual grader identity; unsupported records decline with an actionable explanation, not an impossible rerun instruction. |
| B11 | Collector measurement envelope and storage | M3 | Independent envelope migration carries measurements, denominator, trials, uncertainty and missingness, with tenant isolation. |
| B12 | Namespaces, declarative packs and ID service | Later | Keep local ID validation; investigate non-executing packs first. An external registry needs evidence of collisions/discovery needs. |
| B13 | Public contributor tasks and adoption checks | F2/F6 | Prepare small issue descriptions from B04/B06/B08; record five developer sessions and two team integrations with consent. Publishing issues is separate maintainer work. |
| B14 | Taxonomy policy for application quality suites | F1 | README and the threat model were reconciled in 0.29.0. The loader already accepts a user suite with no `taxonomy`; CONTRIBUTING ("No mapping, no merge") and CLAUDE.md principle 5 still read as if every rule needs one. State that the rule covers built-in security checks, keep their mappings, and let application quality criteria stay unmapped. |

Existing lockfile/gitleaks, ONNX metadata grading, ATLAS provenance and tooling
items remain open below. Before closing any item, rerun its reproduction; this
audit did not repair runtime code or mark historical defects fixed.

## Accepted designs the roadmap does not carry

`proposed`, written as cycle 5 of the extensibility program (`docs/design/audit-0.22.md`),
with no code behind it. It is not in the "Now" table of `ROADMAP.md`, so it is neither
scheduled nor rejected — a decision, then either a roadmap row or a `superseded by` line.
(`docs/design/attack-techniques.md`, cycle 4, left this list when `ROADMAP.md` placed it under
"Researched after the foundations", behind repeated trials and judge-error correction —
`docs/design/audit-0.26-measurement.md`.)

- `docs/design/namespaced-extension-ids.md` — an open id registry for third-party extensions;
  the `guardana.*` reservation is enforced, the registry is not built.

## Found while sampling the declarative catalog

Both were found on 2026-09-19 writing fixtures for the agent rules, and both are evaluator
changes rather than fixture changes (`docs/design/declarative-fixtures.md`, Decision 6).

- `guardana.agent.tool_argument_scope` reports the exact path its task names as over-broad:
  `forbidden_argument_values: ["*", "/tmp/", ".."]` is matched as substrings, and
  `/tmp/session-42.log` contains `/tmp/`. Reproduce with a scripted agent calling
  `delete_file` with `{"path": "/tmp/session-42.log"}` — the rule yields `fail`. It needs a
  `tool_call` criterion that says "wider than the named file" (an allowed exact value, or
  anchored matching); until then the rule ships no clean fixture and `rule test` says so.
- Without a clean fixture, `tool_argument_scope`'s finding sample would also pass a
  meaningless criterion (`forbidden_argument_values: ["path"]` matches the JSON key) — one
  more reason the missing clean sample above is worth the evaluator change.
- `guardana.agent.memory_poisoning` passes a model whose first session saved *something*
  other than the poison: the store is not empty, the second session recalls it and behaves.
  Whether the poison itself crossed would need a marker the rule does not declare.
- `canary` over an agent run reads only the last prose turn (`Exchange.from_trajectory` keeps
  prose steps, `reply_text` is the last one), so a model that recites a marked tool schema while
  calling a tool and then says "Done." is graded clean. The shipped fixtures of
  `guardana.agent.hidden_context.tool_schema` are single-turn, which is the case the rule grades.

## Deferred by the declarative fixtures design

- A load check that the tool a rule names in `delivered_by` returns a payload at all. A
  scripted fixture cannot see it: `tool_result_injection` with its notice deleted still
  passes all three samples, so only the rule file can be checked for it.

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

- **`calibrations:` in a profile is still resolved against the working directory**, the same
  defect 0.26.1 fixed for `contracts:` (`_run_meta.py::_recorded_calibrations` does `Path(raw_path)`). The fix is
  the same helper.
- **`calibrate` never routes through `run_against_endpoint`**, so an endpoint that answers 401
  surfaces as a traceback rather than as exit 4 with an explanation. Every other endpoint
  command handles it.
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
  (`cli/calibrate.py::_record`), and a run then says "lacks per-class counts; rerun guardana
  calibrate --record", which a rerun cannot fix.

## Quality suites (found shipping ROADMAP row 1)

Found on 2026-09-26 while building and reviewing the suites
(`docs/design/quality-suites.md`).

- The collector trend cannot see K: a rate over one trial and a rate over five share a
  chart (the "Assessments in the collector" row).
- `guardana plan probe` prices suite requests but not judge calls, which K and
  `min_agreement` multiply, and judge calls do not appear in the run's usage block. They are
  bounded by the run's budgets on their own meter, not counted.
- `guardana run inspect`'s trials summary counts repeating rules and leaves suites out.
- `regex` runs the rule author's pattern on every reply with no match-time bound.
- `guardana.training.dataset_integrity` fires on any call named `load_dataset()` without
  `revision=`, whoever defines it: the suite loader first carried that name and the dogfood
  scan reported seven LOW findings on Guardana's own code. The rule could check that the
  name comes from Hugging Face `datasets` before it reports.

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

