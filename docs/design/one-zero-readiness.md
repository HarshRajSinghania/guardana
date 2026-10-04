---
title: "1.0 readiness"
nav_order: 93
summary: "what v0.41 builds so the release candidates carry fixes only: a pinned supported surface with a compatibility policy, a conformance kit and a reference pack, three-outcome fixtures for every built-in, older documents written by the releases that wrote them, exercised runbooks, a protocol the target does not speak read as not applicable, and a delivery a profile can require"
status: accepted
---

# 1.0 readiness

**Status:** accepted, not yet implemented · **Written:** 2026-10-04 · **Serves:** ROADMAP v0.41,
BACKLOG B21, B11 (in part)

## The question

1.0 freezes the supported Python facade, the rule, evaluator and target contracts, the output
contracts, the CLI flags and exit codes, the profile schema and the collector envelope. ROADMAP
lists nine criteria. v0.41 builds every one that code can meet, so the two release candidates
carry fixes only, and reports the ones that wait for people outside the project. It also builds
the decided `not_applicable` reading of a protocol the target does not speak, and four owner
decisions taken on 2026-10-04: principle 3 names a reporter, a profile can require delivery, the
reference webhook ignores proxy variables, and a lock checks who registers an evaluator or a
target.

## Where each criterion stands

| # | Criterion | Before v0.41 | After v0.41 |
|---|---|---|---|
| 1 | "Now" exit criteria and three published measures | first-run measure generated, 0 of 5 sessions; no generator for the other two | generators for all three (decision 13); sessions and teams external |
| 2 | facade, extension and output contracts with a compatibility matrix and a deprecation policy | facade pinned; no matrix; one sentence of policy | met (decisions 8, 9) |
| 3 | conformance kit and an independently installed reference pack, published | kit unnamed, no output checks; no reference pack | kit met; the pack on the GitHub Release, on PyPI once the owner registers its publisher (decisions 10, 11) |
| 4 | three-outcome fixtures for every built-in that can decline | 19 of 58 | met, with any exemption reviewed and listed (decision 12) |
| 5 | envelope versioned apart from the run schema, clients and storage migrated together | separate constant (8 vs 17); server accepts 2–8 | met: published schema, stated window, envelopes written by older releases (decision 7) |
| 6 | migrations exercised with older run, dataset, profile, pack and collector documents | two stored documents from older releases; no profile version | met (decisions 5, 6) |
| 7 | third-party customization and team reproduction recorded with consent | none | external |
| 8 | security and recovery runbooks exercised | backup and restore exercised | collector runbooks exercised by tests; the security runbook's settings checked, its drill the owner's (decision 14) |
| 9 | two release candidates without unplanned public API changes | — | checked by the surface snapshot (decision 8) |

## What exists, so this does not rebuild it

Each decision names the code it changes and what that code does today. `core/` is
`packages/guardana-core/src/guardana/core/`, `cli/` is `packages/guardana-cli/src/guardana/cli/`.

## Decisions

### 1. A rule for a protocol the target does not speak is `not_applicable`

A capability says what a target implements, not what it is: a third-party agent target that
fronts MCP tools may implement only `chat` and `call_tools`. So the target states its protocol,
and the rule's protocol comes from the capabilities it requires.

`core/target/base.py`:

- `WireProtocol(StrEnum)`: `CHAT = "chat"`, `MCP = "mcp"`, `A2A = "a2a"` (the MCP and A2A values
  equal the keys of `Target.protocols()` and `CoverageRecord.protocols`).
- `WIRE_PROTOCOL_OF: Mapping[Capability, WireProtocol]`: `chat`, `call_tools`,
  `plant_system_prompt` → chat; `list_tools`, `inspect_authorization`, `registry_entry` → mcp;
  `inspect_a2a` → a2a. `wire_protocols_of(capabilities) -> frozenset[WireProtocol]`.
- `Target.speaks(self) -> frozenset[WireProtocol] | None`, a concrete method returning `None`
  (unknown). Overridden: `EndpointTarget`, `RecordedTarget`, `_RecordedView` → `{CHAT}`;
  `SeededTarget` → what its endpoint speaks; `McpServerTarget` → `{MCP}`; `A2aAgentTarget` →
  `{A2A}`. Every other `Target` subclass in `packages/*/src` (planter views, wrappers)
  delegates to the target it wraps or keeps `None`. An addition with a default, so `EXTENSION_API_VERSION` stays 2.
