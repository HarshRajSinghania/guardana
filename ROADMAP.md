# Guardana roadmap

Guardana should give an individual developer a useful result on the first run,
then let a team turn the same evidence into its own tests, gates, reports and
tools without forking the engine. The product is an offline-first verification
framework with a usable CLI and optional collection, outside the production
request path.

This is the ordered plan toward 1.0, not a release promise. [FEATURES.md](FEATURES.md)
describes shipped behavior; [the generated rule summary](docs/generated/rule-summary.md)
and [rule catalog](docs/generated/rule-catalog.md) are the coverage source of truth;
[Product status](docs/product-status.md) states limits; [CHANGELOG.md](CHANGELOG.md)
records releases.

## Product constraints

1. An unavailable check, ungraded case, partial run or invalid comparison never becomes a pass.
2. Offline scanning stays offline; target and judge traffic is explicit and bounded.
3. Engine capabilities and built-in checks remain open source, without an account.
4. Application-specific checks and output destinations work without an engine fork.
5. Public data formats are versioned, with tested readers and migrations.
6. Findings, quality measurements, errors and missing evidence remain separate.
7. Results explain their source, coverage, execution cost and comparability.
8. The collector is optional; local files and Python deliver independent value.

## What ships today (1.0.0rc1)

The first release candidate, 1.0.0rc1, scans offline artifacts; probes endpoints, MCP servers in `2025-11-25` and `2026-07-28`, and A2A v1 agents; analyzes traces; compares regressions; gates policy and baselines; supports extension packs; and offers an optional authenticated PostgreSQL collector. MCP and A2A probes are checked against servers built on their protocol owners' SDKs. MCP checks cover task listings and an operator-supplied registry entry; A2A checks cover cards, callers without a credential and one caller's view of another's tasks. `guardana.core.verify` returns the failed, indeterminate and stopped outcomes of `guardana scan` and `guardana probe` as typed data. Empty scans, unreadable components and ungraded rules cause shortfalls; part-way target failures save runs, including on MCP and A2A. A rule for a protocol the target does not speak is `not_applicable`; an absent capability within that protocol remains a gap, and `not_offered` still records a surface absent when a rule runs. A rule demanded by id remains a `demanded_check` shortfall.

Adapters identify guard declines, copy bounded metadata and set retry statuses; built-in provider transports do not carry those adapter fields. Evaluators grade declines or leave them inconclusive, and recordings retain them for `guardana grade`. Rate budgets pace targets and judges. Suites grade versioned datasets and gate pass rates; plans and runs track judge calls, budgets and stopped suites. Judge-graded suites and judge-error correction remain experimental: matching calibrations correct trial and suite rates, and reports flag their absence. Mid-run judge failures keep no partial run. Agent checks catch cross-turn canary leaks, require payload proof and argument allowlists, and refuse truncated runs. Runs and messages hide credentials. Human, JSON, SARIF and JUnit agree on nonpassing runs. `--preset release` rejects skipped or ungraded selected checks, and `plan` rejects them before sending.

Commands start with built-in plugin trust. `guardana doctor` lists installed extensions, formats and reporters without importing them. Installed `--format` formats and `--reporter` reporters import only when named; unknown, duplicate or trust-refused outputs exit `3` before sending. Outputs receive saved run data; reporters never receive kept exchanges and print a stable `delivery:` line. Failed installed outputs exit `8` with the verdict printed. `delivery: {required: true}` also requires acknowledgements from every reporter and collector delivery; the collector accepts only a JSON object with `status` equal to `ok`. `examples/output_pack` provides CSV and Standard Webhooks output, with its webhook ignoring `HTTP_PROXY` and `HTTPS_PROXY`. `guardana.core.verify.load_verification` reads saved runs for export without sending.

