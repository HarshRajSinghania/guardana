---
title: "Repository recipes, one connection and provider conformance"
nav_order: 87
summary: "a team pins what its checks are next to the application they run against, Guardana refuses to send anything when a pin moved, every endpoint command reads the same connection settings, and one suite proves what each provider path carries"
status: accepted
---

# Repository recipes, one connection and provider conformance

**Status:** accepted, implemented — ships in the next release · **Written:** 2026-10-02 · **Serves:** ROADMAP F6
(first half), backlog B08, the F5 leftover on stopped recordings

## The question

A team wants its own application checked in CI the same way every night: the same checks,
datasets and judges, against the system its users talk to, with an artifact a reviewer can
read. Three things stand in the way.

1. Nothing pins what a check *is* at the level a team reviews. `pack lock` pins installed packs;
   a profile, a local rule, a dataset, a calibration or a judge can change under a green build,
   and the next comparison blames the application.
2. Each endpoint command reads its connection on its own. `--adapter` exists on `probe` only;
   an unknown `--provider` or a missing `--system-prompt-file` is an internal error (exit `5`);
   `--api-key-env` naming an unset variable silently sends no key, so a gateway answering
   "please log in" grades as a refusal; a judge block accepts misspelled keys and names;
   `calibrate` calls its judge with no budget; `plan probe` accepts a token ceiling `probe`
   refuses; with `--adapter`, the run names `--url` while the requests go to the adapter's
   `url:`.
3. What each provider path carries — a system message, tools, token counts, retries — is known
   only from reading the transports. No test runs one set of assertions over all of them; the
   adapter does not retry, and the Ollama path ignores the token counts Ollama sends.

## Decisions

### 1. A hand-written recipe, a generated lock

`guardana-recipe.yaml` belongs to the team and Guardana never rewrites it, as with a pack
manifest. `guardana recipe lock` writes `guardana-recipe.lock.yaml` beside it;
`guardana recipe lock --check` compares without writing, as `pack lock --check` does;
`guardana recipe run` checks the lock, then runs.

```yaml
schema_version: 1
name: support-bot
profile: guardana.yaml
subject:
  kind: application              # application | model_harness — required, no default
  connection:                    # or `recording: answers.jsonl`, never both
    url: http://127.0.0.1:8080
    model: support-bot
    api_key_env: SUPPORT_BOT_KEY
    adapter: adapter.yaml        # optional
    system_prompt_file: prompts/canary-host.txt   # optional, as --system-prompt-file
  ai_system: support-bot         # optional, as --ai-system / --environment
  environment: ci
output:
  directory: guardana-artifact   # a relative subdirectory beside the recipe, never `.`
  exchanges: false               # the artifact holds replies only when this and the profile say so
```

`recipe run` takes no selection, trust, trials or profile flags: those are what the lock pins.
It takes `--plugins`/`--allow-plugin` only through the profile's `plugins:`.

Rejected: pins inside the recipe (a tool rewriting a reviewed file); connection settings in
the profile (a profile is a policy shared across targets); pins inside `guardana-lock.yaml`
(that lock describes installed packs whatever runs; a recipe describes one selection); a
separate `recipe check` verb (`lock --check` mirrors the precedent and adds less CLI surface).

### 2. The lock pins identities the run already records, plus what they miss

Computed from the recipe's plan without building a transport that sends and without reading a
secret, so it runs where CI withholds keys:

- the recipe's canonical digest (its parsed form, so a comment or line endings are not drift),
  the Guardana version, and the plugin trust in force;
- the profile digest the manifest records;
- every selected rule: id, `digest()` (a suite's covers its dataset; a YAML rule's is
  canonical), and the distribution and version that registered it;
- every evaluator a selected rule grades with: id, the distribution and version that registered
  it, its judge identity, and the digest of the calibration in force for it;
- every rule the plan skips for a reason the configuration decides (`unsafe_mode`,
  `missing_capability` from the declared provider or adapter), by reason code — never a
  recording-dependent skip, which is the subject's answer, not the configuration;
