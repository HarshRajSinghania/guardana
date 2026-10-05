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
| B10 | Calibration identity supports several rubric versions and verdict IDs | M1 | Match the actual grader identity. Kept for M1 in 0.30.0: re-keying the store is calibration schema 3 and F5 defines grading identity; the decline already no longer promises an impossible rerun. |
| B11 | Collector measurement envelope and storage | M3 | The envelope is versioned apart from the run schema and published as a JSON schema (0.41.0); a later version carries measurements, denominator, trials, uncertainty, missingness, coverage shortfalls and judge usage, with tenant isolation. |
| B12 | Non-executing declarative packs | parallel lane, decided before F2 | Keep local ID validation. Decide whether a pack can ship checks that execute no Python. The public extension-ID service is dropped (direction audit). |
| B13 | Public contributor tasks and adoption checks | F2/F6 | Prepare small issue descriptions from B04/B06/B08; record five developer sessions and two team integrations with consent. Publishing issues is separate maintainer work. |
| B20 | Live retrieval pilot | F6 | One retrieval target catches a poisoned document and a tenant-filter failure without an uncontrolled side effect. The checks and a reference application shipped in 0.37.0; open until a team's own retrieval target has run them. |
| B22 | A time bound for `regex` | Later | A crafted reply can make an author's backtracking pattern run for a very long time; the 65,536-character bound limits input, not time. Any fix that adds a dependency needs principle 6's justification. |

B21 shipped in 0.41.0 (every built-in rule proves all three outcomes). B06 shipped in 0.40.0 (ROADMAP F4). B19 shipped in 0.39.0 (ROADMAP F7). B08 shipped in 0.36.0 (ROADMAP F6, first half); the F6 second half shipped in 0.37.0. B07 shipped in 0.35.0 (ROADMAP F5). B15, B16, B17 and B18 shipped in 0.32.0 (ROADMAP Q1). B01, B02, B03, B09 and B14 shipped in 0.30.0 (ROADMAP F1). The lockfile/gitleaks and
script-parser items shipped in 0.31.0; ONNX metadata grading, ATLAS provenance and the other
items remain open below. Before closing any item, rerun its reproduction.

## Found while building Q1 (0.32.0)

Found by the pre-ship review and the false-green hunt on 2026-09-30; each was reproduced.

- **A trace reads as `content_prefix` when `MAX_SPANS` stops a read of a file the buffer
  already held whole.** Conservative: `content` is claimed only after the raw read returned
  end of file.
- **Observation dialect detection reads the document a second time**, bounded like the
  first read.

## Found while preparing the OpenSSF badge (after 0.32.0)

A code sweep for the `know_common_errors` attestation on 2026-09-30. The first three were
reproduced; the rest are the sweep's reading with its anchors, not yet reproduced.

- A symlinked file inside a scanned directory is read even when it points outside the root
  (bounded by the reader caps; `open_regular` refuses FIFOs and devices). Refusing it would leave
  every Hugging Face snapshot (`snapshots/<rev>/x -> ../../blobs/<sha>`) `indeterminate`; it needs
  a design that names the directories a link may lead to.
- The dashboard cookie is `Secure` only when the app itself sees `https`; behind a proxy that
  uvicorn does not trust, it never does. `docs/deployment.md` names `FORWARDED_ALLOW_IPS`; a
  setting of Guardana's own would add an environment variable to the supported surface.
- `llm_judge` places the transcript into its prompt unfenced (`core/evaluator/llm_judge.py:26`).

## From the codex review of 0.36.0

A whole-codebase and documentation review (GPT through codex, read-only, 2026-10-02). Every
finding was reproduced or read in the code before anything changed; these were confirmed and
left for the owner, or are design gaps already documented elsewhere.

- **`MonitorSummary.exit_code` is `0` after cycles that could not be sampled**; the `monitor`
  command exits `4`. The engine owns result codes only, and the field now says so.
- **`assert_target_conforms` passes a file target with no files**: it samples the files the
  target lists. The extension guide's example now points at a directory holding one; failing an
  empty target would change the kit for every pack test.
