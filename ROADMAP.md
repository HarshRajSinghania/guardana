# Guardana roadmap

Guardana should give an individual developer a useful result on the first run,
then let a team turn the same evidence into its own tests, gates, reports and
tools without forking the engine. The product is an offline-first verification
framework with a usable CLI and optional collection, outside the production
request path.

This is the ordered plan, not a release promise. [FEATURES.md](FEATURES.md)
describes shipped behavior; [the generated rule summary](docs/generated/rule-summary.md)
and [rule catalog](docs/generated/rule-catalog.md) are the coverage source of truth;
[Product status](docs/product-status.md) states limits; [CHANGELOG.md](CHANGELOG.md)
records releases; [the framework audit](docs/design/framework-usability-audit.md)
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

## What ships today (0.29.0)

The current release is beta. It provides offline artifact scanning, controlled endpoint
and MCP probing with repeated trials, recorded-trace analysis, regression comparison,
policy and baseline gates, extension APIs with scaffolding for a new pack, and an
optional authenticated PostgreSQL-backed collector. Quality suites grade versioned
datasets supplied by the team and gate their pass rates. Judge-graded trials and suite
pass rates are corrected for the judge's measured error when a matching calibration
exists; otherwise the report says so. See [FEATURES.md](FEATURES.md) for the concise
overview and [Product status](docs/product-status.md) for limitations.

## Now: first value and an extensible data workflow

Use stable IDs for new planning. Older designs may reference the previous numbered
roadmap table; their decisions remain historical inputs. Verify the implementation
status of each item before starting it.

| Order | ID | Deliverable | Done when |
|---:|---|---|---|
| 1 | F2 | First result and one custom check | A clean-install offline starter demonstrates a failure, a fix and saved evidence, without an account, key, model or collector. A user edits one check and reruns it. Separate paths cover local scan, recorded answers and a real application. Five external users attempt it; publish completion counts and observed times. Target: four finish in ten minutes without maintainer help. |
| 2 | F3 | Supported Python data workflow | A documented facade composes the existing registry, execution, redaction, gate, manifest and serialization. Typed results are accessible even when a run fails. CLI and Python agree on every result channel and gate. Custom targets, local checks and private evaluators work through both; trust, calibration, budgets and paths are explicit. |
| 3 | F4 | Renderer and reporter plugins | Implement the output-plugin proposal with common redaction, collision checks, trust modes, pack validation and locks. An independently installed package exports a local table and delivers a team webhook payload without CLI changes. Offline use has no network; delivery status is separately observable. |
| 4 | F5 | Recorded-answer grading and evidence regrading | Versioned, validated cases with supplied answers can be assessed without target calls. Original execution and new grading identities remain separate. Remote judging declares traffic and budget; unavailable or insufficient evidence stays ungraded. |
| 5 | F6 | Reproducible team checks | A repository recipe pins profiles, datasets, packs and grading identities; runs the actual application or a clearly labelled model harness; and produces a reviewable CI artifact. Connection settings work across probe, plan, target inspection, monitor and calibration. Two independent teams reproduce a run and consume its data. |

F1 (suite integration and verdict defects) shipped in 0.30.0. Design F3 and F4 around
the same result boundary. F5 consumes it. Advanced statistics must not block
inspecting a result, adding a deterministic check or consuming a table;
statistically proven regression claims must wait for M1.

### Milestone exit criteria

- A new user obtains a local result and modifies one check.
- A Python consumer processes failed and incomplete runs as typed data.
- Third-party targets, rules, evaluators, renderers and reporters work without a fork.
- Case outcomes and missing evidence survive serialization, redaction and export.
- A team runs its application and reviews saved evidence in CI.
- User research is recorded with consent, without telemetry or invented adoption claims.

## Next: trustworthy comparison and shared measurements

| ID | Deliverable | Done when |
|---|---|---|
| M1 | Paired statistical diff | Pair compatible cases and grading identities; handle repeated trials at the case level; refuse insufficient coverage or power; report effect size and uncertainty; gate on a declared effect; control multiple gated suites. Label existing descriptive diff accurately. |
| M2 | Provider and application conformance | Repeatable tests back documented support, starting with pilot-team providers and adapters. Exercise system messages, tools, failure paths, budgets, usage and adapter limits. |
| M3 | Collector measurements | Version the envelope independently from run schema; migrate clients and storage together. Query by system, deployment, dataset and assessor; carry sample counts, unknowns and uncertainty. Show coverage gaps beside trends. |
| M4 | Evidence-to-regression workflow | A team reviews and labels redacted recorded cases, versions a small dataset, adds an assessor and prevents a previously observed failure in CI. No automatic promotion of sensitive production data. |

Keep the earlier designs for [suites](docs/design/quality-suites.md),
[trials](docs/design/repeated-trials.md) and
[judge error](docs/design/judge-error-correction.md).
F4 starts from [output plugins](docs/design/output-plugins.md);
F5 from [regrading](docs/design/regrading-stored-exchanges.md);
M1 from [paired statistics](docs/design/paired-regression-statistics.md).

## Later: ongoing verification and platform fit

- Synthetic scheduled verification with [anytime-valid monitoring](docs/design/anytime-valid-monitoring.md), rather than repeated fixed-level tests presented as reliable alerts.
- Prometheus and webhook reporters over the common output contract.
- Live RAG/application targets with safe fixtures and explicit data boundaries, ordered by pilot needs.
- Central distribution of signed, versioned profiles and policies.
- OIDC/SSO, human roles and Helm when collector users need them; exercise upgrade, rollback, backup, restore and deletion.

An exported recording remains an explicit supported subset behind an adapter.
OpenTelemetry conventions are input formats, not Guardana's storage contract.
Live production intake and supervision belong to
[Guardana Control](docs/design/guardana-and-control.md).

## 1.0: dependable extension contracts

- Publish the supported Python facade, extension protocols and output contracts, with a compatibility matrix and deprecation policy.
- Ship a standalone conformance kit and independently installed reference pack.
- Exercise migrations with older run, dataset, profile, pack and collector documents.
- Ship two release candidates without unplanned public API changes.
- Record successful third-party customization and team reproduction, with consent.
- Exercise security and recovery runbooks.

Beta does not require an API freeze. It requires an explicit supported surface,
tested examples and migration guidance when that surface changes.

## Parallel contributor lane

Small deterministic checks, framework adapters, taxonomy updates and artifact
formats may proceed when they do not delay the milestone. Heavy dependencies,
niche corpora and experimental graders belong in extension packages.

ATLAS content provenance, fixture expressiveness, stateful tool doubles and
non-executing declarative packs remain in [the backlog](docs/work/BACKLOG.md).
Evaluate declarative pack loading before building a public extension-ID service;
namespaces and local validation already address the immediate author workflow.

Application quality checks need application-owned criteria, rather than invented
OWASP mappings; built-in security checks retain public-framework mappings
([CONTRIBUTING.md](CONTRIBUTING.md), principle 5).

## Researched after the foundations

Multi-agent protocols, multimodal carriers, adaptive attackers,
[reusable techniques](docs/design/attack-techniques.md) and broad multilingual or
domain corpora follow measured usefulness, evaluation quality and bounded execution.
Additional attack volume is not the current adoption metric.

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
