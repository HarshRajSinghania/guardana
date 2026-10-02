# Guardana features

Guardana is an open-source AI security verification engine. It checks artifacts,
live systems, and recorded executions with one policy and one evidence model.

This page is an overview, not a second rule catalog. Exact, generated sources of
truth are the [rule summary](docs/generated/rule-summary.md),
[rule catalog](docs/generated/rule-catalog.md),
[evaluator catalog](docs/generated/evaluator-catalog.md), and
[taxonomy coverage](docs/generated/taxonomy-coverage.md).

For maturity and known gaps, read [Product status](docs/product-status.md).

## Core workflows

| Need | Command | Result |
|---|---|---|
| A first result, offline | `guardana init --starter DIR` | a failing scan, its fix, a saved run and one editable local check, with no account, key, model or network |
| Scan code and model artifacts | `guardana scan PATH` | deterministic, offline findings |
| Probe a model, agent, or MCP server | `guardana probe ...` | bounded active checks with graded evidence |
| Analyze an existing execution | `guardana analyze-trace TRACE` | trace rules over a local file, calling no model or tool |
| Grade recorded answers | `guardana grade RECORDING` | your rules over answers you supplied or a probe kept, with no target request |
| Inspect available evidence | `guardana trace inspect TRACE` | recorded dimensions and policy gaps |
| Compare releases | `guardana diff BEFORE AFTER` | deterioration, improvement, or an explicit refusal to compare |
| Re-run checks on a schedule | `guardana monitor ...` | each cycle gated and compared with the first cycle |
| Use verification in tests | `guardana.testing.assert_secure(...)` | the same policy as a pytest assertion |
| Run verification from Python | `guardana.core.verify.Verifier(trust=...)` | the run `scan` or `probe` writes, as typed data, failed and stopped runs included |

[Providers](docs/providers.md) lists what each provider and adapter carries and retries; one
conformance suite holds them to it.

Every target-building workflow also accepts an installed, trusted custom target
as `--target scheme://locator`. The command retains control of the target kind,
budgets, policy, evidence, and exit behavior; the extension owns only how its
locator becomes a target. `guardana doctor` shows which schemes were loaded.

`guardana plan`, `target inspect`, `doctor`, `config explain`, `config validate`,
`baseline`, `run inspect`, `run migrate`, `rules`, `taxonomy`, `rule test`,
`pack`, `calibrate`, `init`, `new-rule`, `new-pack`, and `import-observations`
support those main workflows. The [documentation map](docs/index.md) links each
command guide.

## Evidence that does not fail open

A run keeps separate channels for:

- findings: a check reached a negative verdict;
- unverified results: the check ran but could not decide;
- errors: the check could not run;
- coverage shortfalls: policy-required evidence was unavailable, or a model file the
  scan observed was read by no rule that ran;
- assessments: what was measured, including passes.

