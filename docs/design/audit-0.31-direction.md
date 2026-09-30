---
title: "Direction audit after 0.31"
nav_order: 220
summary: "The roadmap checked against a year of standards, protocol and market movement, and the product against the extension models of garak, PyRIT, promptfoo, Inspect AI and DeepEval: the order that follows, and why"
status: accepted
---

# Direction audit after 0.31

**Status:** accepted · **Written:** 2026-09-30 · **Supersedes the order in:**
[`framework-usability-audit.md`](framework-usability-audit.md), whose evidence stands

## Decision

Keep the direction: an offline-first verifier outside the production request path. Its
distinction is not attack volume or format count but missing evidence carried honestly through
a plan, a gate, a saved run, a comparison and an export, with bounded cost, calibrated grading
and locked packs. Change the order of the milestone so that it is protected first and the
user's actual application becomes the acceptance test sooner:

1. **Q1 — evidence and gate integrity.** Small, and each item is a place where a report can say
   more than it established.
2. **F2 — first result and one custom check**, starting with built-in trust only.
3. **F3 — the supported Python data workflow.**
4. **F5 — recorded-answer grading and regrading**, ahead of output plugins: it replays a real
   failure cheaply and separates execution identity from grading identity, and regrading on its
   own is no longer distinctive.
5. **F6 — reproducible team checks on the real application**, absorbing M2 (provider and
   application conformance) and M4 (evidence to regression), with one live retrieval pilot.
6. **F7 — protocol and evidence conformance** (new): both current MCP revisions against
   independent servers, and one A2A v1 fixture.
7. **F4 — narrowed** to one redacted local export and one webhook that reports its delivery
   status; the general renderer and reporter plugin contract waits for a team that needs more.

"Next" keeps M1 after the F5–F6 evidence workflow and M3 after two teams have reproduced and
consumed local results. A public extension-ID service is dropped. ATLAS provenance, fixture
expressiveness and a decision on non-executing declarative packs move up in the parallel lane.
The milestone gains three published measures in place of counts of formats and attacks.

## How this was produced

Two questions went to GPT through the codex CLI on 2026-09-30, one call each, with live web
search and a read-only checkout: does the roadmap still point the right way, and does the
product still meet the bar for quality and extensibility. Before anything was adopted, the
repository claims were checked against the code:

| Claim | Checked | Outcome |
|---|---|---|
| JUnit renders a budget-stopped run as a clean suite | reproduced: `tests="2" failures="0" skipped="0" errors="0"` | fixed in 0.31.0 |
| `writing-rules.md` calls a raised `RuleLoadError` a skip | the runner records it in `errors` | corrected in 0.31.0 |
| `architecture.md` lists no `TargetKind.TRACE` | the enum has it | corrected in 0.31.0 |
| a trace's `document_digest` identifies name and size, not content | `core/trace/load.py::_size_and_name` | Q1 |
| three-outcome fixtures cover 12 of 51 built-ins | `test_builtin_fixture_coverage.py` | parallel lane, 1.0 criterion |
| no strict preset; `fail_on_inconclusive` and `fail_on_skipped` default off | `core/profile/model.py` | Q1 |
| generated-documentation checks run only locally | **refuted**: pytest runs every generator's `--check` (`test_generated_truth_is_current`) and `build_site.py --check`, and CI runs pytest | not adopted |

The external claims below carry their sources and were not independently re-verified. The two
unedited reports were kept in `docs/work/` until this decision and remain in git history
(`e5ef4998`).

## What moved in a year