- `pickle_opcode` still decompresses each non-pickle member up to 64 MiB before it stops
  parsing; reading a short probe first would cut that cost. A raw `.pkl` has no opcode budget,
  but its cost grows with its own size.
- Documented gaps it re-found: third-party reporters cannot be selected (F4), the `Capability`
  set is closed (`target/base.py`), and `Verifier` does not run trace analysis
  (`docs/python-api.md`).

## Left by 1.0 readiness (0.41.0)

- **Within a protocol, a missing capability stays a gap.** A chat endpoint without tools or
  without system-prompt planting, and any target without seeded fixtures, still leaves
  `probe --preset release` `indeterminate`; only a protocol the target does not speak is
  `not_applicable`. The seeded rules require `seeded_data` alone, which names no protocol.
- **Some inconclusive samples write 16 or 64 MiB files** to pass a rule's own read bound
  (`prompt.mcp_tool_poisoning`, `supply_chain.remote_code_config`, `saved_model_ops`,
  `hardcoded_secret`, `provenance`), each time the samples are built; a rule's bound is its own
  constant. Samples the target declines use `files_target(source_read_limit=…)` and stay small.
  `files_target` is supported surface, so the fix needs a seam on the rule's bound, after 1.0.
- **The reference pack is not on PyPI** until the owner registers its pending trusted publisher
  and sets `REFERENCE_PACK_PYPI`; it is attached to the GitHub Release.
- **The security runbook is not exercised**: `check_repo_settings.py` reads the settings it
  relies on, and `docs/maintainers/drills.md` records no drill. The two ghcr packages read as
  NOT CHECKED without a `read:packages` token.