Unknown counts and costs remain unknown rather than becoming zero. Exhausted
budgets, incomplete runs, unreadable artifacts, and incomparable baselines produce
explicit non-success exit codes; a crash exits `5` and an interrupt `7`. An unverified result is never weighed against a
severity bar: how bad an unmeasured thing is has no answer, so `fail_on_inconclusive`
governs all of them or none, and a check that went dark between two runs is a
regression at any severity. Saved runs carry versions, policy identity (the profile's digest),
target identity, the plugin trust in force, protocol versions, usage, redaction mode, rule
provenance, and for a file scan every file it listed and the excludes it applied with
their source. `diff` calls a finding resolved only where the second run listed its file;
one that was deleted, moved, renamed or excluded is a `left_scan` regression.
Usage keeps the judges configured under `evaluators:` on their own meters, apart from
the target. `guardana plan probe` prices those judge calls before the run, names what
it cannot price, and exits `3` when the target or a judge meter could exceed the
request budget, when no rule would run, when a rule it would skip or a calibration
file would stop the run, or when the run would record an error before its first rule.
The gate, the four output formats and `plan` decide from one list of open questions, so no
format renders clean a run the gate refused: no `✓`, a JUnit `<error>`, and SARIF
`executionSuccessful: false` with a notification naming the cause. A saved run over a trace
or an imported document records the SHA-256 of the bytes it read and whether that was the
whole file (`run.target.document`).

Repeated trials send the same case as independent, fresh requests without shared
conversation history or agent memory. Any failed attempt fails the case; if a grader
cannot decide and none fail, the case remains unverified. The report counts failed
attempts and gives a bound computed over cases, since attempts at one prompt are
correlated. See [repeated trials](docs/usage-probe.md#repeated-trials).

## Security coverage

### Build-time

The offline scanner parses Python and common AI artifact formats, including GGUF,
safetensors, ONNX, Keras, pickle-based checkpoints, notebooks, model configuration,
chat templates, dependency manifests, and agent rule files. Coverage includes:

- unsafe deserialization and dynamic code execution;
- model and dependency provenance risks;
- malicious or vulnerable AI/ML dependencies;
- chat-template and hidden-instruction payloads;
- hardcoded credentials and insecure transport;
- risky model graph, external-data, and format metadata;
- training-data hygiene and package-name leads.

### Runtime and recorded executions

Active and trace-backed checks cover:

- prompt injection, jailbreaks, secret leakage, and cost asymmetry;
- excessive tool use, over-broad arguments, credential exfiltration, and poisoned
  tool results;
- memory poisoning across sessions;
- live MCP manifests, authorization discovery, audience and session handling,
  scope breadth, discovery targets, issuer identification, and cache scope;
- recorded identity, consent, policy, approval, handoff, retrieval, credential,
  and side-effect boundaries;
- application-owned security contracts compiled into rules.

Every built-in rule id, severity, target, maturity, and framework mapping is in the
[generated rule catalog](docs/generated/rule-catalog.md).

## Evaluators

Built-in evaluators are:

- `keyword` for low-confidence refusal matching; in an agent run a final refusal after a reply without one is `inconclusive`;
- `canary` for deterministic planted-marker evidence in any reply under grade: every reply of an agent run or a whole conversation, and the replies a scenario step's grader has not read yet;
- `tool_call` for actions and decoded argument values over a trajectory, including an exact allowlist per tool and proof that a payload was delivered;
- `length` and `amplification` for resource-consumption signals;
- `llm_judge` for configurable semantic grading;
- `answered` for judging whether a reply refuses a benign task;
- `contains` for required or forbidden case-sensitive substrings; a forbidden one fails in any reply under grade;
- `exact_match` for comparison with a reference answer, with optional normalization;
- `json_valid` for valid JSON and optional required keys;
- `regex` for matching a bounded reply against a pattern; `must_match: false` fails in any reply under grade;
- `reference_judge` for grading against a reference answer with a versioned rubric;
- `guard` for an optional external safety classifier, given every reply under grade in one call.

`guardana calibrate` measures evaluator confidence against labelled samples, including
per-class sensitivity and specificity. A run can carry a corrected trials rate when its
recorded calibration qualifies. `reference_judge` uses the configured `llm_judge`
connection, but its own evaluator id requires its own calibration; `llm_judge`
calibration does not apply to it. A third-party evaluator declares the fields it needs,
and malformed configuration is rejected before a run starts.

## Quality suites

A quality suite is a declarative rule that grades a versioned JSONL dataset the team supplies against a chat endpoint before release or in CI. Guardana does not read production traffic.

Each case runs for the configured `trials` or `probe --trials`. The suite records an assessment for every trial, including passes, and gates on the mean pass rate over cases.

The gate passes, fails, or declines when it cannot conclude. Judge-graded suites use a qualifying calibration to correct the pass rate; without one, they decline. Judge-graded suites and judge-error correction are experimental. A failed suite yields at most one finding, about the rate.

Saved runs retain the suite summary. Human reports show a Measured block, and JUnit emits one testcase per suite. See [Quality suites](docs/usage-suites.md) for the how-to.

## Policy and repeatability

`guardana.yaml` selects rules, severity thresholds, evaluator settings, budgets,
required evidence, and redaction. Built-in presets cover CI, pre-training,
monitoring and release gates; `release` also fails when a selected check is skipped or
reaches no verdict. Baselines are explicit, fingerprinted, and can expire; comparisons
refuse changes that make the evidence incomparable.

Rules map to versioned OWASP LLM, OWASP Agentic, OWASP MCP, OWASP ML, MITRE ATLAS,
and NIST AML references. `guardana taxonomy` resolves editions and crosswalks
without guessing from a short id.

## Integrations and packaging

- Python 3.11–3.13 and five separately installable distributions.
- A SHA-pinned GitHub Action and generic JSON, SARIF, JUnit, and human output.
- CI examples for GitHub, GitLab, Jenkins, and Azure DevOps.
- Multi-architecture CLI and collector containers.
- OpenTelemetry GenAI input plus LangChain, Pydantic AI, OpenAI Agents, Hermes,
  and shell-hook integration examples.
- No account and no telemetry; an artifact scan opens no network connection unless a `--reporter` is configured.
- JSON Schemas for saved runs, plans, comparisons, and traces, served at the URL each
  `$id` names under `https://guardana.dev/schemas/`.

## Extension surface

Third-party packages can provide rules, evaluators, targets, and taxonomies
through Python entry points. Every command starts with Guardana's own distributions
only: an installed pack is refused before it is imported, the refusal leaves a run
`indeterminate`, and the pack is admitted by name (`--plugins allowlist
--allow-plugin`, or `plugins:` in a profile). `guardana doctor` lists what an installed
pack would execute without importing it. YAML rules cover `prompt`, `scenario`, and `agent`
endpoint shapes, and every shape can declare the finding, clean, and inconclusive
samples that `guardana rule test` runs without a network. A rule declares whether a finding
is a checked fact or a lead (`detection:`), and the generated
[detection limits](docs/generated/detection-limits.md) page lists every built-in by family
beside the framework entries it is only mapped to. `guardana new-pack` writes a complete pack —
manifest, entry points, one sampled rule per shape, a locator target and tests — that
passes `pack validate` and `rule test` before it is edited. Pack manifests declare API
compatibility and locks pin the exact installed extensions.
The shipped conformance helpers verify capability claims and fail closed on an
incomplete implementation.

The extension API remains pre-1.0; compatibility guarantees are described in
[Product status](docs/product-status.md) and the path to stability in
[ROADMAP.md](ROADMAP.md).

## Optional collector

`guardana-server` accepts redacted run envelopes and can provide:

- PostgreSQL persistence and reversible migrations;
- organization/project tenancy, with optional environment-pinned keys;
- scoped, hashed, revocable, and expiring API keys;
- run and finding history, lifecycle states, expiring waivers, and audit events;
- retention and deletion commands, backup/restore checks, health, and readiness;
- a read-only dashboard authenticated with a read-scoped session.

The collector is optional. Local and CI verification do not depend on it. It does
not yet provide quality-assessment trends, human SSO/RBAC, or a supported
Kubernetes deployment; those remain roadmap work.

## Safety boundaries

Guardana never executes a tool offered to a model. Active checks still send real
requests and can cost money or trigger a model's surrounding application, so they
are opt-in, budgeted, and documented for staging use. See
[Safe testing](docs/safe-testing.md), [Privacy](docs/privacy.md), and the
[Threat model](docs/threat-model.md).
