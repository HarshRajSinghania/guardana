---
title: "Documentation"
nav_order: 340
summary: "Choose a task, then follow one focused guide."
status: stable
---

# Guardana documentation

Start with the root [README](../README.md). Before production use, read [Product status](product-status.md), [Safe testing](safe-testing.md), and the [Threat model](threat-model.md).

## First run

- [`install.md`](install.md) — install the CLI or a container
- [`usage-init.md`](usage-init.md) — a first-run project that fails, is fixed and keeps its evidence, offline
- [`recipe-local-scan.md`](recipe-local-scan.md) — scan your own project and save the run
- [`recipe-recorded-answers.md`](recipe-recorded-answers.md) — check a run your application already recorded
- [`recipe-real-application.md`](recipe-real-application.md) — probe the application your users talk to
- [`usage-scan.md`](usage-scan.md) — scan artifacts offline
- [`usage-probe.md`](usage-probe.md) — probe a live endpoint, agent, or MCP server
- [`usage-testing.md`](usage-testing.md) — run the same checks from pytest
- [`python-api.md`](python-api.md) — run scans and probes from Python and read every outcome as data
- [`how-it-works.md`](how-it-works.md) — understand targets, rules, evaluators, and evidence

## Run and policy

- [`profiles.md`](profiles.md) — configure rules, gates, budgets, trust, and redaction
- [`usage-plan.md`](usage-plan.md) — estimate a run before sending requests
- [`usage-target.md`](usage-target.md) — verify endpoint capabilities
- [`providers.md`](providers.md) — what each provider and adapter carries, and which failures it retries
- [`usage-doctor.md`](usage-doctor.md) — validate and explain effective configuration
- [`safe-testing.md`](safe-testing.md) — bound active checks and side effects
- [`exit-codes.md`](exit-codes.md) — interpret command outcomes

## Evidence and regression

- [`usage-run.md`](usage-run.md) — inspect and migrate saved runs
- [`usage-diff.md`](usage-diff.md) — compare runs without hiding coverage changes
- [`usage-baseline.md`](usage-baseline.md) — accept risk with an expiry
- [`usage-monitor.md`](usage-monitor.md) — schedule active re-verification
- [`usage-calibrate.md`](usage-calibrate.md) — measure evaluator confidence
- [`usage-suites.md`](usage-suites.md) — gate a deployed endpoint against a golden set
- [`privacy.md`](privacy.md) — control redaction and retained evidence

## Recorded applications

- [`usage-analyze-trace.md`](usage-analyze-trace.md) — grade a recorded execution
- [`usage-grade.md`](usage-grade.md) — grade answers your application already gave, without calling it
- [`usage-trace-inspect.md`](usage-trace-inspect.md) — inspect available evidence dimensions
- [`usage-contracts.md`](usage-contracts.md) — express application-specific invariants
- [`usage-import-observations.md`](usage-import-observations.md) — import external tool claims
- [`writing-an-integrator.md`](writing-an-integrator.md) — produce honest trace evidence

## Rules and extensions

- [`usage-rules.md`](usage-rules.md) — list discovered rules
- [`writing-rules.md`](writing-rules.md) — create YAML or Python rules
- [`usage-rule-test.md`](usage-rule-test.md) — test positive, negative, and inconclusive fixtures
- [`extending.md`](extending.md) — provide rules, evaluators, targets, or taxonomies
- [`usage-new-pack.md`](usage-new-pack.md) — scaffold an installable pack that already passes
- [`usage-pack.md`](usage-pack.md) — validate and lock extension packs
- [`usage-taxonomy.md`](usage-taxonomy.md) — resolve framework editions and crosswalks
- [`model-formats.md`](model-formats.md) — use the bounded artifact readers

## Collector and deployment

- [`usage-collector.md`](usage-collector.md) — operate the optional collector
- [`deployment.md`](deployment.md) — deploy it with PostgreSQL and TLS
- [`integrations.md`](integrations.md) — connect Guardana to CI and GitHub
- [`../deploy/docker/README.md`](../deploy/docker/README.md) — use the official images
- [`../deploy/ci/README.md`](../deploy/ci/README.md) — use GitLab, Jenkins, or Azure DevOps

## Architecture and security

- [`architecture.md`](architecture.md) — understand package and trust boundaries
- [`threat-model.md`](threat-model.md) — see what Guardana does and does not defend
- [`product-status.md`](product-status.md) — check maturity and known limitations

## Reference

These files are generated from the registry and are the source of truth for
coverage. Do not edit them by hand.

- [`generated/rule-summary.md`](generated/rule-summary.md) — counts by surface and severity
- [`generated/rule-catalog.md`](generated/rule-catalog.md) — every built-in rule
- [`generated/evaluator-catalog.md`](generated/evaluator-catalog.md) — every evaluator
- [`generated/taxonomy-coverage.md`](generated/taxonomy-coverage.md) — framework coverage
- [`generated/detection-limits.md`](generated/detection-limits.md) — what a finding states, per rule family
- [`generated/first-run.md`](generated/first-run.md) — whether new users reach a first result in ten minutes, from the study sheet

## Design documents

- [`design/README.md`](design/README.md) — accepted decisions, proposals, and status conventions

Design documents explain why an implementation has its current shape. They are
not task guides and may describe rejected or superseded alternatives.

## Project direction

- [`../FEATURES.md`](../FEATURES.md) — concise shipped capability overview
- [`../ROADMAP.md`](../ROADMAP.md) — ordered next work and exit criteria
- [`design/audit-0.31-direction.md`](design/audit-0.31-direction.md) — the current order: evidence and gate integrity first, the real application as the acceptance test, protocol conformance, and narrower output work
- [`design/guardana-and-control.md`](design/guardana-and-control.md) — Guardana and Guardana Control: measuring before release versus supervising agents while they run, what the two exchange, and how the two sites divide the work
- [`design/non-executing-packs.md`](design/non-executing-packs.md) — whether a pack can ship checks that execute no Python, and why every command starts with built-in plugin trust
- [`../CHANGELOG.md`](../CHANGELOG.md) — release history

## Maintainers

- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — setup, quality gates, and review rules
- [`../RELEASING.md`](../RELEASING.md) — versioning and publishing
- [`maintainers/github-setup.md`](maintainers/github-setup.md) — repository settings
- [`maintainers/ops-catalogue.md`](maintainers/ops-catalogue.md) — which script, is it safe, what it needs
- [`maintainers/lessons.md`](maintainers/lessons.md) — why the rules are what they are
- [`maintainers/first-run-study.md`](maintainers/first-run-study.md) — how the first-run sessions are run, consented and recorded

## Governance

- [`../SECURITY.md`](../SECURITY.md) — report vulnerabilities and understand support
- [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) — community expectations
