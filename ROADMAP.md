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
records releases; [the direction audit](docs/design/audit-0.31-direction.md)
explains this order.

## Product constraints

1. An unavailable check, ungraded case, partial run or invalid comparison never becomes a pass.
2. Offline scanning stays offline; target and judge traffic is explicit and bounded.
3. Engine capabilities and built-in checks remain open source, without an account.
4. Application-specific checks and output destinations work without an engine fork.
5. Public data formats are versioned, with tested readers and migrations.
6. Findings, quality measurements, errors and missing evidence remain separate.
7. Results explain their source, coverage, execution cost and comparability.
8. The collector is optional; local files and Python deliver independent value.

## What ships today (0.35.0)

This beta scans offline artifacts, runs repeated controlled endpoint and MCP probes, analyzes recorded traces, diffs regressions, gates on policy and baselines, supports extension APIs and pack scaffolding, and offers an optional authenticated PostgreSQL collector. The supported Python API, `guardana.core.verify`, runs what `guardana scan` and `guardana probe` run and returns every outcome as typed data, including failed, indeterminate and stopped runs; Python callers state plugin trust as every command does. Quality suites grade versioned team datasets and gate pass rates; stopped or raised suites keep total and measured case counts and appear as JUnit errors. Plans price judge calls against budgets; saved runs log judge usage and budget stops. Agent checks catch canary leaks across turns, require payload proof and argument allowlists, and never pass a truncated run. Judge-graded suites and judge-error correction are experimental; matching calibrations correct trial/suite rates, and reports flag their absence. Text checks read every agent reply; a scenario step grades replies since the previous graded step. Target URL credentials stay out of saved runs, reports and messages. Plans refuse runs that cannot pass; crashes and interrupts exit with documented codes. Human, JSON, SARIF and JUnit outputs and `plan` agree on every run that does not pass; none renders clean a run the gate refused. Saved trace and imported-document runs record the SHA-256 of bytes read and whether the read covered the whole file (`run.target.document`). `--preset release` fails when a selected check is skipped or has no verdict, and `plan` refuses such a run before sending anything. A generated page identifies tested invariants, heuristic leads and framework entries only mapped for each rule family. Every command starts with built-in plugin trust: an installed pack is refused before import until admitted by name, and `guardana doctor` lists what it would execute. `guardana init --starter` writes an offline first run that fails, is fixed, keeps its evidence and edits one local check. `guardana grade` grades a recording of answers an application already gave, or exchanges kept by `guardana probe --keep-exchanges`, with no target request; missing or altered answers never pass. Saved runs use schema 13 to keep the graded execution apart from the grading, and `guardana diff` leaves out a rule graded by another evaluator or judge. See [FEATURES.md](FEATURES.md) and [Product status](docs/product-status.md).

## First goal: 1.0

1.0 is the first release whose public surface stays stable: the supported Python facade, the
rule, evaluator and target contracts, the output contracts, the CLI flags and exit codes, the
profile schema and the collector envelope. From 1.0 on, a breaking change needs a major
version ([RELEASING.md](RELEASING.md)).

It follows the three remaining "Now" items, with F2's five-user study alongside, one readiness release and two release candidates:

| Target | Delivers |
|---|---|
| **v0.36**, **v0.37** | F6 on the real application: the recipe, connection settings and provider conformance, then the team regression loop and the live retrieval pilot |
| **v0.38** | F7 protocol and evidence conformance |
| **v0.39** | F4 one redacted export and one webhook |
| **v0.40** | 1.0 readiness: every criterion below that an earlier release did not meet |
| **v1.0.0rc1**, **v1.0.0rc2** | the frozen surface with fixes only, at least two weeks apart so the pilot teams can run each one |
| **v1.0.0** | the first stable release |

The target is the first quarter of 2027. External evidence sets that date more than the code
does: five first-run users after F2, two independent teams in F6 and a recorded third-party
customization. A missed criterion moves the date, never the bar. Every release re-reads the
targets; the documentation tests refuse a target that has already shipped.

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

1.0 does not wait for M1, the M3 measurement queries or anything under "Later": each extends a
versioned contract in a 1.x release. Until 1.0, beta does not require an API freeze. It
requires an explicit supported surface, tested examples and migration guidance when that
surface changes.

## Now: honest evidence, first value and the real application

Use stable IDs for new planning. Older designs may reference the previous numbered
roadmap table; their decisions remain historical inputs. Verify the implementation
status of each item before starting it.

