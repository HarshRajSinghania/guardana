---
title: "Framework usability audit"
nav_order: 210
summary: "Evidence behind prioritizing first value, a supported Python data workflow and output extensions."
status: superseded
---

# Framework usability and direction audit

**Status:** superseded by [`audit-0.31-direction.md`](audit-0.31-direction.md), which keeps this document's evidence and changes its order · **Written:** 2026-09-26

The roadmap order was updated at the owner's request. This document records the
research and implementation rationale; it does not claim the proposed APIs ship.
Initial snapshot: HEAD `1fcb037443d8e928542ca6778145465863b24229`, main two commits ahead
of origin/main, with substantial uncommitted suite/assessment work. Findings apply
to this working tree, not an independently verified installed PyPI release.

Final reconciliation: concurrent work advanced HEAD to the 0.29.0 release
(`5bed6dc`), completed suite documentation and removed the measurement work file.
The WIP observations below describe the initial inspection. F1 now verifies
remaining integration and verdict gaps; it does not rebuild or release suites.
The initial missing suite-document link is resolved in the final tree.

## Decision

Verify released suite integration and verdict correctness, then prioritize a runnable starter, a
supported Python result facade, output extensions, recorded-answer grading and
reproducible team checks. Follow with statistical gates and shared measurements.
Preserve the offline engine, separation of result channels, bounded execution,
versioned schemas and optional collector. Do not rewrite the engine.

## Implementation evidence

| Area | Observed evidence | Assessment |
|---|---|---|
| Package boundaries | `pyproject.toml` import contracts; `uv run lint-imports` kept all three contracts across 339 files | Strong separation of engine, CLI and optional collector. |
| Extension input | `core/registry.py`, `core/target/protocols.py`, `examples/custom_rule/`, isolated-install checks in CONTRIBUTING | Real discovery and protocol seams, not only documentation. Four groups exist today. |
| Output extension | `cli/_formats.py` is a four-value enum; `cli/_reporting.py` constructs HttpReporter | Renderer/reporter protocols exist but arbitrary CLI output destinations still require CLI changes. |
| Data | `core/report/result.py`, `core/assessment.py`, `core/manifest/`, `schemas/` | Typed multi-channel results and versioned manifests are a sound foundation for custom tooling. |
| Python workflow | `guardana.testing.assert_secure` returns data on pass and attaches data to its exception on failure; `Runner.run` is available but lower level | There is a usable API, but an application integrating data must assemble discovery, calibration, redaction, manifest and gate behavior. A facade should compose existing behavior. |
| Bootstrap | `cli/init.py` writes a short rules/severity profile; README starts with artifact scan | Immediate scan value exists; bootstrap does not scaffold the user's own application, dataset, assessor and result consumer. |
| Own-agent coverage | Product status explicitly distinguishes Guardana's model harness from the user's actual agent | Honest limitation; framework model adapters alone do not establish application-level coverage. |
| Suite work | Uncommitted at the snapshot; released in 0.29.0 (`5ad527e`, `5bed6dc`) with `docs/usage-suites.md` | F1 verifies the remaining gaps listed in the backlog; the suite is not rebuilt. |
| Collector | `core/reporter.py::_serialize` carries findings, unverified, errors and run metadata; no assessments | Team measurement support requires an independent envelope and storage evolution. Run-v9 alone is insufficient. |
| Calibration paths | `cli/_run_meta.py::_recorded_calibrations` uses `Path(raw_path)` | Backlog path-resolution defect remains present. |
| Connection options | Only probe exposes adapter; plan, target, monitor and calibrate do not | A custom guarded endpoint cannot use the full lifecycle through equivalent command options. |
| Trust | `core/plugins.py` defaults to ALL; registry filters distributions before `ep.load` | Allowlisting exists. Do not describe disabled mode as a sandbox. Python packs execute installed code; starter trust must be explicit. |
| Verdict scope | Canary evaluator reads `reply_text`; argument evaluator matches substrings in serialized arguments | Existing backlog defects need execution-scope and argument-value regressions before broader agent assurance claims. |
| Public backlog | GitHub open issues query returned zero; five open PRs were dependency updates | Contributor discovery lacks public product tasks. Absence of issues is not proof of absence of users or work. |

The audit sampled architecture and key workflows; it is not a penetration test,
full provider validation, database recovery exercise or release certification.

## Documentation and backlog

