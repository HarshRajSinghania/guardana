# Backlog — open work with no owner right now

Each item says where it stands IN THE CODE, as verified on 2026-09-18 when the agent setup was
rebuilt. An item leaves this file by becoming a work file (`/plan`) or by being dropped with a
reason in the commit message. Priorities live in `ROADMAP.md`; this file is the inventory.
Re-verify an item before starting it — several sessions work in this repo.

## Triage (2026-09-30, after the direction audit)

The inventory below is preserved. Priorities use the IDs in [ROADMAP.md](../../ROADMAP.md);
the order and its evidence are in the [direction audit](../design/audit-0.31-direction.md),
which supersedes the [framework audit](https://github.com/guardana/guardana/blob/257b6bb98be678fc387d11ea92b180882c7c6a93/docs/design/framework-usability-audit.md)'s order.
No remote issues were created; the GitHub open-issue query returned zero.

| ID | Concrete work | Roadmap | Acceptance evidence |
|---|---|---|---|
| B04 | Starter and three short task-oriented recipes | F2 | Clean-install offline run, edited custom check and saved artifact; recorded-answer and actual-application paths clearly distinguish their coverage. |
| B06 | One redacted export and one webhook | F4 | An independently installed package provides both through the common redaction boundary, collision checks, trust modes and locks; delivery status observable; offline use sends nothing. The general plugin contract is deferred. |
| B08 | Connection/adapter parity across endpoint commands | F6 | One custom endpoint can be planned, inspected, probed, monitored and calibrated with equivalent settings. |
| B10 | Calibration identity supports several rubric versions and verdict IDs | M1 | Match the actual grader identity. Kept for M1 in 0.30.0: re-keying the store is calibration schema 3 and F5 defines grading identity; the decline already no longer promises an impossible rerun. |
| B11 | Collector measurement envelope and storage | M3 | Independent envelope migration carries measurements, denominator, trials, uncertainty and missingness, with tenant isolation. |
| B12 | Non-executing declarative packs | parallel lane, decided before F2 | Keep local ID validation. Decide whether a pack can ship checks that execute no Python. The public extension-ID service is dropped (direction audit). |
| B13 | Public contributor tasks and adoption checks | F2/F6 | Prepare small issue descriptions from B04/B06/B08; record five developer sessions and two team integrations with consent. Publishing issues is separate maintainer work. |
| B19 | MCP and A2A conformance fixtures | F7 | Both MCP revisions against independent server fixtures (authorization, task identity, cache scope, registry metadata, version change) and one A2A v1 fixture; unsupported capability recorded as missing coverage. |
| B20 | Live retrieval pilot | F6 | One retrieval target catches a poisoned document and a tenant-filter failure without an uncontrolled side effect. |
| B21 | Three-outcome fixtures for every built-in | 1.0 | The ratchet in `test_builtin_fixture_coverage.py` (12 of 51 at 0.31.0) reaches every rule that can decline. |
| B22 | A time bound for `regex` | Later | A crafted reply can make an author's backtracking pattern run for a very long time; the 65,536-character bound limits input, not time. Any fix that adds a dependency needs principle 6's justification. |

B07 shipped in 0.35.0 (ROADMAP F5). B15, B16, B17 and B18 shipped in 0.32.0 (ROADMAP Q1). B01, B02, B03, B09 and B14 shipped in 0.30.0 (ROADMAP F1). The lockfile/gitleaks and
script-parser items shipped in 0.31.0; ONNX metadata grading, ATLAS provenance and the other
items remain open below. Before closing any item, rerun its reproduction.

## Found while building Q1 (0.32.0)

Found by the pre-ship review and the false-green hunt on 2026-09-30; each was reproduced.

- **`scan` of an empty directory passes under every preset, `release` included.** Every
  artifact rule runs over no file and concludes: exit `0`, JUnit `tests="19" errors="0"`,
  SARIF `executionSuccessful: true`, and `plan scan` agrees. `docs/profiles.md` says so.
  Recording a target that holds no file as a coverage shortfall changes the exit code of
  every scan of an empty path, so it needs a decision, and a new shortfall kind is a run
  schema change.
- **A protocol the target does not speak is a capability skip.** A chat endpoint skips the
  nine MCP rules, so `probe --preset release` is `indeterminate` against any single endpoint
  unless a profile selects the rules it serves (documented). Decide whether an MCP rule
  against a chat endpoint, or a chat rule against an MCP server, is `not_applicable`.
- **A trace reads as `content_prefix` when `MAX_SPANS` stops a read of a file the buffer
  already held whole.** Conservative: `content` is claimed only after the raw read returned
  end of file.
- **Every Python built-in declared `invariant` is "invariant, not sampled"** on the
  detection-limits page until it ships samples (B21).
- **Observation dialect detection reads the document a second time**, bounded like the
  first read.

## Found while preparing the OpenSSF badge (after 0.32.0)

A code sweep for the `know_common_errors` attestation on 2026-09-30. The first three were
reproduced; the rest are the sweep's reading with its anchors, not yet reproduced.

- **The dashboard sends no Content-Security-Policy and nothing tests its escaping** against a
  crafted payload (`server/dashboard.py:179`); `docs/threat-model.md` T7 now says so.
- The CLI prints model output and file names verbatim, so ANSI and other control
  characters reach the terminal (`report/human.py:37`).
- The endpoint, adapter and reporter HTTP clients follow redirects without the private-address
  guard the MCP discovery client applies (`core/target/endpoint.py:231`).
- `analyze-trace --write-trace` writes the trace unredacted (`cli/analyze_trace.py:208`).
- A stdio MCP server's `readline()` has no size cap or timeout
  (`core/target/_mcp_client.py:251`), and a zip's member count is uncapped
  (`rules/supply_chain/pickle_opcode.py:294`).
- A symlinked file inside a scanned directory is read even when it points outside the root
  (bounded by the reader caps).
- The dashboard cookie is `Secure` only when the app itself sees `https`
  (`server/app.py:394`), and an unknown key prefix returns before hashing
  (`server/auth.py:200`), which tells a caller whether a prefix exists.
- `llm_judge` places the transcript into its prompt unfenced (`core/evaluator/llm_judge.py:26`).
- Container base images are pinned by tag, not by digest (`deploy/docker/cli.Dockerfile:12`).

## Left by F5 (0.35.0)

- **Grading a budget-stopped probe's sidecar can pass where the probe exited `6`.** A suite
  counts every unrecorded trial as failed and passes when its bar still holds, as it does for
  any ungraded trial; the stop survives only in `run.recording.origin.stopped_by` and a stderr
  note. Whether a stopped origin should make the graded run decline is the owner's call.
- **Only the built-in endpoint keeps exchanges, and only its plain pass.** A pack's endpoint
  target would need a protocol to keep them; canary passes and tool offers are not kept, so
  canary and agent rules cannot be graded again.
- **`grade` has no `--reporter`**: the collector envelope carries no recording identity.
- **Two graders of one execution are not compared**: `diff` excludes a rule graded
  differently; assessor-agreement statistics are M1.
- A target that writes a redaction placeholder (`[redacted:x]`) into its replies makes them
  ungradable in a regrade — never a pass, but a way to avoid being graded.
- A recording answers a question only when the messages match exactly; whitespace drift is an
  unanswered question (an error). A probe whose kept exchanges pass 64 MiB writes a sidecar
  `grade` refuses.
- `monitor` keeps no exchanges and warns when the profile asks it to; JUnit and SARIF do not
  list `not_recorded` skips, as they list no skip.
- A probe-versus-regrade `diff` also prints the "different targets" note for the
  `recording:` reference beside the shared-execution note.

## Left by F3 (0.34.0)

- **Should a scan that lists no file pass?** An empty directory, or one whose every file is
  excluded, passes today; `test_scanning_an_empty_directory_is_still_a_clean_pass` pins "nothing
  to find is a pass, nothing to look at is not". The false-green hunt on F3 argued for
  `indeterminate`: a CI job pointed at an empty checkout or a failed artifact download passes,
  while the same pickle scanned directly fails. Changing it moves a pinned decision and about
  twenty tests, so it is the owner's call.
- **Trace analysis, `monitor`, `baseline create` and `import-observations` do not run through
  `guardana.core.verify`**, so Python gets typed results for `scan` and `probe` only.
- **A run whose target failed part-way returns no partial result**: `TargetUnavailableError`
  carries no `ScanResult`, as the CLI's exit `4` carries no report.
- **A registry given to `Verifier` whole does not load the profile's `rules.paths`**, which is
  documented; refusing it would need the registry to record which rule directories it loaded.
- **A `SystemPromptPlanter` view must enforce every budget its base target accepted.** A
  third-party view that refuses one after the plain pass sent requests leaves the target
  unclaimed for reuse, and only its meter then stops a second run; the planter contract does
  not say so yet.

## Left by F2 (0.33.0)

- **The five first-run sessions.** The owner recruits five people new to Guardana and runs them
  as `docs/maintainers/first-run-study.md` describes. The F2 row stays in ROADMAP's "Now" table,
  marked study pending, until `scripts/first_run_measure.py` renders five consented rows.
- **The profile has no `schema_version`.** A 0.33 profile using `plugins:` fails loudly on 0.32,
  which is right, but the 1.0 criterion "migrations exercised with older profile documents" needs
  a version to migrate from.
- **Stating `builtins` with a pack co-installed leaves every run `indeterminate`**, and the only
  way out, `fail_on_error: false`, turns off all error gating. A refusal the user stated could be
  a visible coverage note instead of an error.
- **The starter's end-to-end test runs its README through `/bin/sh`**, so it does not run on
  Windows.
- Under a stated trust, `taxonomy` words a refused rule or evaluator entry point as "could not
  load a taxonomy provider"; and `rule test` prints a load failure twice, on stderr and in its
  report.

## Left by run schema 12 (the `left_scan` and `unexamined_component` fixes)

- **Formats the inventory does not list as models**: `.npy`/`.npz` (numpy can hold pickles),
  `.msgpack`, a TensorFlow `.pb`. `saved_model_ops` reads `.pb` but nothing observes it, so a
  shortfall cannot name one; a `.bin` holding GGUF or GGML is a shortfall with no reader.
- **The collector envelope carries no coverage shortfall**, so a run that is `indeterminate`
  for an unread component or a missing dimension reaches the collector without its cause.
- **`left_scan` cannot tell a file deleted from one hidden.** Accepting a deliberate removal
  needs a way that is recorded, not a neutral change kind.

## Left by the codex audit of 0.33.0

Reproduced, deliberately not fixed in this pass, or found while fixing.

- **`guardana-collector status` exits `1` when the database is unreachable** (09.5). `1` means a
  policy failure in `docs/exit-codes.md`; `4` and `5` fit. The collector CLI's codes are a
  documented contract of their own (`docs/usage-collector.md`), so changing them is a decision.
- **`/stats` drops a source whose submissions all fall outside the newest 1,000** from
  `by_source`, critical ones included; only the submissions tile says the window was cut.
- **The pickle allowlist names exact callables**, so a legitimate pickle that rebuilds
  something else (numpy's random state, a scikit-learn estimator) is a finding; widen it only
  with a callable that cannot run code.
- `_pushes_main` in the guard hook reads only the first push in a compound command, and
  `git --help push` now reads as a push (it asks).
- The safetensors reader does not check that `dtype` and `shape` match the offsets or that
  tensor ranges do not overlap; the trace ceilings count characters, not bytes.
- `ci-passed` in `release.yml` was tested against a fake `gh`, not the real API; the first
  release with it is the test.
- An stdio MCP server's `stdin.write` has no deadline; the selector-based read is POSIX-only.
- Agent and tool rules now stop a token-bounded run on any transport whose tool replies carry
  no usage (the LangChain adapter, scripted doubles).

## Accepted designs the roadmap does not carry

`proposed`, written as cycle 5 of the 0.22 extensibility program,
with no code behind it. It is not in the "Now" table of `ROADMAP.md`, so it is neither
scheduled nor rejected — a decision, then either a roadmap row or a `superseded by` line.
(`docs/design/attack-techniques.md`, cycle 4, left this list when `ROADMAP.md` placed it under
"Researched after the foundations", behind repeated trials and judge-error correction —
the 0.26 measurement audit.)

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
  is rule work for the parallel contributor lane.

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
- **CI is pinned to `ubuntu-24.04`.** On `ubuntu-26.04` the images, the clean install and the
  example suites pass, but the `test` job cannot install `postgresql-client-16`, which
  `pg_dump` needs to match the `postgres:16` service. Moving means the PGDG apt repository or
  a newer service and client together, and the collector's documented PostgreSQL version.

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

- **A trace's `document_digest` identifies name and size, not content** — B16, shipped in 0.32.0.
- **Built-in three-outcome fixtures are a ratchet at 12 of 51 rules** — B21, a 1.0 criterion.
- **A strict CI policy is one profile away, not a preset** — B17, shipped in 0.32.0.
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

