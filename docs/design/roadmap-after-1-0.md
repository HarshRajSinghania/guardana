---
title: "Roadmap after 1.0: evidence before expansion"
nav_order: 95
summary: "A proposed evidence plan for reaching 1.0 and sequencing 1.x without weakening the release criteria."
status: proposed
---

# Roadmap after 1.0

**Status:** proposed · **Written:** 2026-10-06

## Baseline: evidence required before proposals

“Not measured” means the required external observation has not been recorded. It does not mean the gate passed.
Counts below come from generated measures and maintainer records, not inferred use.

| Gate | Recorded baseline | Completion evidence | Owner and source |
|---|---|---|---|
| F2 first run | **0/5** consented sessions; completion and time **not measured** | At least four of five people new to Guardana finish the failure, fix, saved evidence, and edited check within ten minutes without maintainer help. The observed task can continue to 30 minutes. Record consented CSV rows. | Maintainer; [study](../maintainers/first-run-study.md), [CSV](../maintainers/first-run-study.csv), [generator](../../scripts/first_run_measure.py), [generated measure](../generated/first-run.md). |
| F6 independent applications | **0/2** independent teams; application measures **not measured** | Each team locks an application recipe, saves a failed and an incomplete run, turns a redacted case into a versioned case, regrades it, and gates it in CI. One retrieval pilot uses the team's own target to expose a poisoned document and a tenant-filter failure without an uncontrolled side effect. Keep saved runs with teams and publish consented counts. | Maintainer and each team; [study](../maintainers/adopter-study.md), [CSV](../maintainers/adopter-runs.csv), [generator](../../scripts/adopter_measure.py), [generated measures](../generated/application-measures.md), [reference pilot test](../../examples/retrieval_pilot/tests/test_reference_application.py). The team's own target remains untested. |
| Third-party customization | **0 recorded**; success **not measured** | An external author independently installs a pack and successfully customizes a check or output using public extension and output contracts. Keep a redacted, consented field note. | Maintainer and external author; [conformance kit](../conformance-kit.md), [reference-pack tests](../../examples/reference_pack/tests/test_reference_commands.py), and the field note. No external customization generator exists. |
| Security runbook drill | **0 recorded** | Date the real steps exercised in `docs/maintainers/drills.md`; identify skipped and simulated steps explicitly. Running `scripts/check_repo_settings.py` or reading `security-runbook.md` is not a drill. | Maintainer; [drills](../maintainers/drills.md), [security runbook](../maintainers/security-runbook.md). |
| Reference pack | GitHub Release attachment published; **0 verified installs from a released wheel**; PyPI absent. Conformance kit published. | Independently install the released wheel and record the result. Accepted [1.0 readiness](one-zero-readiness.md), decision 11, treats criterion 3 as met only when the pack is on PyPI. A release workflow or isolated CI source install does not establish that result. | Maintainer; [release workflow](../../.github/workflows/release.yml), [isolated source tests](../../examples/reference_pack/tests/test_reference_commands.py), [release guide](../../RELEASING.md), [1.0 readiness](one-zero-readiness.md). |