- **OWASP LLM Top 10 2026**, announced 2026-09-02: Excessive Agency rose to LLM03, Unbounded
  Consumption to LLM06, and prompt injection names image and audio carriers. Guardana maps both
  editions and tests text only. [announcement](https://genai.owasp.org/2026/09/01/owasp-genai-security-project-unveils-2026-top-10-for-llm-applications-new-agent-control-standard-and-sponsors-as-community-tops-30000-members/)
- **OWASP Top 10 for Agentic Applications**, 2025-12-09. Built-in rules map eight of its
  entries and none to ASI08 or ASI10; a mapping is relevance, not coverage.
  [list](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- **OWASP AI Testing Guide v1**, 2025-11-26: a technology-neutral testing method that supports
  application-owned quality criteria outside any security taxonomy.
  [guide](https://owasp.org/projects/ai-testing-guide)
- **MITRE ATLAS** moved to monthly content releases, separate from the data-format version:
  v2026.07 split tool poisoning, v2026.08 added agent communication and authority-expansion
  mitigations, v2026.09 shipped 2026-09-15. Guardana's catalogue records v5.6.0, a format
  release. [releases](https://github.com/mitre-atlas/atlas-data/releases)
- **EU AI Act**: obligations for providers of general-purpose AI models since 2025-08-02, the
  Commission's enforcement powers since 2026-08-02. Traceable evidence is useful; certification
  stays a non-goal. [obligations](https://digital-strategy.ec.europa.eu/en/factpages/general-purpose-ai-obligations-under-ai-act)
- **MCP 2025-11-25** added tasks, URL-mode elicitation and authorization extensions; **MCP
  2026-07-28** removed protocol-level sessions, introduced `server/discover`, hardened issuer and
  credential handling and moved Tasks to an extension. Guardana negotiates both revisions
  already; what is missing is conformance against independent servers.
  [2025-11-25](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/),
  [2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **A2A v1.0.0**, 2026-03-12, is specific enough for one agent-card, caller-identity and
  task-visibility fixture. [release](https://github.com/a2aproject/A2A/releases/tag/v1.0.0)
- **OpenTelemetry GenAI conventions** moved to their own repository and remain at Development
  status: an input format behind an adapter, never Guardana's storage.
  [status](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md)
- **Evaluation and scanning became commodities.** Promptfoo open-sourced ModelAudit
  (2026-03-10; pickle, safetensors, GGUF, ONNX, Keras, SARIF, SBOM) and announced an agreement to
  be acquired by OpenAI (2026-03-09; completion not verified). Inspect re-scores saved logs.
  PyRIT v1.1.0 (2026-09-04) added an undetermined score. garak v0.17.0 added EU AI Act mapping.
  [ModelAudit](https://www.promptfoo.dev/blog/open-sourcing-modelaudit/),
  [Inspect](https://inspect.aisi.org.uk/reference/inspect_score.html),
  [PyRIT](https://github.com/microsoft/PyRIT/releases/tag/v1.1.0),
  [garak](https://github.com/NVIDIA/garak/releases/tag/v0.17.0)
- **Security vendors consolidated** into runtime and agent products: Palo Alto Networks and
  Protect AI (2025-07-22), Check Point and Lakera (2025-10-22), Zscaler and SPLX (announced
  2025-11-03), Snyk and Invariant Labs with mcp-scan (2025-06-24); HiddenLayer and Cisco moved
  into agent runtime. The runtime lane belongs to Guardana Control, not here.

Inference: regrading, model-file scanning, SARIF output and attack libraries are no longer a
reason to choose Guardana, and "unknown is not pass" on its own is no longer unique (PyRIT and
Inspect have unscored states). What stays distinctive is carrying missingness through every
channel together, and the plan has to protect exactly that.

## Roadmap decisions

| Item | Decision | Reason |
|---|---|---|
| F2 first result | keep first after Q1; built-in trust by default | a no-account offline start must not import code the user never meant to trust |
| F3 Python workflow | keep | typed results on failure are the core of the distinction and feed F5 and F6 |
| F4 output plugins | narrow and move last | JSON, JUnit and SARIF ship; demand for a general plugin ecosystem is unproven |
| F5 recorded answers | move up | replays a real failure without target calls; competitors already regrade |
| F6 team checks | move up; absorb M2 and M4; one live retrieval pilot | the model harness is not the user's application, and RAG coverage is a named gap |
| F7 conformance | new | two MCP revisions and A2A v1 need proof against servers Guardana did not write |
| M1 paired statistics | keep, after F5–F6 | a statistical claim needs compatible cases, coverage, assessor identity and power |
| M3 collector measurements | move down | trends before reproducible local results make incomparable runs look comparable |
| Prometheus reporter | defer | until a team names the measurements and unknowns it needs; the webhook is in F4 |
| central signed profiles | move down | locks and recipes should prove local use first |
| conformance kit | build during F6–F7, publish at 1.0 | publishing only at 1.0 postpones the evidence 1.0 needs |
| ATLAS provenance | move up | content now ships monthly; pin content and format versions apart |
| non-executing declarative packs | schedule a decision | installed Python packs execute code, and `--plugins all` is the default |
| public extension-ID service | drop | namespaces, local validation and locks cover the author workflow |
| multi-agent protocols | narrowly, in F7 | one A2A v1 fixture, not a multi-agent platform |
| multimodal carriers | narrowly, when a pilot uses one | a document or image carrier, with absent extraction reported as unverified |
| broad corpora, attack volume | move down | import or buy coverage; prompt count is not the adoption metric |

## Published measures

The milestone publishes three measures from generated data instead of counts of formats or
attacks: first-run completion, coverage of the real application, and the share of attempted
checks that reached a supported verdict with comparable evidence.

## Risks named by the review

- A first run that loads every installed plugin contradicts an offline, no-account start.
- "51 checks" and several framework badges read as comprehensive coverage; reports should lead
  with the surface tested, the evidence required and the dimensions left out.
- A user-defined `regex` check can still backtrack for a very long time on a crafted reply.
- Paired statistics cannot rescue a harness that missed the real application or a stale judge
  calibration.
- Output plugins, collector trends, central policies and SSO each add support and migration
  obligations before adoption has been measured.

## Quality and extensibility, in comparison

The extension contracts hold up: four entry-point groups load in a fixed order with isolated
failures, an installable example exercises all of them, cost is gated by operation counts, and
the import contract keeps the engine off the collector. garak (probes, detectors, generators,
buffs), PyRIT (targets, converters, scorers, memory), promptfoo (providers, assertions,
plugins, strategies), Inspect AI (tasks, solvers, scorers, sandboxes, a readable log format) and
DeepEval (metrics over test cases) are each ahead on one surface: an output or log API a program
reads, packaged team workflows, or attack breadth. None carries missing evidence through
planning, gating, comparison and export as one contract. The supported Python facade (F3) and
the narrowed output work (F4) close the gap that matters most to a team building on Guardana.