- trials per case per rule;
- the subject's own files the team reviews: the adapter file as written (before `${VAR}`
  expansion) and the system-prompt file, by digest. Never a secret, never the recording.

A distribution installed editable or from a direct URL (PEP 610 `direct_url.json`) can change
its code under one version, so its rules and evaluators are listed under `unpinned`. Every
digest sits under a `digest:` key, as `pack lock` lays them out.

Drift is named by kind, both directions: `recipe_changed`, `guardana_changed`,
`trust_changed`, `profile_changed`, `rule_added`, `rule_removed`, `rule_changed`,
`distribution_changed`, `skip_changed`, `evaluator_added`, `evaluator_removed`,
`judge_changed`, `calibration_changed`, `trials_changed`, `subject_file_changed`.

### 3. Exit codes

| Situation | `recipe lock` | `recipe lock --check` | `recipe run` |
|---|---|---|---|
| written / matches; run as its gate says | `0` | `0` | the run's code |
| a pin moved | — | `1` | `3`, nothing sent |
| anything selected is unpinned | `2`, written, naming them | `2` | runs; `unpinned` recorded and named |
| nothing selected, or plugin trust refused an installed extension | `2`, nothing written | `2` | `3`: no lock can match |
| recipe or lock unreadable, missing, or a lock schema this build does not know | `3` | `3` | `3` |

`--check` never writes, so a first run cannot pass by creating its own lock. A lock written by
a newer Guardana is refused with "upgrade Guardana", never "relock". `recipe run` does not
refuse on `RunPlan.blockers`: `probe` and `grade` do not, a grade sends nothing to save, and a
refused run would hide a finding the recording holds. The gate decides.

### 4. What answered, and how, are declared and travel with the evidence