`guardana init --starter` supplies an offline first run. `guardana grade` grades earlier answers or exchanges kept by `guardana probe --keep-exchanges` without a target request. `guardana recipe lock` pins checks and targets; `guardana recipe run` refuses drift before sending. Endpoints and judges share connection settings. `guardana case add` creates proven regression pairs from kept failures, and selected suites regrade them. Fixtures declare tenants, documents, records and tools; `guardana fixtures render` prepares documents and doubles record tool effects. `probe --fixtures FILE` and `plan probe --fixtures FILE` check tenant boundaries and poisoned documents; unreachable controls are indeterminate. Runs record fixtures and deterministic evaluators; `guardana diff` refuses incompatible fixtures. Native traces enforce schema, rule refusal markers cover other languages, and empty replies cannot pass.

Profiles have a versioned schema, all 58 built-in rules have finding, clean and inconclusive samples, and the conformance kit checks outputs. Historical documents from 0.2.0 through 0.41.0 are read by current tests. The collector envelope is published and versioned independently; recovery runbooks are exercised by tests, while the security runbook drill is not recorded. The supported surface, compatibility matrix and 1.0 deprecation policy are published. `guardana-reference-pack` 0.1.0 is attached to the GitHub Release and is not on PyPI. Application coverage and supported-verdict share remain "not measured" until two independent teams have rows. See [FEATURES.md](FEATURES.md) and [Product status](docs/product-status.md).

## First goal: 1.0