The attachment is “published” in ordinary language. Under the accepted 1.0 criterion interpretation, the pack remains partial until PyPI publication and an independent released-wheel install.
On 2026-10-06, the [rc1 release](https://github.com/guardana/guardana/releases/tag/v1.0.0rc1) listed the `guardana_reference_pack-0.1.0-py3-none-any.whl` asset, while the [PyPI project JSON endpoint](https://pypi.org/pypi/guardana-reference-pack/json) returned HTTP 404. This verifies distribution state, not successful independent installation.
The owner may explicitly supersede that interpretation. The recommendation here is to keep it.

The local audit input `cache/audit-2026-10-06/priorities-final.md` mixes verified findings with model findings and partial checks.
Treat its verified findings as verified; treat its remaining findings as hypotheses until reproduced.
Neither a backlog entry nor an accepted design is evidence that a user needs a new feature.

## Decision and constraints

**Research question:** How does Guardana reach 1.0, then sequence 1.x, without eroding the bar?

This document recommends a sequence. [ROADMAP.md](../../ROADMAP.md) links this proposal and makes M1 and M3 starts conditional; it does not set a release date or record an owner decision.
The maintainer decides release criteria and priorities using the evidence recorded below.

The audited baseline was `9bab2cf2`; subsequent fix commits have reached main. `1.0.0rc1` was released on 2026-10-05; `0.41.0` is the stable release.
The earliest `rc2` is 2026-10-19 at 09:07 UTC. It carries fixes only: no features, fields, documentation-generated surface movement, or `api-surface.json` movement.
No new features or fields enter the release candidates before 1.0.
Q1 2027 remains a target, not a promise. See [ROADMAP.md](../../ROADMAP.md).

An unavailable check, ungraded case, partial run, or invalid comparison must not become a pass.
All engine capabilities and built-in rules stay open. Offline use needs no telemetry or account.
Traffic to a target, judge, or chosen destination must be explicit and bounded.
Every built-in rule needs a public taxonomy mapping that states relevance; a mapping does not establish coverage.
Company usability comes before adding coverage for its own sake.
Law, vendor integrations, and changing formats belong in data or adapters where possible, rather than core verdict logic.

Guardana Control is independent. It owns the production request path and live telemetry.
Guardana's saved local evidence and optional collector remain useful without Control.
A format bridge, if needed, belongs on the Control side; Control must not become a Guardana dependency.

## Eight-week evidence plan

These are planning durations, not observed session counts or timings.
Invite maintainers of LLM, MCP, and RAG applications directly and with regard for privacy.
Use professional open-source communities, GitHub Discussions, technical contacts, and non-core teams.
Avoid mass outreach and telemetry. Record invitation, acceptance, consent, and completion counts each week without identifying people publicly.

Allow each F2 participant an observed task capped at 30 minutes, plus roughly 3–5 minutes for consent.
Allow each pilot team 60–90 minutes for setup, 30–45 minutes for review and interview, and, if needed, a 30-minute follow-up.
Allow a third-party author roughly 45–90 minutes. These estimates plan recruitment capacity; they are not findings.

The existing [first-run consent](../maintainers/first-run-study.md) and [adopter consent](../maintainers/adopter-study.md) need `[STORAGE]` and `[RETENTION]` filled before use.
Ask separately before quoting a participant or recording a screen.
Correct the F2 statement “Guardana sends nothing anywhere” to describe the offline starter only, as the documented `rc2` wording correction.
Use analogous explicit consent for customization; no customization consent template currently exists.

Teams keep their saved runs, prompts, findings, secrets, and target addresses.
A team sends only its `adopter_measure.py row` output after consent.
Use safe fixtures and doubles where appropriate; the required retrieval check still runs against the team's own target without an uncontrolled side effect.
Do not publish raw prompts, findings, or target addresses.

| Week | Checkpoint and record |
|---|---|
| 1 | Fill consent storage and retention fields; correct F2 consent wording; prepare a short invitation and recruitment log. Record invite, accept, consent, and complete counts. |
| 2 | Recruit F2 participants and pilot teams; dry-run instructions without counting maintainer runs as external evidence. Record defects and unresolved setup barriers. |
| 3 | Run early F2 sessions with new users. Record timings and help exactly as the study requires; fix reproduced first-run defects within release rules. |
| 4 | Finish recruitment toward five F2 sessions; begin locked application setup with the first independent team. Review consent and data boundaries. |
| 5 | Run the first team's failed and incomplete cases, redacted regression loop, and local review. Record its row only after consent. |
| 6 | Run the second team's loop and the retrieval checks on a team's own target. Record missing checks and side-effect controls, including failures. |
| 7 | Ask an external author to install the released reference wheel and customize through public contracts. Record the outcome, including unsuccessful attempts. |
| 8 | Generate F2 and F6 measures from consented sheets; record the security drill and pack install evidence; audit every 1.0 criterion and decide the next candidate. |
| 9–10, if needed | Complete missing sessions or repeat a failed setup after a documented fix. Preserve earlier failures and the reason for the extension. |

Every checkpoint records counts, defects, and withdrawals. None supports an adoption claim.
If recruitment falls short, widen the stated channels and reschedule.
Maintainer runs, demonstrations, and repository traffic cannot substitute for independent sessions or teams.

[GitHub Insights traffic](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository) and the [REST traffic views and clones endpoints](https://docs.github.com/en/rest/metrics/traffic) report a 14-day UTC window.
GitHub labels these as unique counts without exposing the identities behind them; its clone traffic concerns full clones, not fetches.
They provide neither participant identity nor evidence of installation, use, or adoption.

## If the Q1 target slips

| Option | Cost and effect | Recommendation |
|---|---|---|
| Keep the criteria; release `rcN` with fixes only | More release overhead and a later stable date. External evidence remains comparable to the stated bar. | **Recommended.** Record the unmet criterion and new target date. |
| Design 1.1 privately while `rcN` continues | Branch divergence, migration and backport work, and contract drift. Design can proceed offline; do not publish 1.1 before 1.0. | Use only if the maintenance cost is explicit. |
| Change a 1.0 criterion explicitly | Trust cost, an accepted design and ROADMAP supersession, and reduced comparability with earlier measurements. | Consider only if the owner has new evidence, not because a deadline arrived. |

The owner makes the release decision.
This proposal recommends keeping the pack criterion's accepted PyPI interpretation and the external evidence bar.

## Three jobs users may already solve elsewhere

The linked primary product and project sources below are treated as read on 2026-10-06.
They establish the cited capability, not its effectiveness for a Guardana pilot or the absence of other capabilities.
Guardana's intended distinction is a workflow: carry missingness through plan, gate, saved run, diff, and export.
That is a proposed position, not a claim of uniqueness.

### Job A: gate an LLM or MCP application in CI

[promptfoo's GitHub Action](https://www.promptfoo.dev/docs/integrations/github-action/) describes before/after evaluations in CI; its [MCP provider](https://www.promptfoo.dev/docs/providers/mcp/) provides an MCP test route.
[garak's CLI reference](https://reference.garak.ai/en/stable/cliref.html) describes scanner probes and detectors.
[PyRIT 1.1.0, released 2026-09-04](https://github.com/microsoft/PyRIT/releases/tag/v1.1.0), describes scanner and undetermined scores.

[mcp-scan documentation](https://github.com/invariantlabs-ai/docs/blob/main/docs/mcp-scan/index.md) describes scanning file-based client configurations, tool poisoning, pinning, and a runtime proxy.
[Giskard's quickstart](https://docs.giskard.ai/en/latest/getting_started/quickstart/quickstart_llm.html) takes a RAG scan into tests.
[NeMo Guardrails documentation](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/configure-rails) describes inline input, output, retrieval, and tool rails.

[llm-guard's quickstart](https://github.com/protectai/llm-guard/blob/main/docs/get_started/quickstart.md) describes input and output scanners as a library.
Its [repository](https://github.com/protectai/llm-guard) was archived on 2026-07-09.
These tools occupy different parts of testing and runtime workflows; the cited pages do not justify a claim that any one lacks another capability.

### Job B: scan a model file

[ModelScan](https://github.com/protectai/modelscan) describes scanning serialized model files including H5, Pickle, and SavedModel.
[promptfoo ModelAudit's scanner list](https://www.promptfoo.dev/docs/model-audit/scanners/) describes a broader set of scanner types as read on 2026-10-06; this is no historical comparison.
Expand model-file handling only when a pilot supplies a relevant sample and a reproducible gap.

### Job C: review an agent regression

[Inspect tasks](https://inspect.aisi.org.uk/tasks.html) use dataset, solver, and scorer components, and [Inspect scoring](https://inspect.aisi.org.uk/reference/inspect_score.html) can re-score a saved log.
The [promptfoo Action](https://www.promptfoo.dev/docs/integrations/github-action/) supports CI evaluation; the [Giskard quickstart](https://docs.giskard.ai/en/latest/getting_started/quickstart/quickstart_llm.html) describes a scan-to-tests path.
[PyRIT 1.1.0](https://github.com/microsoft/PyRIT/releases/tag/v1.1.0) includes undetermined scores.
Guardana should test whether teams value its intended continuity from incomplete observation to a reviewable ship decision.

## Standards and formats to track

These editions and dates are supplied source facts as read on 2026-10-06.
A public taxonomy mapping records why a built-in rule is relevant; it does not claim full framework coverage or certification.
Put changing legal, vendor, and format identifiers in versioned data and documentation where possible.

| Authority, edition, date | Scope or jurisdiction | Relevance to Guardana | Response in data, docs, or code |
|---|---|---|---|
| [OWASP LLM Top 10 for 2026](https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/), announced 2026-09-02 in an article dated 2026-09-01 | LLM application security guidance; international project | Public vocabulary for applicable checks | Version the taxonomy mapping in data; explain unmapped and untested areas in docs. |
| [OWASP Agentic Applications Top 10 for 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/), published 2025-12-09 | Agentic application security guidance; international project | Agent and tool risk vocabulary | Map each applicable built-in with edition and rationale; do not equate mapping with coverage. |
| [MITRE ATLAS data releases](https://github.com/mitre-atlas/atlas-data/releases): content `v2026.09` on 2026-09-15; format `v5.6.0` | International adversarial AI knowledge base | Techniques and provenance may change separately from file structure | Pin content and format versions separately; test positive and negative mapping fixtures. |
| [NIST AI RMF 1.0](https://www.nist.gov/itl/ai-risk-management-framework), 2023-01-26, and [GenAI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence), 2024-07-26 | Voluntary US framework with international use | Context for evidence, governance, and uncertainty | Document relevance and limits; make no compliance claim from a scan. |
| [EU AI Act, Regulation 2024/1689 as amended by 2026/1744](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ%3AL_202601744); [Commission overview](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) | EU; GPAI 2025-08-02, general 2026-08-02, Annex III high-risk 2027-12-02, Annex I high-risk 2028-08-02 | A user's obligations depend on role and use; Guardana is not automatically a provider or deployer | Date and scope documentation; no certification or automatic compliance claim. |
| [ISO/IEC 42001:2023](https://www.iso.org/standard/42001), published December 2023 | Voluntary international AI management standard | Organizational management context | Document possible evidence exports without claiming certification. |
| [MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) and [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) | Protocol editions | Existing probe interoperability and explicit edition handling | Keep conformance fixtures and edition data; add protocol code after 1.0 only for an observed interoperability failure, with a versioned contract. |
| [A2A v1.0.0](https://github.com/a2aproject/A2A/releases/tag/v1.0.0), published 2026-03-12 | Agent protocol | Existing A2A probe and possible trust checks | Keep conformance evidence; add optional signature support only after a demonstrated trust gap and contract review. |
| [OpenTelemetry GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md), in development as of 2026-10-06 in a split repository | Developing telemetry format | Potential imported evidence | Treat as an input adapter, never Guardana's storage contract; preserve missing fields and source version. |

## Conditional starts after 1.0

**M1, paired statistical diff.** Start only after at least two independent pilot teams each use local `diff` on comparable saved before/after application runs to make a documented ship decision, and one asks for uncertainty because descriptive counts are insufficient.
Record case and grader identity and the denominator before designing an inference.
Do not promise statistical power or a sample size before the observed cases support a power plan.
Version the comparison and grading identity contract; retain refusal when comparison is invalid.
This threshold is proposed, not observed.

**M3, collector measurements.** Start only after at least two teams submit and read their own locked application runs in the optional collector and each asks the same cross-run question that local files cannot answer.
Version the collector envelope and storage together, enforce tenancy, and show missingness and unknowns in the answer.
Do not build an arbitrary dashboard to discover the question.
This threshold is proposed, not observed.

**B12, non-executing packs.** The [accepted design](non-executing-packs.md) commits to a parallel lane after F2, but remains unimplemented. The 1.0 surface freeze places any implementation in 1.x.
This research proposes deferring implementation until at least one team shares a local YAML check across projects and reports Python packaging or trust friction. That would change the accepted timing; the owner must decide and record a superseding design before moving B12 in ROADMAP.
The accepted design calls its new entry-point group a fifth group, but the frozen surface now has six; it would be a seventh group. Its manifest and lock version changes and data-only import path need a revised contract design and conformance checks proving no third-party code executes. Acceptance of the design is not user-demand evidence.

For the next application target, keep one candidate: a multi-step agent and tool workflow with synthetic fixtures, if a pilot reports that pain.
Do not select it now. Expand model-file scanning only if a pilot supplies a sample.
Schedule synthetic monitoring after repeated alert pain; expose Prometheus only for named measurements.
Distribute signed central policy after local recipe reuse, and profiles in packs after shared-check demand.

Keep optional A2A signature verification with its JOSE extra behind an observed trust gap.
Derive agent provenance fields from pilot evidence.
Define imported-evidence quality only after a real import request.
Consider OIDC, SSO, and Helm when collector teams ask for them.
These remain unordered candidates, not 1.0 work or an ordered 1.x queue.

## Front page and documentation sequence

The local audit input `cache/audit-2026-10-06/priorities-final.md` verifies copyable shell and YAML defects, the clipped `scan .` command at 390 px, source-first installation advice, and unsafe deployment, writing-rules, and CI examples.
Correct those for `rc2` within its fixes-only constraint.
The study consent correction belongs there too.

Before 1.0, test a visible starter, an RC label, mobile navigation and code/table readability, a three-step [docs index](../index.md), and a result glossary as F2 barrier candidates.
Promote a candidate to a release fix when a user study confirms it or a direct reproduction establishes the defect.
Audit items marked as partial or model findings remain hypotheses until checked.

After 1.0, consider shortening the hero, a careful comparative line, a simpler Control section, and diagram polish.
A confirmed contrast accessibility defect is a defect to fix, not cosmetic work.
The commercial boundary in product principle 4 remains: open engine and built-in rules, with paid hosting or curated content only.
Control's separate live runtime role does not change that boundary.

## Candidate rubric for later ordering

“Not observed” below is a statement about pilot pain, not a negative user finding.
Costs are qualitative planning estimates. Every start needs the stated evidence and an acceptance check before a roadmap move.

| Candidate | Observed pilot pain | User value if confirmed | Evidence quality now | Implementation and maintenance cost | Versioned contract and acceptance | Defer condition |
|---|---|---|---|---|---|---|
| M1 paired diff | Not observed | Qualified uncertainty for a ship decision | Existing design, no qualifying team requests | High: statistical and grading maintenance | Comparison, case, and grader identity; refuse incompatible or underpowered claims | Fewer than two qualifying teams or no uncertainty request |
| M3 collector measurements | Not observed | Answer a repeated cross-run question | Existing collector, no qualifying question | High: tenancy, storage, query semantics | Envelope and storage versions; preserve unknowns and tenant isolation | Fewer than two qualifying teams or local files answer the question |
| B12 data-only packs | Not observed | Share checks without executing author code | Accepted design, no pilot demand | Medium to high: entry point, manifest, lock, conformance | Version manifest and lock; prove data-only import and independent install | No shared YAML check with reported packaging or trust friction |
| Agent/tool application target | Not observed | Test a real multi-step workflow safely | Candidate only | High: fixtures, adapters, side-effect controls | Target and fixture contracts; reproduce a pilot failure with synthetic fixtures | No pilot pain |
| Imported-evidence quality | Not observed | Make imported observations reviewable | Candidate only | High: source trust, missingness, comparability | Version import and quality record; refuse unsupported local-regression promotion | No real import request |
| Site and docs adoption repairs | Verified defects plus unverified barrier candidates | Help a new user reach the first result | Direct reproductions for defects; F2 pending for barriers | Low to medium; ongoing content checks | Copyable examples and documented CLI behavior; F2 completion check remains unchanged | Barrier changes without reproduction or study signal |
| Prometheus reporter | Not observed | Export named measures | Candidate only | Medium: metric stability and unknowns | Version output mapping; verify named measures and missingness | No team names measures |
| Central signed profiles and policy | Not observed | Reuse governed local recipes | Candidate only | High: trust, signatures, rotation | Version policy, lock, and signature format; verify local reuse first | No repeated local recipe use |
| Profiles in packs | Not observed | Distribute requested shared profiles | Candidate only | Medium: pack and profile migrations | Version manifest and profile schema; conformance fixtures | No shared-check demand |
| Scheduled synthetic monitor | Not observed | Catch recurring regressions | Candidate only | High: alert semantics and operations | Version alert and schedule records; test repeat alert need | No repeated alert pain |
| A2A signature extra | Not observed | Verify agent-card trust when required | Candidate only | Medium: JOSE and protocol maintenance | Optional extra and trust result; conformance with cited edition | No observed trust gap |
| Agent provenance | Not observed | Explain tool and server identity | Candidate only | Medium to high: identity sources | Version provenance fields and unknown states | No pilot source for the fields |
| OIDC/SSO and Helm | Not observed | Fit collector team operations | Candidate only | High: auth and deployment support | Version roles and deployment migrations; exercise recovery | No collector team demand |
| Model artifact hardening | Not observed in a Guardana pilot | Clearer artifact risk reporting and fewer missed scans | Public upstream advisory and unconfirmed scanner issues; no Guardana failing case | Medium to high: format, sandbox, and review costs | Review versioned input and result contracts; reproduce a failing artifact and specify acceptance | No pilot pain, failing case, or acceptance criterion |
| Agent action chain | Not observed in a Guardana pilot | Assess whether injected content steers tool actions | Public issue and anecdote; no Guardana pilot trace | High: fixtures and integration costs | Review versioned action and outcome contracts; reproduce a tool-use failure and specify acceptance | No pilot pain, failing case, or acceptance criterion |

## Options and owner questions

| Option | 1.x ordering rule | Consequence |
|---|---|---|
| Evidence-gated sequence, recommended | Keep M1 and M3 conditional; rank remaining candidates after pilot records | Limits contract growth while 1.0 evidence is gathered |
| Contract-first design only | Draft schemas and conformance fixtures without publishing a feature | May reduce later design time; risks work on unused paths |
| Broad feature queue | Put several candidates into Now before pilot evidence | Higher maintenance and contract cost without a demonstrated user job |

The owner needs to decide whether the accepted PyPI interpretation of criterion 3 stands, which F2 barriers warrant immediate fixes after reproduction, and whether either M1 or M3 has met its proposed start threshold.
Record any changed criterion or priority in an accepted design and ROADMAP before treating it as a release decision.

## Sources and limits

Local baseline and criteria: [ROADMAP.md](../../ROADMAP.md), [1.0 readiness](one-zero-readiness.md), [direction audit](audit-0.31-direction.md), [product status](../product-status.md), [features](../../FEATURES.md), [lessons](../maintainers/lessons.md), [first-run measure](../generated/first-run.md), [application measures](../generated/application-measures.md), [drills](../maintainers/drills.md), and [non-executing packs](non-executing-packs.md).
Local audit records: `cache/audit-2026-10-06/A.json` through `E.json`, `priorities.md` and `priorities-final.md`, supplied locally and not tracked in this repository.
External primary links appear beside each capability, standard, or traffic claim above; their stated reading date is 2026-10-06.
No usage, effectiveness, legal compliance, or adoption result is inferred from those links.

## Public defect discussions and the 2.0 horizon (2026-10-06)

This is a bounded, non-exhaustive sample of public discussions from Reddit, GitHub issues and advisories, X search results, the Hugging Face forum, and Hacker News, read on 2026-10-06. Reports and questions below suggest cases to investigate; they do not establish that every alleged issue is verified or affects Guardana.

**Prompt injection and agent action.** A [2026-02-07 Reddit account](https://www.reddit.com/r/LocalLLaMA/comments/1qyljr0/prompt_injection_is_killing_our_selfhosted_llm/) (firsthand anecdote/question) says a QA prompt injection exposed a self-hosted application’s system prompt. An [MCP specification issue opened 2026-08-07](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3213) (unconfirmed issue/PoC) alleges that `server/discover` instructions, amplified by a public cache, can inject instructions; its submitted PoC was not independently reproduced here. A [2025-04 Hacker News discussion](https://news.ycombinator.com/item?id=43601653) (secondary signal) records a researcher’s concern about MCP tool poisoning, rather than a verified Guardana defect.

**RAG isolation.** A [2026-06-05 Reddit question](https://www.reddit.com/r/LocalLLM/comments/1txf6sx/auditing_a_custom_rag_system_looking_for/) (question, not a defect report) seeks methods for testing cross-user document leakage; it reports no observed exploit. [FEATURES.md](../../FEATURES.md) documents F6’s poisoned retrieval document and tenant-boundary checks on the reference app. The team-owned retrieval pilot has not yet been measured.

**Model artifact execution.** A [2026-06-10 Hugging Face forum question](https://discuss.huggingface.co/t/how-to-ensure-safe-usage/176678) (question, not a defect report) asks how an administrator can prevent accidental loading of malicious models. [ModelScan issue #354, opened 2026-06-21](https://github.com/protectai/modelscan/issues/354) (unconfirmed issue/PoC), remains open and reports a corrupt ZIP entry that skips a later `archive/data.pkl` and returns zero issues; its PoC was not independently executed here. [ModelScan issue #343, opened 2026-05-12](https://github.com/protectai/modelscan/issues/343) (unconfirmed issue/PoC), remains open and alleges a Keras Lambda detection bypass while withholding details. The [diffusers advisory published 2026-05-20](https://github.com/huggingface/diffusers/security/advisories/GHSA-7wx4-6vff-v64p) (confirmed advisory) describes an upstream `trust_remote_code` time-of-check/time-of-use bypass affecting versions below 0.37.1 and patched in 0.38.0. These concern tooling that handles model artifacts, not a model’s behavioral defect. Guardana already supports model formats, but has no comparative coverage proof across them.

**False-green scoring and scanning.** [PyRIT issue #2658, opened 2026-09-14](https://github.com/microsoft/PyRIT/issues/2658) (unconfirmed issue/PoC), remains open and reports an undetermined aggregate becoming `FAILURE`; it was not reproduced here. [promptfoo issue #5080, opened 2025-07-28](https://github.com/promptfoo/promptfoo/issues/5080) (unconfirmed issue report), is closed and reported a critical raw finding alongside a green summary and UI in version 0.117.3; this says nothing about the current release. Guardana already documents explicit inconclusive results, errors, and coverage shortfalls.

X searches found one relevant [2026-03-24 AISecHub security-skill post](https://x.com/AISecHub/status/2036419023592690109) (promotional signal), but no independently verifiable defect report in the inspected results. X is not a comprehensive corpus.

These observations can inform pilot interview questions and synthetic fixtures. [The broader security research horizon](two-zero-horizon.md) compares advisories, behavioral research, incident reports, public discussions, and current competitor documentation. Model artifact hardening and agent action chains remain candidate rows in the rubric above. Moving either to Now requires pilot pain, a reproducible failing case, an acceptance criterion, and a versioned contract review. **2.0 has no version plan, date, or commitments.** Demonstrated incompatible contract changes or multi-team needs might eventually justify it, with an explicit migration path and assessed costs. The 1.x M1/M3 gates remain conditional, and Later remains unordered.