- **The tag ruleset does not restrict updates**: "Protect release tags" has `creation`,
  `deletion` and `non_fast_forward`, so a write user can move a `v*` tag forward to a descendant
  commit; `check_repo_settings.py` reports it ABSENT until the owner enables "Restrict updates".
  GitHub documents no built-in `RepositoryRole` ids (github/rest-api-description#4406); the live
  ruleset's bypass actor is `5` (Admin), and Maintain (2) is unconfirmed.
- **Before 1.0.0:** `RELEASING.md` says Guardana "is **pre-1.0**", which no gate rewrites
  or checks at the final release.
- **An exempt console-script wrapper's content is never hashed**, so an edited
  `bin/<declared script>` pins the same as the generated one; the exemption is sound only for an
  unmodified wrapper.
- **The largest classes carry several reasons to change**: `_Probe` (MCP authorization,
  discovery and tasks), `Verifier` (running a check and assembling its result), then `Registry`
  and `Runner`. Split them behind behaviour tests, without a line-count target and without moving
  the supported surface; after 1.0, since the release candidates take fixes only.

## Left by the export and webhook release (0.40.0)

- **`guardana grade` warns when a sidecar's saved run records another digest.**
  `docs/design/regrading-stored-exchanges.md` specifies refusal; the exit change waits for 1.x.
- **A probe keeps its saved run when its sidecar cannot be written.** It exits `3`, while the
  run still records the digest of exchanges that were not written.
- **Sidecar mismatch:** `grade`, `plan grade` and `recipe run` warn only on stderr; the
  saved report records the recording's own origin and digest but not the disagreement
  with the run beside it.
- **Unwritable built-in report:** An earlier report and its sidecar remain at `--output`;
  removing them needs a way to distinguish an earlier run from a user-protected file,
  such as a read-only one.
- **Failed installed format or redaction:** Removes whatever file is at `--output`, including
  a read-only or non-run file, and says it held an earlier run.
- **Profile files:** Files named by `contracts:`, `rules.paths`, `calibrations:` or an adapter
  are not checked against `--output`; only files named on the command line are.
- **Probe inputs:** `probe` checks none of `--profile`, `--rules`, `--system-prompt-file`,
  `--fixtures`, `--mcp-pin` or `--mcp-registry-entry` against `--output`.
- **Baseline output:** `scan --write-baseline` writes nothing at `--output` and leaves an
  earlier run there with exit `0`; neither path is checked against the other, the sidecar
  path or the inputs.
- **Digest sidecar:** A run migrated to another `--output` records an exchanges digest whose
  sidecar stays beside the original. The same holds for a current-schema run copied there.
- **Profile inputs:** `recipe run` checks only files the recipe itself names against its
  `output.directory`, not files its profile names (`rules.paths`, `calibrations:`,
  `contracts:`). Only files sharing a name the artifact's marker lists can be lost,
  since `claim` refuses any other file.
- **Unreadable recipe:** An unreadable recipe marks its earlier artifact refused without
  knowing its inputs. If it names that artifact's own `junit.xml` or `report.txt`, that
  file is rewritten.
- **Migrate file metadata:** `run migrate` writes through a temporary file and a rename.
  This breaks a hard link to the old file and keeps only its mode, not its owner, ACLs or
  extended attributes. A writable file in a directory this process cannot write is now
  refused.
- **Self-input refusal:** When a recipe names the artifact's own `guardana-artifact.json` as an
  input, the in-place refusal touches nothing. The earlier marker and `junit.xml` stay green;
  only exit code `3` reports the refusal.
- **An installed format's text written with `newline=""` is not tested on Windows.**

## Left by protocol conformance (0.39.0)

- **A2A HTTP+JSON and gRPC bindings** are not spoken, and an interface on another origin
  is not followed; one binding has one fixture.
- **Agent-card signatures are not verified**: JWS over RFC 8785 needs a JOSE or crypto
  dependency (principle 6). Decided: an optional extra after 1.0, never a dependency of
  `guardana-core`.
- **MCP Server Cards** (`.well-known/mcp.json`) are not read (an open proposal in neither
  revision); **`cacheScope` on prompt and resource lists** is not graded (Guardana sends
  neither request); **older handshake revisions** (`2025-06-18`, `2025-03-26`) are reported
  as sharing no revision.
- **A legacy session re-opened once** adds an `initialize` and its announcement that the
  rules' `estimated_requests` do not count, so `plan probe --mcp` can price a run below what it
  sends; the meter still holds `--max-requests`.
- **The `conformance` dependency group** (`mcp`, `a2a-sdk`) is pinned exactly: a Dependabot
  bump of either moves what the conformance suite means and is read as a test change.

## Left by the guarded-application release (0.38.0)

- **`monitor` builds a fresh meter per cycle**, so `max_requests_per_minute` is not held across
  cycles closer together than `60 / N` seconds; the usage page says so.
- **A judge failing mid-run keeps no partial run**: it exits `4` with nothing saved.
- **Declines exist on the adapter only**; the built-in provider transports have no
  `declines:`, `retry_statuses:` or `metadata_paths:`.
- **`recipe lock` plans with `build_plan`**, not with the probe's canary passes, so how the
  lock prices a canary pass can differ from the run.
- **Source pins:** a `.pyc` under `__pycache__/` is left out, so an unchecked-hash or
  timestamp-matching bytecode file can run code the pin does not cover; a distribution installed
  with `pip --target`, on `PYTHONPATH` or by a system package without a `RECORD` is always
  unpinned (fail-closed, noisy); `open_regular` checks a file's type before it opens it, so a file
  swapped for a FIFO between the two can still block.
- **Withheld values:** a placeholder key of four or more characters (`EMPTY`, `ollama`) is
  withheld wherever it appears, which can mark kept replies altered so `grade` skips them;
  `target`'s locator failure is quoted under the `redacted` policy rather than the
  profile's; `--write-mcp-pin` keys tools by name, so a token a server puts in a tool name
  reaches the pin file.
- **A first monitor cycle its target stopped** alerts on what it proved and still exits `4`,
  the CLI's code for a target failure, rather than `1`.

## Left by F6, second half (0.37.0)

- **The secret and MCP-manifest scans read 16 MiB of a file**; a larger `tokenizer.json` is
  unverified. Streaming the secret scan and sniffing a manifest by structure would cover it;
  a name-based exemption would not.
- **Third-party evaluators cannot be configured from the profile** (`evaluator_config:`), and a
  dataset case cannot set request fields (a language per case) a target or adapter sends.
- **Traces:** a standalone `trace validate` for producers that cannot import Guardana; a
  `decision_required` contract kind; a per-assertion `when_available` for contracts a producer
  cannot yet serve; the reason of a coverage shortfall is withheld under `metadata_only`
  although it holds no evidence.
- **Regression cases:** a dataset shared by two suites can make the other one fail to load after
  `case add`; a judge-graded case cannot be proven (`rule test` sends nothing); a case is not
  reproduced against the subject before it is written.
- **Fixtures and doubles:** the doubles' trace is graded by a second command, not inside
  `recipe run`; `monitor` takes no `--fixtures`; `fixtures render` writes no records file for a
  port of the doubles outside Python; which `${VAR}` header authenticates is not declared, so
  every one counts as distinguishing two tenants.
- **Per-minor upgrade notes**: what to regenerate (locks, baselines, calibrations) and which
  keys moved, beside the changelog.
- **A native trace still defaults a few absent fields**: a memory operation without `action`
  reads as a read, a consent without `granted` as not granted, a delegation without `actor` or
  `boundary` as unknown; `minLength` is not enforced and an unparseable timestamp reads as
  absent.

## Left by F6, first half (0.36.0)

- **A recording's origin** (`stopped_by`, planned rules) is declared, not checked against the
  origin's `run.json`.
- **Recipes name a connection, a recording or an installed target**, but no MCP subject, no
  `--reporter`, and no SARIF in the artifact (SARIF carries no subject label yet).

## Left by F5 (0.35.0)

- **Only an endpoint built on `EndpointTarget` keeps exchanges, and only its plain pass.** Another
  pack target would need a protocol to keep them, a subclass whose `chat` does not call the base
  keeps none, and canary passes and tool offers are not kept, so canary and agent rules cannot
  be graded again.
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

- **Trace analysis, `monitor`, `baseline create` and `import-observations` do not run through
  `guardana.core.verify`**, so Python gets typed results for `scan` and `probe` only.
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

- **`/stats` drops a source whose submissions all fall outside the newest 1,000** from
  `by_source`, critical ones included; only the submissions tile says the window was cut.
- **The pickle allowlist names exact callables**, so a legitimate pickle that rebuilds
  something else (numpy's random state, a scikit-learn estimator) is a finding; widen it only
  with a callable that cannot run code.
- `_pushes_main` in the guard hook reads only the first push in a compound command, and
  `git --help push` now reads as a push (it asks).
- The safetensors reader does not check that `dtype` and `shape` match the offsets or that
  tensor ranges do not overlap; the trace ceilings count characters, not bytes.
- An stdio MCP server's `stdin.write` has no deadline; the selector-based read is POSIX-only.
- Agent and tool rules stop a token-bounded run on any transport whose tool replies carry no
  usage (scripted doubles; LangChain carries it since 0.36.0).

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
  two on separate tracks: format releases by semantic version (`v5.6.0`, 2026-05-04) and monthly
  content releases as `YYYY.MM` (`v2026.09`, 2026-09-15), the content version stored in the
  collection object (atlas-data releases page, read 2026-10-04). The
  provenance field is the first fix; mapping the agent-facing techniques the newest releases add
  is rule work for the parallel contributor lane.

## ONNX metadata grading

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
- For the `control` repository, not this one: `control.guardana.dev` states the boundary
  guardana.dev now states — Guardana measures before and between releases, Control decides tool
  calls at run time, the kind of control the OWASP Agent Control Standard describes.
- For the `control` repository, not this one: a site generator for `control.guardana.dev`
  that vendors `site/assets/brand/v1/` and checks it against its `SHA256SUMS`; and its
  `docs/foundation/12_INTEGRATION_WITH_GUARDANA.md` and product spec still describe a
  coupling its ADR-0024 refuses.