| Order | ID | Deliverable | Done when |
|---:|---|---|---|
| 1 | F2 | First result and one custom check | A clean-install offline starter demonstrates a failure, a fix and saved evidence, without an account, key, model or collector. It runs with built-in trust only and shows what an installed pack would execute. A user edits one check and reruns it. Separate paths cover local scan, recorded answers and a real application. Five external users attempt it; publish completion counts and observed times. Target: four finish in ten minutes without maintainer help. **Study pending:** the starter, recipes and study kit ship in 0.33.0; the row stays until [the generated measure](docs/generated/first-run.md) holds five consented sessions. |
| 2 | F6 | Reproducible team checks on the real application | A repository recipe pins profiles, datasets, packs and grading identities, runs the team's own application with safe fixtures or doubles (a model harness only when clearly labelled) and produces a reviewable CI artifact. Two independent teams save a failed and an incomplete result, label a redacted case, version it, regrade it and gate that regression in CI, with no automatic promotion of sensitive production data. Connection settings work across probe, plan, target inspection, monitor and calibration. Repeatable conformance tests cover the providers and adapters the pilots use: system messages, tools, failure paths, budgets, usage and adapter limits. One live retrieval target catches a poisoned document and a tenant-filter failure without an uncontrolled side effect. |
| 3 | F7 | Protocol and evidence conformance | MCP `2025-11-25` and `2026-07-28` are tested against independent server fixtures for authorization, task identity, cache scope, registry metadata and version changes. One A2A v1 fixture covers the agent card, caller identity and task visibility. A capability a server does not support is recorded as missing coverage, never as a pass. |
| 4 | F4 | One redacted export and one webhook | One redacted local export and one webhook that reports its delivery status go through the common redaction boundary, collision checks, trust modes and pack locks, from an independently installed package, without CLI changes. Offline use sends nothing. The general renderer and reporter plugin contract waits for a team that needs more. |

F1 shipped in 0.30.0 and the defects found while building it in 0.31.0; Q1 shipped in 0.32.0; F2's starter, recipes and study kit shipped in 0.33.0, and its five-user study is pending; F3 shipped in 0.34.0; F5 shipped in 0.35.0. M2 (provider and
application conformance) and M4 (evidence to regression) are part of F6 now. Design F4
around the result boundary F3 shipped, `guardana.core.verify`; F6 regrades with the
recordings F5 shipped ([recorded answers](docs/design/recorded-answers.md)). Advanced statistics must not block inspecting a
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
| M1 | Paired statistical diff | Pair compatible cases and grading identities; handle repeated trials at the case level; refuse insufficient coverage or power; report effect size and uncertainty; gate on a declared effect; control multiple gated suites. Label existing descriptive diff accurately. It follows the F5–F6 evidence workflow. |
| M3 | Collector measurements | Query by system, deployment, dataset and assessor; carry sample counts, unknowns and uncertainty. Show coverage gaps beside trends. It starts after two teams reproduce and consume local results. Versioning the envelope independently from the run schema is a 1.0 criterion. |

Keep the earlier designs for [suites](docs/design/quality-suites.md),
[trials](docs/design/repeated-trials.md) and
[judge error](docs/design/judge-error-correction.md).
F4 starts from [output plugins](docs/design/output-plugins.md), narrowed to the export and
the webhook; M1 from [paired statistics](docs/design/paired-regression-statistics.md) and
the case-compatibility contract in [recorded answers](docs/design/recorded-answers.md). F6 and F7
start from [the direction audit](docs/design/audit-0.31-direction.md) and need a design
before code.

## Later: ongoing verification and platform fit

- Synthetic scheduled verification with [anytime-valid monitoring](docs/design/anytime-valid-monitoring.md), rather than repeated fixed-level tests presented as reliable alerts.
- A Prometheus reporter over the common output contract, once a team names the measurements and unknowns it needs.
- Live RAG and application targets beyond the F6 pilot, with safe fixtures and explicit data boundaries, ordered by pilot needs.
- Central distribution of signed, versioned profiles and policies, after local locks and recipes prove use.
- Agent supply-chain provenance beyond a manifest hash: the approved tool schema, package or image identity, resolved server origin, and skill and configuration identity.
- An evidence-quality contract for imported runs (garak, promptfoo, Inspect, OpenTelemetry): source trust, missing fields, redaction, sampling, judge identity and comparability, and when an imported observation may become a verified local regression.
- OIDC/SSO, human roles and Helm when collector users need them; exercise upgrade, rollback, backup, restore and deletion.

An exported recording remains an explicit supported subset behind an adapter.
OpenTelemetry conventions are input formats, not Guardana's storage contract.
Live production intake and supervision belong to
[Guardana Control](docs/design/guardana-and-control.md).

## Parallel contributor lane

Small deterministic checks, framework adapters, taxonomy updates and artifact
formats may proceed when they do not delay the milestone. Heavy dependencies,
niche corpora and experimental graders belong in extension packages.

These move up, and live in [the backlog](docs/work/BACKLOG.md): ATLAS provenance, pinning
the monthly content release and the data-format release separately, with positive and
negative fixtures for new techniques; fixture expressiveness and stateful tool doubles,
which F6 needs; and the non-executing declarative packs [decided](docs/design/non-executing-packs.md)
but not yet built, because installed Python packs execute code. A public extension-ID service is dropped: namespaces,
local validation and locks cover the author workflow.

Application quality checks need application-owned criteria, rather than invented
OWASP mappings; built-in security checks retain public-framework mappings
([CONTRIBUTING.md](CONTRIBUTING.md), principle 5).

## Researched after the foundations

Multi-agent protocols beyond the A2A fixture in F7, multimodal carriers beyond one
document or image carrier a pilot actually uses, adaptive attackers,
[reusable techniques](docs/design/attack-techniques.md) and broad multilingual or
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
dependencies and the work moved down. Record owners and acceptance evidence in
work files; use GitHub issues for externally discoverable contributor tasks.