1.0 is the first release whose public surface stays stable: the supported Python facade, the
rule, evaluator and target contracts, the output contracts, the CLI flags and exit codes, the
profile schema and the collector envelope. From 1.0 on, a breaking change needs a major
version ([versioning](docs/compatibility.md#versioning)).

The readiness release and first release candidate have shipped. F2's five first-run sessions and F6's two independent teams remain alongside the second candidate and stable release:

| Target | Delivers |
|---|---|
| **v1.0.0rc2** | fixes only; ships once the fixes found in rc1 are in and the gate is green |
| **v1.0.0** | first stable release when a release candidate has drawn no new defect reports for a while and the 1.0 criteria below hold |

The target is the first quarter of 2027. External evidence sets that date more than the code
does: five first-run users after F2, two independent teams in F6 and a recorded third-party
customization. A missed criterion moves the date, never the bar. Every release re-reads the
targets; the documentation tests refuse a target that has already shipped.

The [generated first-run](docs/generated/first-run.md) and
[application](docs/generated/application-measures.md) measures track the remaining external
1.0 gates. A missing observation remains
not measured; the owner decides any change to the release criteria.

1.0 is reached when:

- the "Now" milestone exit criteria hold, including the three published measures;
- the supported Python facade, extension protocols and output contracts are published with a
  compatibility matrix and a deprecation policy;
- the conformance kit built during F6 and F7 and an independently installed reference pack
  are published;
- every built-in rule that can decline carries finding, clean and inconclusive fixtures;
- the collector envelope is versioned independently from the run schema, with clients and
  storage migrated together, because 1.0 keeps the envelope stable;
- migrations are exercised with older run, dataset, profile, pack and collector documents;
- successful third-party customization and team reproduction are recorded, with consent;
- security and recovery runbooks are exercised;
- two release candidates ship without unplanned public API changes.

0.41.0 met the compatibility-matrix and deprecation-policy criterion, published the conformance kit, added finding, clean and inconclusive fixtures for every built-in rule, published the versioned collector envelope, exercised migrations with documents written by older releases, and exercised collector runbooks. 1.0.0rc1 shipped the 0.41.0 supported surface unchanged, with fixes only. The five first-run sessions, two independent teams, recorded third-party customization, the security runbook drill and the second release candidate are not done; application measures remain "not measured". The reference pack is attached to the GitHub Release but is not on PyPI.

1.0 does not wait for M1, the M3 measurement queries or anything under "Later": each extends a
versioned contract in a 1.x release. The 1.0 release-candidate surface is frozen after rc1:
until stable 1.0, candidates carry fixes only, with no new features, fields or generated API
surface changes. The supported surface, tested examples and migration guidance remain published.

## Now: honest evidence, first value and the real application

Use stable IDs for new planning. Verify the implementation status of each item
before starting it.

| Order | ID | Deliverable | Done when |
|---:|---|---|---|
| 1 | F2 | First result and one custom check | A clean-install offline starter demonstrates a failure, a fix and saved evidence, without an account, key, model or collector. It runs with built-in trust only and shows what an installed pack would execute. A user edits one check and reruns it. Separate paths cover local scan, recorded answers and a real application. Five external users attempt it; publish completion counts and observed times. Target: four finish in ten minutes without maintainer help. **Study pending:** the starter, recipes and study kit ship in 0.33.0; the row stays until [the generated measure](docs/generated/first-run.md) holds five consented sessions. |
| 2 | F6 | Reproducible team checks on the real application | A repository recipe pins profiles, datasets, packs and grading identities, runs the team's own application with safe fixtures or doubles (a model harness only when clearly labelled) and produces a reviewable CI artifact. Two independent teams save a failed and an incomplete result, label a redacted case, version it, regrade it and gate that regression in CI, with no automatic promotion of sensitive production data. Connection settings work across probe, plan, target inspection, monitor and calibration. Repeatable conformance tests cover the providers and adapters the pilots use: system messages, tools, failure paths, budgets, usage and adapter limits. One live retrieval target catches a poisoned document and a tenant-filter failure without an uncontrolled side effect. **Shipped through `0.38.0`:** repository recipes, shared endpoint and judge connections, provider conformance, proven regression cases, declared synthetic fixtures, stateful doubles, tenant-boundary and poisoned-document checks on a reference application, and an application whose guard declines requests. The loop still needs two independent adopters, and the retrieval checks still need an application's own retrieval target. |

F1 shipped in 0.30.0 and the defects found while building it in 0.31.0; Q1 shipped in 0.32.0; F2's starter, recipes and study kit shipped in 0.33.0, and its five-user study is pending; F3 shipped in 0.34.0; F5 shipped in 0.35.0; F6's recipes, connection settings and provider conformance shipped in 0.36.0, its regression cases, fixtures, doubles and seeded checks in 0.37.0, and its guarded-application work in 0.38.0; F7 shipped in 0.39.0; F4 shipped in 0.40.0. M2 (provider and
application conformance) and M4 (evidence to regression) are part of F6 now. F6 regrades with the
recordings F5 shipped. Advanced statistics must not block inspecting a
result, adding a deterministic check or consuming a table; statistically proven regression
claims wait for M1.

### Milestone exit criteria

- A new user obtains a local result and modifies one check.
- A Python consumer processes failed and incomplete runs as typed data.
- Third-party targets, rules, evaluators and the F4 export and webhook work without a fork.
- Case outcomes and missing evidence survive serialization, redaction and export.
- A team runs its own application and reviews saved evidence in CI.
- Three measures are published from generated data: first-run completion, coverage of the
  real application, and the share of attempted checks that reached a supported verdict with
  comparable evidence.
- User research is recorded with consent, without telemetry or invented adoption claims.

## Next, after 1.0: trustworthy comparison and shared measurements

| ID | Deliverable | Done when |
|---|---|---|
| M1 | Paired statistical diff | **Start when** two independent pilot teams each use local `diff` on comparable saved before/after application runs for a documented ship decision, and one requests uncertainty because descriptive counts are insufficient. **Done when** compatible cases and grading identities are paired, repeated trials are handled at case level, insufficient coverage or power is refused, effect size and uncertainty are reported, declared effects can gate, and multiple gated suites are controlled. Version the comparison and grading-identity contract; label existing descriptive diff accurately. |
| M3 | Collector measurements | **Start when** two independent teams submit and read their own locked application runs in the optional collector and each asks the same cross-run question that local files cannot answer. **Done when** versioned envelope and storage queries answer that recorded question by the necessary system, deployment, dataset and assessor dimensions, enforce tenancy, and report sample counts, uncertainty, coverage gaps, missingness and unknowns beside trends. Keep the envelope versioned independently from the run schema. |

## Later: ongoing verification and platform fit

Later is an unordered, unversioned set of possibilities, not a plan for 2.0. Promoting an item to Now requires pilot pain, a reproducible failing case, an acceptance criterion, and a versioned contract review. A future 2.0 additionally requires evidence that a necessary public-contract break cannot be represented faithfully by a compatible 1.x addition.

- Synthetic scheduled verification with anytime-valid monitoring, rather than repeated fixed-level tests presented as reliable alerts.
- A Prometheus reporter over the common output contract, once a team names the measurements and unknowns it needs.
- Live RAG and application targets beyond the F6 pilot, with safe fixtures and explicit data boundaries, ordered by pilot needs.
- Model-artifact inventory and parser completeness, starting from the known gaps in unlisted formats and safetensors validation; accept only when malformed, unreadable and partially scanned inputs cannot look clean under the versioned scan and coverage contract.
- An agent tool-action application target after retrieval, only if a pilot supplies a controlled injected input, complete action trace and harmless side-effect oracle; review the versioned target, fixture and trace contracts before adding it.
- Central distribution of signed, versioned profiles and policies, after local locks and recipes prove use.
- Profiles distributed in packs are a 1.x addition. `guardana.yaml`, the presets and the versioned profile schema are the 1.0 contract.
- Agent-card signature verification for A2A as an optional extra, so the JOSE dependency it needs never reaches `guardana-core`.
- Agent supply-chain provenance beyond a manifest hash: the approved tool schema, package or image identity, resolved server origin, and skill and configuration identity.
- An evidence-quality contract for imported runs (garak, promptfoo, Inspect, OpenTelemetry): source trust, missing fields, redaction, sampling, judge identity and comparability, and when an imported observation may become a verified local regression.
- OIDC/SSO, human roles and Helm when collector users need them; exercise upgrade, rollback, backup, restore and deletion.

An exported recording remains an explicit supported subset behind an adapter.
OpenTelemetry conventions are input formats, not Guardana's storage contract.
Live production intake and supervision belong to
Guardana Control.

## Parallel contributor lane

Small deterministic checks, framework adapters, taxonomy updates and artifact
formats may proceed when they do not delay the milestone. Heavy dependencies,
niche corpora and experimental graders belong in extension packages.

These move up: ATLAS provenance, pinning
the monthly content release and the data-format release separately, with positive and
negative fixtures for new techniques; fixture expressiveness; and the non-executing declarative packs decided
but not yet built, because installed Python packs execute code. A public extension-ID service is dropped: namespaces,
local validation and locks cover the author workflow.

Application quality checks need application-owned criteria, rather than invented
OWASP mappings; built-in security checks retain public-framework mappings
([CONTRIBUTING.md](CONTRIBUTING.md), principle 5).

## Researched after the foundations

Multi-agent protocols beyond the A2A fixture in F7, multimodal carriers beyond one
document or image carrier a pilot actually uses, adaptive attackers,
reusable techniques and broad multilingual or
domain corpora follow measured usefulness, evaluation quality and bounded execution.
Import or buy coverage rather than grow the prompt count; attack volume is not the
adoption metric.

## Non-goals

An inline firewall or guardrail proxy; production agent supervision; a general
SAST, CVE, secret or network scanner; a second production trace store; compliance
certification; a marketplace of unverified prompts; autonomous production attacks.

## Release gate and changing the order

Every increment needs meaningful tests, docs, redacted evidence, explicit exit
and delivery behavior, compatibility/migration notes and a changelog entry.
Follow [CONTRIBUTING.md](CONTRIBUTING.md), including isolated extension installation
checks and generated documentation. Skips are not passes.

Change priority using a user problem, observed evidence, affected item ID,
dependencies and the work moved down. Use GitHub issues for owners, acceptance
evidence and externally discoverable contributor tasks.