Documentation is extensive: extension contracts, doubles, third-party examples,
product limits, privacy, install and CI instructions exist. Missing value is a
short task-oriented path through those pieces. Add three recipes: first local
finding, a recorded answer dataset and a real application with one custom check.
Each ends in a saved result that another program reads.

Fix wording that says answer quality is outside the product while suites add it.
Clarify that public taxonomy mapping applies to security checks; application-owned
quality criteria should not need artificial compliance references. RuleMeta
already permits an empty taxonomy; policy wording and declarative loaders must
be reviewed together. Do not remove mappings from existing security checks.

The backlog is a useful inventory but mixes verdict correctness, developer
friction, tooling, speculative registries and cross-product marketing. Preserve
its history, add IDs and link it to the roadmap. Use the shipped 0.29.0 suite design and documentation as the baseline. Publish small contributor tasks only
when owners are ready; this audit did not create remote issues.

## Research and its implications

Sources were read on 2026-09-26. Documentation establishes capabilities, not
comparative performance, adoption, license suitability or market demand.

- Promptfoo connects prompts, providers, test cases and assertions in configuration,
  supports custom providers and local structured tests. The relevant lesson is a
  short editable path to a result, rather than copying its entire product.
  [Configuration](https://www.promptfoo.dev/docs/configuration/guide/),
  [getting started](https://www.promptfoo.dev/docs/getting-started/).
- DeepEval exposes custom metrics within its evaluation workflow and CI integration.
  This supports treating the developer's own criterion as a primary extension.
  [Custom metrics](https://deepeval.com/guides/guides-building-custom-metrics).
- Inspect separates task execution and scoring, supports multiple scorers,
  unscored outcomes and re-scoring saved logs. Guardana should preserve that
  separation within its own domain and use it to support custom data consumers.
  [Scoring](https://inspect.aisi.org.uk/scoring.html),
  [components](https://inspect.aisi.org.uk/extensions-components.html).
- OpenTelemetry's GenAI convention entry now points to a dedicated repository.
  Input adapters need an explicit supported convention revision and fixture set;
  Guardana's persisted schema must stay independent.
  [GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

Inference: differentiate around explainable security verification and reusable
application evidence, with explicit missingness and trustworthy comparison.
Generic eval orchestration already has substantial alternatives. That does not
prove users want Guardana: test the first-value flow with five developers and the
team flow with two teams before investing in platform infrastructure.

## Proposed implementation boundaries

Use existing Target, Rule, Evaluator, Registry and Runner. Add a facade that
accepts a profile, explicit trust and grading context, runs the existing engine,
and returns the result, gate and manifest. Choose the public name in F3's design.
Do not build a second execution engine or force data access through assert_secure.

Use one redaction boundary before outputs. Never silently give an output plugin
raw exchanges. Treat execution, grading and delivery identities/statuses as
separate facts. Validate supplied records before running assessors. Offline
recorded-answer grading means no target calls; a configured remote judge is still
network traffic and must be budgeted.

Retain the output-plugin proposal rather than inventing incompatible entry-point
shapes. Include independently installed plugins in tests. Stabilize supported
paths during beta with contract tests and migration notes, without a premature
freeze of the full domain model.

Descriptive comparison is useful immediately, but must not be called a powered
statistical regression gate. M1 keeps case-level pairing, repeated-trial handling,
coverage checks, meaningful effect thresholds and multiple-testing controls.
No advanced infrastructure feature may silently weaken those requirements.

## Validation at the audit snapshot

- Registry, registry isolation, dataset, suite rule, suite statistics and suite CLI:
  119 selected tests passed.
- Import contracts: three kept, none broken.
- CLI help and doctor ran. Doctor reported 51 rules, 10 registered evaluators,
  no installed custom target schemes and no default budget ceiling.
- Final documentation consistency, design-status and documentation-site tests passed
  after reconciliation with 0.29.0 and regeneration of the site and sitemap.
  The initial missing suite-page link was resolved by concurrent release work.
- Full repository gate, live providers and PostgreSQL checks were not run for
  this documentation change. Passing selected tests does not certify a release.

## Planning and acceptance

[ROADMAP.md](../../ROADMAP.md) defines F1–F6 and M1–M4 acceptance criteria.
[BACKLOG.md](../work/BACKLOG.md) links concrete findings to them. Start with F1's
remaining gaps, then F2/F3/F4. Each item needs a work file, meaningful tests, docs,
compatibility notes and recorded acceptance evidence. Reconcile older numbered
roadmap references when the corresponding design or work file is next updated;
do not overwrite accepted historical reasoning.