- Exported from `guardana.core.target`, not from `guardana.core.__all__`.

`core/runner.py: protocol_refusal(rule, target, capabilities=None) -> SkippedRule | None` (in
`runner.__all__`): with `needed = wire_protocols_of(rule.meta.required_capabilities)` and, when
`target.speaks()` is not `None`, `spoken = target.speaks() | wire_protocols_of(capabilities)`
(the target's declared capabilities, which the callers already hold), a skip only when `needed`
is non-empty, `speaks()` is not `None` and `needed` and `spoken` are disjoint:
`reason=NOT_APPLICABLE`, `missing=()`, detail `"{target.ref} speaks {spoken}, and {rule id}
examines {needed}"` (each sorted, comma-joined). It is asked **first**, before
`safety_refusal`, in `select_rules` and in `core/probe.py: _unplantable_skips` (which builds its
`missing_capability` skips by hand).

Consequences, each stated in the docs:

- `speaks()` returning `None` keeps today's `missing_capability`.
- A protocol whose capability the target declares is spoken: a subclass of `EndpointTarget`
  that adds `list_tools` runs `agent.mcp_server_manifest` rather than skipping it as
  `not_applicable`.
- A capability missing within the protocol stays a gap: a chat endpoint without tools still
  skips `agent.excessive_tool_use`, and an stdio MCP server the authorization rules, as
  `missing_capability`. `probe --preset release` is no longer `indeterminate` because of MCP or
  A2A rules on a chat endpoint, or chat rules on an MCP or A2A target.
- A rule demanded by id and `not_applicable` stays a `demanded_check` shortfall.
- `grade` records MCP and A2A rules as `not_applicable`.
- A recipe lock taken before v0.41 pinned those skips as `missing_capability` or, under
  `--safety passive`, `unsafe_mode`; `recipe run` reports the changed reason as drift and the lock
  is retaken. No schema moves: `not_applicable` exists in run schema 17, recipe lock 2 and
  envelope 8.

### 2. A profile can require delivery

```yaml
delivery:
  required: true
```

`core/profile/loader.py` accepts the top-level key `delivery` with the single key `required`
(a boolean; anything else is a load error in the loader's existing form). `Profile.delivery_required:
bool = False`, added to `_LEFT_OUT` in `core/profile/digest.py` and to the exempt set of
`test_profile_digest.py` with the reason "not part of the verdict", so no profile digest, recipe
lock or run manifest moves. `config explain` shows `"delivery": {"required": …}` after
`"plugins"`.

When it is true, every delivery the run makes must be acknowledged, or the job exits `8`:

- an installed reporter whose status is anything but `delivered`, `not_sent` included; after its
  delivery line: `error: the profile sets delivery.required, and the delivery was {status}`;
- the collector: `submit_safely(...) -> bool` returns whether it acknowledged. The warnings it
  prints become `error: the collector rejected this submission (HTTP {code}): {why} — the profile
  sets delivery.required` and `error: could not submit to reporter: {exc} — the profile sets
  delivery.required`.

Acknowledged means the collector's own answer, not any `2xx`: `_urllib_transport`
(`core/reporter.py`) reads the body and accepts only a JSON object whose `status` is `ok`, as
every collector release answers; anything else is `the response was not a collector
acknowledgement`, a failed delivery with or without the setting. The collector client keeps
honouring proxy variables, like the target's first hop: it is a destination the operator names,
reached through the operator's network; decision 3 is the reference for installed reporters.

Precedence is the existing one for `8` (`_unless_stopped`): it replaces `0`, `1` and `2`, the
verdict line is printed when it does, a stopped run keeps `4`, `6` or `7`, a redaction failure
stays `5`. `RunOutputs.end(verification, *, delivery_required=False, collector_acknowledged:
bool | None = None)` decides it for `scan`, `probe` and `analyze-trace`; `import-observations`
(which exits `2`) ends with `8` the same way; `grade` has no reporter. `monitor` delivers only
alerts: its alert handler counts unacknowledged required deliveries, and `_exit_with_worst`
turns a final `0`, `1` or `2` into `8` when the count is above zero, printing `monitor: {n} alert
deliveries not acknowledged`; the watch never stops for it, and `8` stays out of
`core/monitor.py`'s ranking. Without the key nothing changes. `docs/exit-codes.md` row `8` adds
"or a delivery `delivery.required` asks for was not acknowledged".

### 3. The reference webhook ignores proxy variables

`examples/output_pack/src/acme_outputs/webhook.py` builds its opener with `ProxyHandler({})`
before `_RefuseRedirects`. Its test sets `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy` and
`https_proxy` to a refusing address, unsets `NO_PROXY` and `no_proxy`, and still receives the
delivery; it fails against the current opener. `docs/outputs.md` asks an installed reporter to
do the same and says Guardana cannot enforce it; `docs/threat-model.md` states both stances.

### 4. A lock checks who registers an evaluator or a target

`cli/pack.py: _installed` maps evaluators and targets to their registering distribution
(`registry.evaluator_origin(id).distribution`, `registry.target_origin(cls).distribution`, keyed
as today by id and class `__name__`); `Installed.evaluators` and `.targets` become
`Mapping[str, str | None]`. `_foreign_outputs` becomes `_foreign`, covering evaluator, target,
renderer and reporter: writing refuses with `a pack declares an extension another distribution
registers, so a lock would pin code the pack does not ship: {named}`, and `--check` drops the id
from the pack so it reads `removed` (exit `1`). No lock schema moves. `Registry` refuses a second
distribution registering a target class whose `__name__` another distribution registered, as a
load error naming both, so one origin can no longer overwrite another. The `lock.py` module
docstring and `docs/usage-pack.md` stop saying evaluators and targets are pinned by id only.

### 5. The profile has a schema version

`core/profile/loader.py: PROFILE_SCHEMA_VERSION = 1`. A top-level `schema_version` is checked
before unknown keys are refused: absent means 1; above the current version → `invalid profile
{path}: profile schema {n} was written by a newer Guardana; this build reads schema 1 — upgrade
Guardana`; a boolean or non-integer → `invalid profile {path}: schema_version must be an
integer`; below 1 → `invalid profile {path}: schema_version {n} does not exist`. It is not a
`Profile` field. No writer emits it while it is 1 (a profile written with it would be refused by
0.40); a key added in 1.x raises it. `schemas/profile-v1.schema.json` (hand-written, `$id`
`https://guardana.dev/schemas/profile/v1.schema.json`) describes every key the loader accepts; a
test checks every allowed key set of the loader appears in it and validates every stored
historical profile, the presets and `init`'s template against it. `GATED_BY` gains the constant,
gated by `packages/guardana-core/tests/profile/test_profile_schema_version.py`.

`core/report/baseline.py` refuses a `version` that is a boolean or not an integer (`invalid
baseline {path}: version must be an integer`) or below 1 (`invalid baseline {path}: version {v}
does not exist`); a missing `version` stays 1.

### 6. Older documents come from the releases that wrote them

`scripts/capture_historical_documents.py` (maintainer, network; ops-catalogue row; RELEASING.md
says to run it after a release that changes a document). For every Guardana release on PyPI from
0.2.0 on it runs that release in isolation — `uv run --isolated --no-project --python 3.12
--exclude-newer <newest upload time of that release's distributions plus one minute> --with
guardana-cli==V` — with `env` reduced to `PATH`, `HOME` (a temporary directory), and
`HTTP_PROXY`/`HTTPS_PROXY` at a refusing address with `NO_PROXY=127.0.0.1,localhost`, `cwd` the
temporary directory, and relative paths only. It feeds the release synthetic inputs the script
builds and keeps what the release wrote:

| Kind (directory) | How |
|---|---|
| `run` | `scan` of a synthetic directory holding one finding, `--format json --output` |
| `probe-run` | `probe` of a scripted OpenAI-compatible endpoint the script serves on `127.0.0.1`, where the release has `probe` |
| `envelope` | the `scan` with `--reporter` to a capture server the script serves on `127.0.0.1`, accepting any path |
| `profile` | `guardana init <tmp>/guardana.yaml` |
| `pack-manifest`, `pack-lock` | `new-pack` from 0.26; for 0.20–0.25 a minimal pack the script writes and installs; `pack lock` with the trust flags that release needs |
| `dataset` | format-1 and format-2 files the script builds, passed through that release's `read_dataset`; stored with the oldest release that accepts each ("accepted by", not "written by") |

The command line per release range is an explicit table in the script. A release that lacks a
command or flag (read from its `--help`) is recorded as not producing that kind; a command that
exists and fails stops the script with the release and the output, never a silent gap.

A document is kept under `packages/guardana-core/tests/historical/<kind>/<release>.<ext>` when its
set of key paths differs from the last one kept for that kind, so changes within one schema
version are kept too. `historical/releases.json` records per release: the `--exclude-newer`
time, each kind produced or why not, the schema version read from each document, the collector's
migration count (its `*.up.sql` files), `EXTENSION_API_VERSION` and `OUTPUT_API_VERSION` found by
scanning the installed sources for `^NAME = ` (`null` only when no module defines it),
`Requires-Python` and the `Programming Language :: Python :: 3.x` classifiers. The two older
documents already stored (`tests/saved_runs/`, `tests/pack_manifests/`) stay where they are.

`packages/guardana-core/tests/test_historical_documents.py` (offline):

- no stored document holds an absolute path, a home directory or a CI field (`/Users/`,
  `/home/`, `C:\`, `/private/`, `/tmp/`, `/var/`, a `ci` source other than null);
- every run and probe-run through `load_report`, `guardana run migrate` and `load_verification`
  (a migrated schema-1 run refused, as today); each pair of consecutive runs through `guardana
  diff`: exit in {0, 1, 2}, never 3 or 5, and the migrated-schema note printed when a side was
  migrated;
- every profile, pack manifest, lock and dataset through its loader;
- for each persisted kind (run, envelope, pack manifest, lock, dataset, profile), every version
  its reader accepts has a stored document, or an entry in `NOT_EXERCISED: dict[tuple[str, int],
  str]` with the reason (run schemas no release wrote, the profile's version 1 before any release
  wrote the key).

The envelope documents are exercised by the server (decision 7). The in-code builders
(`tests/_documents.py`) stay: they test single fields; the corpus tests what an older writer
wrote.

### 7. The collector envelope is published, its window stated

`schemas/collector-envelope-v8.schema.json`, hand-written in the style of the run schemas, `$id`
`https://guardana.dev/schemas/collector-envelope/v8.schema.json` (as `build_site.py` requires).
A test validates the current writer's envelope and every stored v8 envelope against it and checks
that every property `Submission` and its nested models accept appears in it.
`packages/guardana-server/tests/test_historical_envelopes.py` (PostgreSQL, refuses to skip in
CI) migrates a database, POSTs every stored envelope of every version and reads each back through
the scoped store, the stored version equal to the one sent.

The window, in `docs/architecture.md` and `docs/compatibility.md`: every envelope change raises
its version; a collector accepts every version from 2 up to its own; an agent newer than its
collector is refused with `422` naming the versions the collector speaks, so collectors are
upgraded before agents; dropping a version is a major release. The `app.py` comment that the
envelope "stays at v5" goes. The envelope stays at 8: shortfalls, judge usage and measurements
are M3's, added in 1.x by raising the version.

### 8. The supported surface is a generated snapshot

`scripts/api_surface.py` writes `docs/generated/api-surface.json`; `generate_docs.py` runs it,
so `--check` and pytest gate drift. Built from source with `ast` (no `from __future__` in the
code, so `inspect` would evaluate annotations whose repr differs between Python versions): each
name is mapped to the module defining it, and annotations are `ast.unparse` text. The output is
identical on Python 3.11, 3.12 and 3.13.

| Surface | Recorded |
|---|---|
| facade: `guardana.core.verify.__all__`, `guardana.core.doubles.__all__` | per name: kind; function and method parameters (name, kind, default present or not, annotation text) and return annotation; class public methods; dataclass fields; enum members |
| extension: `guardana.core.__all__` except `Runner` (internal, as `docs/python-api.md` says), `guardana.core.target.protocols.__all__`, `guardana.core.target.WireProtocol`, `guardana.core.source` (`PythonSource`, `UnreadSource`, which `FileReader` returns), `guardana.core.report.shortfall` (`CoverageShortfall`, `ShortfallKind`), `guardana.core.rule.fixture` (`RuleFixture`, `DeclaredFixture`, `FixtureOutcome`, `DEMANDED_OUTCOMES`, `materialise`) | as above |
| outputs: `guardana.core.output.__all__` | as above |
| kit: `guardana.testing.__all__`, `guardana.core.testing.__all__` | as above |
| constants: entry-point groups, `EXTENSION_API_VERSION`, `SUPPORTED_EXTENSION_API_VERSIONS`, `OUTPUT_API_VERSION`, `SUPPORTED_OUTPUT_API_VERSIONS`, every persisted version constant | ints and strings by value, sets as sorted lists |
| CLI | per command path: parameter name, `opts`, `secondary_opts`, required, flag, multiple, hidden, default present or not (from `typer.main.get_command`); no help text |
| `ExitCode` members, target locator schemes, `action.yml` inputs, `GUARDANA_*` environment variable names read in `packages/*/src` | names and values |

The trace format is versioned by its own JSON schema and is not repeated here. For a release
candidate, `release.py` refuses when `docs/generated/api-surface.json` differs from the previous
tag's and `[Unreleased]` has no "Changed", "Deprecated" or "Removed" section.

Removed, each deprecated for at least one minor release: `is_local_address` (and its export and
test), and `check_pack`/`check_packs` given a flat set, which now raise `TypeError("check_pack
and check_packs take a Registered; a flat set of ids is no longer accepted")`. `--no-plugins`
stays, deprecated, until 2.0.

### 9. The compatibility page and the deprecation policy

`docs/compatibility.md` (written by hand, `nav_order` 57) holds the policy and links
`docs/generated/compatibility-matrix.md` (rendered by `generate_docs.py` from
`historical/releases.json` and the current constants: one row per minor release from its newest
patch, plus the current tree; columns Python, run schema, envelope, pack manifest, lock,
profile, extension API, output API). The policy, from 1.0:

- the surface of decision 8 changes incompatibly only in a major release;
- a name to be removed is deprecated first — a `DeprecationWarning` where Python can raise one,
  a "Deprecated" changelog entry naming the replacement — for at least one minor release, and
  removed only in the next major;
- every 1.x reads every document an earlier release wrote and writes the current version, with
  one stated exception: `load_verification` refuses a schema-1 run, which recorded no gate
  (`load_report` and `run migrate` read it);
- the envelope window of decision 7;
- 1.x supports extension API 2 and output API 1; a new API version is opt-in through a pack's
  range, and support for one is dropped only in a major;
- a Python version is supported until its upstream end of life; dropping one is announced one
  minor release ahead;
- until 1.0, a breaking change lands in a minor and is announced under "Changed — breaking".

`docs/python-api.md` points at the page; `docs/product-status.md`, `README.md` and `FEATURES.md`
stop calling the extension API unstable; `SECURITY.md` "Supported versions" links the policy.

### 10. The conformance kit checks outputs, and has a page

`guardana.core.testing.sample_verifications() -> tuple[Verification, ...]`: real engine output,
produced by `Verifier` over kit targets — a passed and a failed scan of `files_target` trees, an
indeterminate scan of an empty tree (`empty_target`), a probe of a scripted endpoint stopped by
`max_requests`, and a run with no rule run. `guardana.testing` adds:

- `assert_renderer_conforms(spec)`: `name` valid and unreserved, `spec.name` equal to it, and
  `render` returning non-empty `str` for every sample through the same redaction boundary
  `--format` uses;
- `assert_reporter_conforms(spec, *, delivered: str, rejected: str, unreachable: str)`: three
  locators the caller supplies; `prepare` sends nothing (`socket.socket.connect`, `connect_ex`,
  `socket.create_connection` and `socket.getaddrinfo` refused for its duration — subprocesses and
  C extensions are not covered, and the page says so); `destination` a `str`; `sent_secrets()` a
  tuple of `str`; through `guardana.core.output.deliver`, each locator yields exactly its status
  for every sample, and `unknown` fails with its detail;
- both raise `OutputContractError(AssertionError)`;
- `guardana.core.testing.receiver()`: a context manager serving `127.0.0.1` and yielding an
  accepting URL, a refusing URL (`403`) and a closed-port URL, for HTTP reporters.

`docs/conformance-kit.md` lists the kit — `guardana rule test` and `verify_rule`,
`assert_target_conforms`, the scripted MCP and A2A servers, `files_target` and the trace and
transport builders, the output checks — with what each proves and does not. `output_pack`'s suite
uses the output checks.

### 11. The reference pack

`examples/reference_pack`: distribution `guardana-reference-pack`, its own version `0.1.0`
(bumped by hand when its content changes, like any third-party pack), `guardana-core>=0.41` with
no upper bound, so its manifest's `extension_api` and `output_api` ranges decide compatibility.
Module `guardana_reference_pack`, ids under `reference.`, output names `reference-summary` and
`reference-file`. It provides one YAML rule and one Python rule, each with finding, clean and
inconclusive fixtures; one evaluator; one target passing `assert_target_conforms`; one taxonomy
catalogue; the format `reference-summary` (a Markdown summary of the run); the reporter
`reference-file` (`reference-file://<dir>`: `prepare` only validates the locator; `deliver`
writes `<dir>/guardana-<run_id>.md` through a temporary file, `fsync` and `os.replace`, then
returns `delivered`; a missing directory is `unreachable`, an `OSError` while writing
`rejected`); a schema-3 manifest; a committed `guardana-lock.yaml`.

Its suite, installed in isolation like the other examples (`ci_local.sh`, `ci.yml`), uses only
the conformance kit and the surface of decision 8 — a test walks its sources' imports and refuses
any `guardana.*` name outside `docs/generated/api-surface.json` — and runs `guardana rule test
'reference.*'`, the target and output checks, `pack validate`, `pack lock --check`, and a `scan`
with `--plugins allowlist --allow-plugin guardana-reference-pack --format reference-summary
--reporter reference-file://…`. `clean_install_check.py` installs it beside the five and runs
`pack validate` and `rule test` on it.

`release.yml` builds it into `dist-reference/`, attests it and uploads it to the GitHub Release
in its own job `reference-pack` (`needs: publish`): the pack's own build, attestation and PyPI
upload run in jobs after the main publish, while CI and the release's clean-install check build
and check the pack before anything is published. A separate job `publish-reference-pack` (`needs:
reference-pack`, environment `pypi`,
`skip-existing: true`) runs only when the repository variable `REFERENCE_PACK_PYPI` is `true`,
which the owner sets after registering the pending trusted publisher for
`guardana-reference-pack`; the GitHub Release and the images never wait on it. Criterion 3 is
reported met only once the pack is on PyPI. `custom_rule` and `output_pack` stay as teaching
examples.

### 12. Three-outcome fixtures for every built-in

Prerequisite in `core/rule/verify.py`: a fixture whose target is a `FileReader` reports its
`unread_sources()` as a decline, as the runner turns them into errors, so an artifact the rule
could not read never classifies as clean. `guardana.core.testing.files_target(files:
Mapping[str, bytes | str]) -> ArtifactTarget` (re-exported from `guardana.core.testing`): an
`ArtifactTarget` over a fresh temporary directory holding `files`, removed by `weakref.finalize`
when the target is collected.

The 39 unsampled rules declare a finding, a clean and an inconclusive fixture each, built in
code: artifact rules through `files_target`, trace rules through `TraceTarget(Trace(...))`, MCP
rules through `rules/mcp/_samples.py`, chat rules (`output.secrets`, `agent.excessive_tool_use`)
through `EndpointTarget("http://fixture.invalid", "fixture", transport=…)` with the scripted
transports, as `core/rule/_fixture_schema.py` does. An inconclusive fixture shows the rule
declining something it could not establish, never a fixture shaped to move the counter.

About half of these rules have no decline path today. Each gains one where its claim can be
prevented — an unread or over-budget input, an unparseable document, a record the trace marks
withheld — or an entry in `_EXEMPT: dict[str, str]` in the ratchet test with the reason it can
never be prevented, reviewed. A rule that gains a decline path changes behaviour (a run may be
`inconclusive` where it was clean); the changelog names each under "Changed". The ratchet pins
`len(provide_rules()) - len(_EXEMPT)`; the count is generated into
`docs/generated/rule-summary.md` and `docs/usage-rule-test.md` links it instead of stating it.
`guardana rule test --write-corpus` over the new fixtures exits as without the flag and counts
artifact and trace samples under its existing "no scripted reply" reason.

### 13. Measures 2 and 3 get generators

`scripts/adopter_measure.py` mirrors `first_run_measure.py`. `row RUN.json --team T1 --consent
yes` prints one row of counts from a saved run, never its content, for
`docs/maintainers/adopter-runs.csv` (columns `team, run_id, guardana, schema_version,
rules_selected, rules_not_applicable, rules_attempted, rules_decided, consent_to_publish`; teams
`T1`, `T2`; a row without consent, or a second row with the same `run_id`, refused). It refuses a
run older than schema 14, one with `stopped_by` set (rules that never started are not recorded),
one without a recipe, one whose `recipe.kind` is not `application`, whose `recipe.lock_digest` is
null, or that records an error naming no rule (its rules would read as decided). From the run:

- selected = rules in `rules_run`, in `rules_skipped`, and named by an error before they ran;
  not applicable = skips with reason `not_applicable`; attempted = rules in `rules_run` or named
  by an error; decided = rules in `rules_run` with no error and no unverified entry naming them
  (a finding or clean);
- **coverage of the real application** = attempted ÷ (selected − not applicable);
- **supported-verdict share** = decided ÷ attempted, over these locked application runs, which are
  the comparable ones.

`docs/generated/application-measures.md` (rendered by `generate_docs.py`) says "not measured"
until two teams have rows.

### 14. Runbooks, and what was exercised

`docs/deployment.md` gains key rotation (issue, deploy, revoke, confirm the old key answers
`401`) and names the test that exercises each runbook: backup and restore
(`test_backup_restore.py`), rollback and forward (`test_migrations.py`), project deletion
(`test_retention_and_deletion.py`), and two new PostgreSQL tests in
`packages/guardana-server/tests/`: `test_upgrade_from_previous_release.py` (migrate to the
migration count the oldest stored release shipped, migrate forward, ingest every stored envelope,
read back) and `test_key_rotation.py`.

`docs/maintainers/security-runbook.md`: a vulnerability report (private advisory, fix on a private
fork, release, advisory published with the fixed version), a compromised or broken release (yank
on PyPI by the owner, delete the ghcr version, move `vX.Y` back, advisory, changelog), a leaked
collector key or database credential. `scripts/check_repo_settings.py` reads, through `gh api`,
the settings the runbook relies on — private vulnerability reporting, the tag ruleset, the
`pypi` environment's required approval, the release workflow's CI gate, the ghcr packages — and
prints each PRESENT, ABSENT or NOT CHECKED (no `gh`, no auth, or a `403`/`404`); exit `0` all
present, `1` any absent, `2` any not checked. `docs/maintainers/drills.md` records each drill:
date, runbook, steps exercised, steps not exercised. Reading settings is not a drill: the
security runbook counts as exercised once the owner records one.

### 15. Principle 3 names a reporter

CLAUDE.md principle 3 reads: "Offline, no account, always: traffic goes only to destinations the
run names — the target under test, a judge or guard the profile configures, the authorization
metadata the target itself advertises, and a collector or reporter `--reporter` names; the
collector is optional in every direction." `docs/maintainers/lessons.md`, `docs/safe-testing.md`,
`CONTRIBUTING.md`, `.claude/rules/server.md` and `.claude/skills/stack/SKILL.md` follow.

## What stays outside v0.41

- Five first-run sessions (F2), two independent teams (F6), a recorded third-party customization.
- Envelope shortfalls, judge usage and measurements: M3, by raising the envelope version.
- An evaluator conformance check: an evaluator is exercised through its rules' fixtures.
- The reference pack on PyPI: the owner's pending publisher.
- The security runbook drill: the owner's.

## Options that lost

- **Protocol read from capabilities alone**: a target implementing only chat while fronting MCP
  would turn a real gap into `not_applicable`, and that reading would freeze at 1.0.
- **A new skip reason `other_protocol`**: run schema 18, recipe lock 3 and an envelope change for
  a distinction no gate uses.
- **A protocol field on `RuleMeta`**: every pack would have to learn it; the capability a rule
  requires already names its protocol.
- **Delivery under `fail_on:`**: `fail_on` decides the verdict; a delivery comes after it.
- **`not_sent` exempt from a required delivery**: a reporter can return it, and the job would pass
  with nothing delivered.
- **Envelope v9 before 1.0**: freezing a measurement block M3 has not designed.
- **Older documents rebuilt in code only, or captured from 0.12.0**: the first cannot catch a
  field an older writer emitted; the second misses envelopes 2–6 and run schema 1.
- **One document per schema version**: loses changes inside one version (envelope 8 spans
  0.13–0.40).
- **Merging `custom_rule` and `output_pack` into the reference pack**: renames ids the extension
  guides teach with; a separate small pack on the frozen surface costs less.
- **The reference pack versioned with Guardana**: every bump would move its lock and its build
  scripts; a third-party pack has its own version.
- **A script that prints EXERCISED for a setting it read**: a setting present is not a runbook
  exercised.