`subject.kind` says what answered: `application` (the endpoint the team's users reach, run in
CI with the team's own fixtures or doubles behind it) or `model_harness` (a model reached
without the application's prompt, tools and data). The source says how: a `connection` or a
`recording`. Guardana cannot verify which one a URL is; it records what the team declared, and
the declaration is reviewed in the recipe. The saved run records both (`run.recipe`); the
terminal report's first line, the JUnit testsuite name (`guardana (model harness)`),
`run inspect` and a `diff` note when two runs' kinds differ show them. A recording does not
carry the kind: a recipe grading one declares it again. SARIF and the collector are not in
this half — the artifact has no SARIF file, and the envelope does not carry the recipe.

Guardana does not start, verify or record the team's doubles. "Safe fixtures or doubles" in
F6's exit criterion is met in this half by a recording source only; stateful doubles stay open.

### 5. The artifact cannot show a stale or partial green

`recipe run` first replaces the output directory with a placeholder whose `junit.xml` holds one
error testcase ("the run did not finish") and whose `report.txt` says so, then writes the run
into a temporary sibling and swaps it into place at the end. An interrupted run leaves the
placeholder; a refused run (drift, exit `3`) writes the refusal into the same two files. The
directory carries `guardana-artifact.json` (the files it holds); an existing non-empty
directory without it is refused, never deleted. Contents: `run.json`, `report.txt` (the
terminal report, no colour, followed by the lock comparison), `junit.xml`, copies of the recipe
and the lock, and `run.exchanges.jsonl` only when both the profile and `output.exchanges` say
so — a CI artifact is a copy of the application's replies nobody controls.

### 6. One connection for targets and judges

`Connection` — url, model, provider, api key variable, adapter file — is read the same way
from CLI flags, a recipe's `subject.connection` and a judge block (`endpoint` stays the URL
key). One resolver validates it; `probe`, `plan probe`, `target inspect`, `monitor`, and every
judge (`calibrate` included) use it. Refused with exit `3` before any request: an unknown
provider; a missing system-prompt or adapter file; `--adapter` with an explicit `--provider`
or with `--api-key-env` (the adapter's `headers:` carry credentials); an adapter `url:` that
disagrees with `--url` or a judge's `endpoint` (the run names the URL it calls); an adapter
`method:` other than `POST`; an api key variable that is unset or empty — read only when a
transport that will send is built, so `plan` and `recipe lock` need no secret. A judge block's
unknown keys and unknown block names under `evaluators:` are a `ProfileError`.

A judge's identity gains `provider=` and `adapter=<digest>` only when set, so existing
identities, and `diff` across versions, do not move. A caller-supplied `judge_endpoint` builder
(the Python facade) cannot honour a provider or an adapter; a block that sets one with such a
builder is a `ProfileError`, never silently built on the OpenAI wire.

`plan probe` applies the budget check `probe` applies. `calibrate` holds its judge to the
profile's `budgets:`; a calibration the budget stops exits `6` and records nothing. The saved
run records the provider and fills `configuration.adapter_digest` (the file as written) and
`configuration.system_prompt_digest` (the operator's file, never the planted canary).

### 7. Provider conformance is one table of requirements

A private local HTTP double (`guardana.core.testing._fake_provider`, unpublished until the
pilots settle its interface) speaks the OpenAI, Ollama, TGI and adapter shapes and can fail on
cue: a status with `Retry-After`, a redirect, malformed JSON, a missing field, an oversized
body, a slow reply. One parametrized suite holds every transport to one table. A "not
carried" cell must pair with its refusal: no tools → no `call_tools` capability; no token
counts → a token ceiling refused. Shared failure paths: `401`/`403`/`404` fail without retry;
`429`/`503` retry within `--max-requests` and count in `usage.requests`; a redirect is refused;
malformed or missing content fails closed; a slow reply times out (injectable timeout); token
counts are read when sent and unknown — never zero — when not. The built-in HTTP paths also
retry `500`/`502`/`504`; the adapter does not, because an application may have acted before it
failed. Ollama's `prompt_eval_count` and `eval_count` are read. LangChain has its own rows;
the HTTP failure paths do not apply to it. `docs/providers.md` prints the table and a test holds
the page to the suite's table.

### 8. A recording from a stopped run never grades to a pass

A graded run whose recording's origin was stopped (`origin.stopped_by`) carries a coverage
shortfall of a new kind, `incomplete_recording`, naming the origin run. A shortfall has no
switch, so the run is `indeterminate` (exit `2`) unless a finding fails it (exit `1`); `plan
grade` foresees it. Only a stop counts: an origin that ended `indeterminate` is the case
regrading exists for, and an origin's errors already return as errors. The origin is declared,
not verified; checking it against the origin's `run.json` is open.

## Persisted documents

- Run schema 14: `recipe` (name, recipe digest, lock digest, kind, source, unpinned ids),
  `configuration.provider`, the `incomplete_recording` shortfall kind. A schema-13 run migrates
  with `recipe` and `provider` null. The collector envelope is unchanged.
- Recipe schema 1 and recipe lock schema 1, each with `schema_version`, a JSON schema in
  `schemas/`, unknown keys refused, an unknown version refused rather than read.
- Profiles: judge blocks gain `provider` and `adapter` and refuse unknown keys and names.
  Profiles carry no `schema_version`; a 0.36 profile using the new keys fails on 0.35, loudly.

## Breaking changes

An unset `--api-key-env` or judge `api_key_env` is refused (it sent no key before);
`--adapter` with `--api-key-env` or an explicit `--provider`, an adapter `method:` other than
`POST`, an adapter `url:` that disagrees with `--url`, and a misspelled judge key or block name
are refused; three exit-`5` paths become exit `3`.

## Not done here (v0.37 and later)

The team regression loop, the live retrieval pilot, stateful tool doubles and declared data
boundaries, the subject kind inside a recording, verifying a recording's origin against its
run, a published conformance kit, headers or TLS outside an adapter file, SARIF and the
collector envelope for recipe runs, and a Markdown summary for pull requests.
