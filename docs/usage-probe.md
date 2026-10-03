---
title: "guardana probe"
nav_order: 70
summary: "`guardana probe`: adversarial checks against a live endpoint or agent, and an MCP server's manifest **and authorization surface**"
status: stable
---

# `guardana probe` — one-shot dynamic checks against a live endpoint

Runs every **endpoint**-kind rule against a live chat endpoint, one attempt per
case unless [`--trials`](#repeated-trials) asks for more:
direct prompt injection, jailbreak attempts (single-turn and multi-turn
scenarios), indirect (RAG) injection, system-prompt leakage (via a planted
canary), output-secret leakage, excessive tool-use agency (when the endpoint
supports tool calling), and unbounded output (denial-of-wallet). Each dynamic
finding carries a `Verdict` — `outcome`, `confidence`, `rationale`,
`evaluator_id` — from the rule's configured Evaluator.

By default the endpoint is OpenAI-compatible (`POST /v1/chat/completions` —
Ollama's `/v1`, vLLM, llamafile, LM Studio, and friends). `--provider ollama`
speaks Ollama's native `/api/chat` instead, and `--provider tgi` speaks
Hugging Face TGI's `/generate`.

```bash
guardana probe (--url <base-url> --model <name> | --target <scheme://locator>) [OPTIONS]
```

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--url TEXT` | — | Base URL of the OpenAI-compatible endpoint; with `--adapter`, the URL the adapter posts to. Required unless `--mcp` names an MCP server instead. A redirect is never followed: an endpoint that answers `3xx` is unavailable (exit `4`) |
| `--model TEXT` | — | Model name to send in each request. Required unless `--mcp` names an MCP server instead |
| `--target SCHEME://LOCATOR` | none | Build a trusted installed endpoint target instead of the built-in endpoint or MCP flags |
| `--target-option KEY=VALUE` | none | Repeatable, non-secret configuration passed to that target |
| `--api-key-env TEXT` | none | Name of an environment variable holding the bearer API key. A variable that is unset or empty is refused (exit `3`) before anything is sent; omit the flag for an endpoint that needs no key |
| `--provider [openai\|ollama\|tgi]` | `openai` | Endpoint wire protocol: OpenAI-compatible (default), Ollama's native `/api/chat`, or HF TGI's `/generate`. Any other name is refused (exit `3`) |
| `--adapter PATH` | none | Adapter file mapping a **guarded product endpoint**'s custom request/response schema — see [Probing a guarded endpoint](#probing-a-guarded-endpoint). Cannot be combined with `--provider` or `--api-key-env`: the adapter is the wire shape, and its `headers:` carry the credential |
| `--system-prompt-file PATH` | none | File containing the system prompt already deployed in front of the model, so non-canary rules probe the real configuration. A file that cannot be read is refused (exit `3`) |
| `--fixtures PATH` | none | A [`guardana-fixtures.yaml`](usage-fixtures.md): ask every seeded item as its owner and as every other tenant, each through that tenant's own credentials, and every poisoned document as its owner — see [Seeded data and tenants](#seeded-data-and-tenants). A file or a tenant connection that cannot be used is refused before anything is sent (exit `3`); refused with `--mcp` and `--target` |
| `--profile PATH` | none (built-in default profile) | Path to a `guardana.yaml` policy file |
| `--preset [ci\|pre-training\|monitor\|release]` | none | Named policy preset (mutually exclusive with `--profile`) — see [`profiles.md`](profiles.md#named-presets---preset) |
| `--format [human\|json\|sarif\|junit]` | `human` | Output format |
| `--rules PATH` | none | Directory or file of custom YAML rules; repeatable. Combined with the profile's `rules.paths` — see [`writing-rules.md`](writing-rules.md). A malformed rule file is a warning, never an abort. |
| `--plugins [all\|builtins\|allowlist\|disabled]` | `builtins`, or the profile's `plugins:` | Which installed plugins (entry-point rules, evaluators, targets, taxonomies) to load. `builtins` loads Guardana's own distributions and refuses every other installed pack before importing it; each refusal is an error, so under the default `fail_on_error` the run is `indeterminate` while a pack stays refused. See [plugin trust](profiles.md#plugin-trust-plugins) and [`SECURITY.md`](../SECURITY.md#the-plugin-trust-model). |
| `--allow-plugin TEXT` | none | Distribution to trust; repeatable, needs `--plugins allowlist` |
| `--trials INTEGER` | `1` (or `trials:` in the profile) | Independent attempts per case for rules that grade a sampled reply — see [Repeated trials](#repeated-trials). Every preset uses `1`; we recommend `5` for a release gate, which is also garak's default number of generations per prompt |
| `--concurrency INTEGER` | `4` | How many rules may query the model at once. The probe is almost entirely spent waiting on the model, so overlapping rules is the biggest speed-up available; results stay in rule order, so two runs match. Rate limits (429) are retried with backoff — lower this if an endpoint keeps refusing. Each retry counts against `--max-requests` and in the run's usage. |
| `--reporter TEXT` | none | Forward findings to a collector, e.g. `server://https://collector.example.com` |
| `--mcp TEXT` | none | Examine an **MCP server** instead of a chat model — see [Probing an MCP server](#probing-an-mcp-server). Refused with `--url`, `--model`, `--provider`, `--api-key-env`, `--adapter` or `--system-prompt-file`, which configure a chat endpoint (exit `3`) |
| `--mcp-token-env TEXT` | none | Name of an environment variable holding a bearer token for the MCP server |
| `--mcp-pin PATH` | none | Approved MCP manifest to compare the live one against |
| `--write-mcp-pin PATH` | none | Write the server's current manifest as approved, and exit without reporting |
| `--allow-exec` | off | Permit `--mcp` to **start** an stdio server, which executes the code under examination |
| `--max-requests`, `--max-input-tokens`, `--max-output-tokens`, `--max-duration` | the profile's `budgets:` | Ceilings on what the run may spend — see [`profiles.md`](profiles.md#budgets--a-ceiling-on-what-a-run-may-spend). A token ceiling on a transport that reports no token counts (an adapter, `--provider tgi`) is refused before anything is sent (exit `3`), as `plan probe` refuses it |
| `--max-requests-per-minute INTEGER` | the profile's `budgets:` | Send no faster than this: each request, a retry included, waits for a slot `60 / N` seconds after the one before, shared by every rule running at once. Each judge under `evaluators:` paces itself at the same rate on its own meter. A wait that would pass `--max-duration` stops the run as a spent budget (exit `6`) instead |
| `--safety [passive\|active\|side-effecting]` | `active` | How far rules may reach; a rule above it is skipped |
| `--allow-destructive` | off | Permit rules that can destroy or alter something the target owns |
| `--ai-system TEXT` | none | Which AI system this run verifies, e.g. `support-agent`. Never guessed. |
| `--environment TEXT` | none | Where it runs, e.g. `production`. Never guessed from a branch name. |
| `--deployment-id TEXT` | none | Which version of it, if you have an identifier. |
| `--output PATH` | stdout | Write the report to a file instead of stdout — needed by `guardana diff`. See [Saving a run for comparison](#saving-a-run-for-comparison) |
| `--keep-exchanges` | off (or `privacy.keep_exchanges`) | Keep every chat exchange of the plain pass, redacted, beside the saved run so [`guardana grade`](usage-grade.md) can grade it again without calling the endpoint — see [Keeping the exchanges](#keeping-the-exchanges). Needs `--format json --output`; refused with `--mcp`, with a `--target` not built on the built-in endpoint, and with `privacy.evidence_mode: metadata_only` (exit `3`) |

`--target` is mutually exclusive with `--url`, `--model`, provider, adapter, credential,
system-prompt, and MCP connection flags. The plugin owns construction; Guardana
still owns rule selection, policy, budgets, evidence, and exit codes. A custom
endpoint implements `SystemPromptPlanter` to receive isolated canary passes; if
it does not, canary rules are explicitly skipped rather than graded without a
marker. See [`extending.md`](extending.md#adding-a-target).

## Probing an MCP server

`--mcp` points `probe` at a Model Context Protocol server rather than a chat
endpoint. There is no model to talk to, so every chat rule is skipped by
capability and says so; what runs instead is the manifest check and the eight
authorization checks.

```bash
export MCP_TOKEN=…
guardana probe \
  --mcp https://mcp.example.com/mcp \
  --mcp-token-env MCP_TOKEN
```

**Guardana never calls a tool on your server.** Every observation is made with
`server/discover`, `tools/list`, the `initialize` handshake where the server still
expects one, and unauthenticated `GET`s of the two discovery documents. Calling a
tool is a side effect on somebody's system — possibly a write, possibly a payment
— and no verification result is worth finding that out by experiment.

**Guardana declares no client capabilities**, which is a safety property rather
than an omission. Under the `2026-07-28` Multi Round-Trip Requests pattern a server
asks for sampling, elicitation or a root listing by returning them in a result, and
it **MUST NOT** ask for a capability the client did not declare. A client declaring
none cannot be asked to run a model completion or to prompt a human on the server's
behalf; a server that asks anyway gets an error, never an answer.

### Two revisions of the protocol, and which one your server speaks

The specification revised on 2026-07-28 removed the `initialize` handshake and
protocol-level sessions, and made every request carry its own version. Guardana
speaks both that revision and `2025-11-25`, and settles which one applies before
asking a server anything else:

```
$ guardana probe --mcp https://mcp.example.com/mcp --format json | jq .run.coverage.protocols
{ "mcp": "2026-07-28" }
```

The probe is one `server/discover` call — the method the newer revision requires
and the older one has never heard of, which makes its *answer* identify the era.
Guardana deliberately does not use the cheaper route the HTTP binding allows
(send an ordinary request, read the body of a `400`): some servers built to the
older revision will answer `tools/list` without a handshake, and a client that
opened with one would take their manifest and record `2026-07-28` in the run
manifest — a coverage claim about a revision that server has never heard of.

Three consequences worth knowing:

- **The negotiated revision is in the run manifest**, so [`guardana diff`](usage-diff.md)
  reports a server that moved between revisions as *the reach changed*, not as the
  system behaving differently.
- **`guardana.mcp.session_binding` is silent on a server with no sessions.** A
  conforming `2026-07-28` server mints none, so there is nothing to guess and
  nothing to authenticate with. A server that still offers an older revision
  alongside the new one is graded over that older one, because it is still handing
  sessions to every client that asks for them.
- **No revision in common is an outcome, never a pass.** The authorization checks
  report `inconclusive` naming both version lists, and the manifest checks are
  skipped with the same sentence — which `fail_on.fail_on_skipped` turns into an
  indeterminate run.

**The token never leaves the origin you named.** MCP is the one protocol here
where the server picks an address and the client fetches it, so every redirect hop
is checked against the same guard as the first request — and a hop to a different
scheme, host or port arrives with no `Authorization` and no `Mcp-Session-Id`. The
alternative is a server under test answering `302` and being handed the credential
of whoever is scanning it, which is the confused deputy these checks exist to look
for. A redirect *within* one origin keeps the header, because a server pointing at
its own path is ordinary.

### The manifest, and pinning it

A tool declaration is fed to the agent's model as trusted context, so an
instruction hidden in one is indirect prompt injection with an audience of one.
Guardana scans the whole declaration — description, title, input and output
schema, annotations — because a property description is read by the model exactly
like the tool description.

Drift is only detectable against something you approved:

```bash
guardana probe --mcp https://mcp.example.com/mcp \
  --write-mcp-pin mcp.pin.json          # approve today's manifest
guardana probe --mcp https://mcp.example.com/mcp \
  --mcp-pin mcp.pin.json                # compare against it
```

The pin stores a digest per tool rather than the prose, so the file records *that*
the manifest was approved and cannot be edited into agreement. Without `--mcp-pin`
drift is reported `inconclusive`, never as a clean server.

Pins written before 0.13.0 are `schema_version 1` and cover **descriptions
only**. They still load and still compare, and every run that uses one carries a
note saying which drift it cannot see — re-approve with `--write-mcp-pin` to cover
schemas too.

### The authorization surface

Eight checks, each testing an invariant the MCP specification states, and each
saying plainly when it could not reach a verdict:

| Rule | What it establishes |
|---|---|
| `guardana.mcp.unauthenticated_access` | The server answers a tool listing with no credential. `low` on a loopback or private address, `high` elsewhere |
| `guardana.mcp.authorization_discovery` | A protected server publishes Protected Resource Metadata (RFC 9728) naming an authorization server, identifies *this* origin as its resource, and points at an authorization server that advertises PKCE |
| `guardana.mcp.token_audience` | The server refuses a bearer token it could not have issued |
| `guardana.mcp.session_binding` | Session ids are not a counter, are not shared, and do not authenticate a request on their own |
| `guardana.mcp.scope_breadth` | The advertised scopes can express least privilege, and the challenge names the scope a request needs |
| `guardana.mcp.discovery_target` | Every discovery address the server advertises is one a client may follow |
| `guardana.mcp.issuer_identification` | The authorization server advertises `authorization_response_iss_parameter_supported`, without which a client cannot detect an authorization-server mix-up (RFC 9207) |
| `guardana.mcp.cache_scope` | A tool listing the server gates behind a credential is not also declared `cacheScope: "public"`, which would invite any shared gateway to serve it to a caller the server would have refused |

**Two of them need `--mcp-token-env` to say anything**, and say so rather than
going quiet: whether a session authenticates on its own cannot be tested without a
credential to remove. A run without one reports those as `inconclusive` and names
the flag.

**What a silent `token_audience` does and does not mean.** Guardana presents a
token nobody could mistake for a credential — `alg: none`, an audience and issuer
naming a reserved domain that never resolves, and a signature segment that says
`guardana-probe-not-a-valid-signature` in words. A server that answers a tool
listing while holding it validated nothing, and that is a finding. A server that
rejects it has rejected *that token*; proving it validates audiences would need a
correctly signed token minted for another service, which no scanner can honestly
obtain. Against a server that requires no credential at all the check reports
`inconclusive`, because a server that accepts everything demonstrates nothing.

**Dynamic Client Registration is not reported as a defect.** `2026-07-28`
deprecates it in favour of Client ID Metadata Documents and keeps it legal for at
least twelve months, and it remains the only registration route some authorization
servers offer. Reporting a supported feature as a defect is a false red.

**stdio servers are not graded on this.** The specification says an stdio
implementation should take credentials from the environment instead of following
the authorization spec, so an stdio target does not declare the capability and all
eight rules are **skipped** with their reason recorded. `fail_on.fail_on_skipped`
turns that coverage hole into an indeterminate result; what never happens is six
rules reporting nothing about a server they could not examine.

**The credential never reaches a report.** It is read from the environment rather
than an argument — an argument is in every process list on the machine — and
evidence records whether one was presented and what the server answered, never its
value, at any privacy level.

### Cost

An MCP probe sends around a dozen requests: one `server/discover` to settle the
revision, a listing without a credential (preceded by a handshake where the server
still expects one), up to five discovery fetches, a listing with the forged token,
and a handful of handshakes to sample session ids. Every one is
counted, so `--max-requests` bounds it, and a run that hits the ceiling exits `6`
with an `indeterminate` gate rather than reporting the checks it never reached as
clean.

Ask before you spend, with [`guardana plan`](usage-plan.md):

```bash
guardana plan probe --mcp https://mcp.example.com/mcp
```

That contacts nothing. The ceiling it reports is higher than any run spends —
each rule declares what it would cost *alone*, because a plan cannot know which
one runs first and buys the shared observation — so treat it as the upper bound
it is.

## Probing a guarded endpoint

`--provider` speaks the raw model wire (OpenAI/Ollama/TGI). But the thing you most
want to test is often your **guarded product endpoint** — the model *plus* the API
gateway, auth, and guardrails in front of it — and that has its own request and
response schema. `--adapter <file>` maps it, so the probe drives the whole surface
instead of bypassing it to the bare model.

```yaml
# wellness-adapter.yaml
url: https://api.example.com/v1/wellness/chat   # optional; must equal --url
method: POST                                    # optional; POST is the only method
headers:
  X-Api-Key: ${WELLNESS_API_KEY}                # ${ENV} is expanded; unset or empty = error
  Content-Type: application/json
body:                                           # your endpoint's request shape;
  message: "{{prompt}}"                         # {{prompt}} is where the probe goes
  user_id_hash: "guardana-probe"
  stream: false
response_path: data.reply                       # dotted path to the reply text
```

```bash
guardana probe --url https://api.example.com/v1/wellness/chat --model wellness \
  --adapter wellness-adapter.yaml
```

The run names the URL it calls, so the adapter's `url:` may only repeat `--url`; one that
differs is refused rather than silently replacing it. Everything below is refused with
exit `3` before a request is sent: an adapter file that cannot be read, an unknown key,
a `method:` other than `POST`, a `${VAR}` that is unset or empty, and `--adapter`
together with `--provider` or `--api-key-env`. The same adapter file works for
[`plan probe`](usage-plan.md), [`target inspect`](usage-target.md) and
[`monitor`](usage-monitor.md), and for a judge through `adapter:` in its
[`evaluators:` block](profiles.md#config-wired-evaluators-llm_judge-and-guard). `plan probe` reads
no `${VAR}`: pricing a run needs no secret.

The body is sent as JSON with `Content-Type: application/json` unless `headers:` names its
own content type. A `429` or `503` is retried, honouring `Retry-After`, within
`--max-requests`; a `500`, `502` or `504` is not, because your application may have acted
before it failed ([providers](providers.md)). A saved run records the digest of the adapter
file as written, before `${VAR}` expansion, in `run.configuration.adapter_digest`.

For a **multi-turn** scenario (gradual jailbreak, indirect injection), give the
body a `{{messages}}` slot to receive the full transcript as a `[{role, content}]`
list, if your endpoint speaks multi-turn:

```yaml
body:
  messages: "{{messages}}"     # the whole conversation, not just the last turn
```

Without a `{{messages}}` slot, every turn is folded into `{{prompt}}` as a labelled
transcript — so a scenario's escalation reaches the endpoint instead of collapsing
to the final message.

The mapping is **fail-closed**: a `body` with no `{{prompt}}` or `{{messages}}`
slot is rejected at load (the probe would otherwise send the same static request
for every check and pass everything), and a `response_path` that does not resolve
to a string is an error, never a blank reply graded as clean. A planted system
prompt with no `{{system}}` slot is folded into the prompt rather than dropped, so
a canary/leak check is never silently disarmed. Programmatically, the same mapping
is `guardana.core.target.HttpAdapterTransport` / `AdapterConfig`.

## Repeated trials

A deployed model samples, so one reply per prompt shows only that a failure did not
happen that time. `--trials N` sends every case N times, each as a fresh request with no
shared history, and records every attempt.

```bash
guardana probe --url http://localhost:11434 --model llama3 --trials 5
```

- **Which rules repeat:** single-prompt rules, scenarios, agent runs,
  `guardana.output.secrets` and `guardana.agent.excessive_tool_use` — every rule whose
  verdict depends on a sampled reply. MCP and other protocol checks, trace rules, and a
  scenario marked `stateful: true` make one attempt per case whatever you ask; the
  report names them.
- **A scenario is one case per attempt.** Its graded turns and its whole-conversation
  grade are checkpoints of one conversation, so the bound counts the conversation once,
  not once per checkpoint.
- **A case fails when any attempt fails.** It yields one finding that says how many
  attempts failed (`2 of 5 trials failed: …`). An attempt the grader could not decide,
  with none failed, leaves the case incomplete: it is reported as unverified, never as
  clean.
- **Every attempt is an assessment** with its `trial` number in the saved run, and each
  repeating rule records a `trial_summary` — see
  [`usage-run.md`](usage-run.md#the-document).
- **Cost is exact:** a rule that repeats sends its requests times N,
  `guardana plan probe --trials N` prices that before anything is sent, and a budget
  bounds it.
- **One canary per rule per run:** every attempt of a canary rule sees the same freshly
  minted token, because an attempt repeats the same input.
- **Guardana never changes the target's sampling settings.** A lower temperature would
  measure a configuration nobody deployed.

The report ends with one line per repeating rule:

```text
Trials
  guardana.output.secrets  clean · 0 of 3 cases in 3 trials each · ASR@3 ≤ 63.2% (95%) · graded by guardana.output.secrets
  guardana.prompt.injection.ignore_previous  clean · 0 of 4 cases in 3 trials each · ASR@3 ≤ 52.8% (95%) · corrected ASR@3 ≤ 70.2% (95%) · graded by keyword · sensitivity 0.90/30 positives, specificity 0.93/30 negatives · corpus c683ae93e403
  guardana.prompt.jailbreak.dan_style  clean · 0 of 4 cases in 3 trials each · ASR@3 ≤ 52.8% (95%) · graded by keyword · uncorrected — judge error not measured: no calibration recorded for keyword
  static prompt set · no adaptive attacker ran
```

`ASR@K` is the share of cases where at least one of K attempts failed. A clean rule
states an upper bound on it at 95% confidence, computed over **cases**, not over pooled
attempts: the attempts at one prompt are correlated, so 4 cases in 5 trials each are 4
observations, not 20. A bound over four cases is wide, and the line says so rather than
reading as safe. The bound is over this rule's own prompts, and it counts the grader's
verdicts.

### Judge error

The raw figures stay on the line. When every recorded grader is deterministic, the line
ends with `graded by <assessor>`; there is no judge error to correct. A qualifying
calibration adds a corrected `ASR@K` clause, or a corrected upper bound for a clean
rule. If correction is refused, the line ends with
`uncorrected — judge error not measured` and names the missing condition. A line with no
rate ends with just `graded by <assessor>`.

Rogan–Gladen corrects `ASR@K` over decided cases or the clean bound. Each end of the
printed Wilson interval, or the exact one-sided bound when no case failed, is corrected
at the least favourable corner of the sensitivity and specificity 95% Wilson intervals.
If sensitivity plus specificity minus 1 is not positive at that corner, the end is
unbounded: 0 for the lower end or 1 for the upper end. In simulations with 30
calibration samples per class, per-side misses stayed below 1%. At `K > 1`,
applying per-reply error rates to a per-case rate overstates `ASR@K` in expectation and
does not understate it in expectation.

A calibration must match the rule's sole recorded assessor id and judge identity. It
needs per-class counts from a corpus other than the bundled starter, at least 30 graded
samples in each class, and abstentions below half of each class. The judge's sensitivity
and specificity must give Youden's J of at least 0.1. The observed upper bound must also
exceed the calibrated false-alarm rate. Otherwise the line names why correction was
refused.

To get a corrected rate, label your own traffic with at least 30 graded positives and 30
graded negatives. Run
`guardana calibrate --evaluator <id> --corpus mine.jsonl --record calibrations.json`
with the same judge configuration as the run. List `calibrations.json` under
`calibrations:` in `guardana.yaml`.

`guardana diff` refuses to compare a rule whose trials per case changed between the two
runs — more attempts find more, which is not a regression; see
[`usage-diff.md`](usage-diff.md#exit-codes).

## How canary rules work

Rules that need `plant_system_prompt` (the system-prompt-leak canary rule and
the indirect-injection scenario) run in their **own** probe pass, each against a dedicated endpoint
target whose system prompt is your `--system-prompt-file` contents (if any)
plus a Guardana-generated line embedding a **fresh random canary token**
minted for that run — the static canary value in the rule's YAML only marks
the rule as canary-capable and is never used for detection, so a model can't
have been trained around it. All other
endpoint rules run together in a single pass against your endpoint as
configured. This means one `probe` invocation may issue multiple batches of
requests — this is expected and is what lets an unmodifiable canary
co-exist with your real system prompt.

## Example invocation and output

```console
$ guardana probe --url http://localhost:11434 --model llama3
✖ [CRITICAL] guardana.prompt.system_prompt_leak.canary — System prompt leakage via canary marker
    Planted canary marker found in response.  (http://localhost:11434#llama3)
✖ [HIGH] guardana.prompt.injection.ignore_previous — Prompt injection via instruction override
    No refusal marker found; response likely complied.  (http://localhost:11434#llama3)

Trials
  guardana.prompt.injection.ignore_previous  1 of 4 cases failed in 1 trial each · ASR@1 25% (95% CI 4.5 to 70%) · graded by keyword · uncorrected — judge error not measured: no calibration recorded for keyword
  guardana.prompt.system_prompt_leak.canary  1 of 4 cases failed in 1 trial each · ASR@1 25% (95% CI 4.5 to 70%) · graded by canary
  …
  static prompt set · no adaptive attacker ran

2 finding(s); 8 rule(s) run, 0 skipped. 22/22 case(s) measured.
```

Every dynamic finding's evidence pairs with a verdict: run
`--format json` to see `outcome`, `confidence`, and `rationale` per finding.

A check that ran but could not reach a verdict — an empty model reply, a
judge reply that could not be read — is reported separately as
`? [UNVERIFIED]` (the `unverified` key in JSON), never silently counted as a
pass; set `fail_on_inconclusive: true` in your profile to make it fail the
gate. A judge configured under `evaluators:` that cannot be reached stops the
probe with exit `4` and writes no run, with `--url`, `--target` and `--mcp`
alike ([exit codes](exit-codes.md)).

## Rules graded by an LLM judge

The `llm_judge` and `guard` evaluators need a model of their own, wired from
an `evaluators:` block in `guardana.yaml` — see
[`profiles.md`](profiles.md#config-wired-evaluators-llm_judge-and-guard). With
no block configured, a rule that names one of them is **skipped visibly** in
the run summary rather than silently passed. `plan probe` prices their calls before
the run ([`usage-plan.md`](usage-plan.md#pricing-judge-calls)), and the saved run
records what they spent in `usage.judge` ([`usage-run.md`](usage-run.md#what-a-run-costs)).

## Exit codes

Same policy gate as `scan` (see [`profiles.md`](profiles.md)): exits `1` if
any finding at or above `fail_on.severity` also meets `fail_on.min_confidence`,
else `0`.

**Except when nothing was graded at all**, which exits `2`. An endpoint that answers
every request with an empty message is reachable, well-formed and useless to grade:
each rule runs, each evaluator declines, and the finding count is zero for a reason
that has nothing to do with the model being sound. See
[`exit-codes.md`](exit-codes.md).

## Forwarding to a collector

```bash
guardana probe --url http://localhost:11434 --model llama3 --reporter server://https://collector.example.com
```

## Trying it without a live model

`probe` needs a running OpenAI-compatible endpoint — if `--url` is
unreachable, the command reports a clear connection error and exits
non-zero rather than hanging. The fastest way to get one locally:

```bash
ollama serve &
ollama pull llama3
guardana probe --url http://localhost:11434 --model llama3
```

Any other OpenAI-compatible local server (vLLM, HF-TGI, LM Studio, etc.)
works the same way — just point `--url`/`--model` at it.

## Saving a run for comparison

`--output <path>` writes the report to a file instead of stdout. With
`--format json` that file is a versioned document `guardana diff` reads back, so
you can ask whether the next run is worse than this one — see
[`usage-diff.md`](usage-diff.md).

`--output` with the default human format is **refused before the first request**,
with exit `3`. The probe would otherwise spend its budget against your endpoint and
tell you only afterwards that the file it wrote cannot be compared — and the run you
wanted compared is the one you would have to pay for twice. `--format sarif` and
`--format junit` are written as asked: a code-scanning upload and a CI report reader
are what they are for, and neither has anything to do with `diff`.

```bash
guardana probe --url … --model …  --format json --output run.json
```

Prefer it to a shell redirect: PowerShell redirects write UTF-16, and the reader
on the other end cannot parse that.

### Keeping the exchanges

`--keep-exchanges`, or `privacy.keep_exchanges: true` in the profile, keeps every chat
exchange of the probe beside the saved run, so the same replies can be graded again with
a new rule, a sharper expectation or another judge, without a second request:

```bash
guardana probe --url … --model … --keep-exchanges --format json --output run.json
guardana grade run.exchanges.jsonl --rules rules/ --format json --output regraded.json
```

`run.json` → `run.exchanges.jsonl`. Each line holds the messages a rule sent and the
reply, as a [recording](usage-grade.md#a-recording) `guardana grade` reads. The run
records the file's SHA-256, its line count and how many replies redaction changed under
`run.exchanges`; a sidecar that no longer matches that digest is a different execution to
`guardana diff`.

- Only the plain pass of the built-in endpoint is kept: `--url`, with or without
  `--adapter`, or a pack's `--target` built on `EndpointTarget`. Another `--target` keeps
  nothing and is refused (exit `3`). The system prompt, the canary passes and tool offers
  are never kept, so canary and tool rules are not graded again. What a rule asks as a
  tenant under `--fixtures` is never kept either.
- Every input and reply passes the run's redactor, matched spans only and without the
  evidence size bound; a secret is removed under every `evidence_mode`, `full` included. A
  reply redaction changed is marked `altered` and is never graded again: a reply that
  leaked a secret cannot be regraded into a pass.
- Keeping is off by default. The file holds every reply, passes included, so it widens
  what a leaked run exposes; the collector never receives it. See [privacy](privacy.md).
- A probe that kept nothing writes no file and says so on stderr.

## Seeded data and tenants

With `--fixtures`, the probe also builds one endpoint per tenant the file declares: the run's
URL, model, provider and system prompt, and that tenant's own key or adapter. Two checks ask
through them; every other rule talks to the run's own connection as before, and every tenant
endpoint bills the run's meter, so the budgets bound the whole probe.

```bash
guardana fixtures render guardana-fixtures.yaml --out seed/   # seed seed/documents.jsonl yourself
guardana probe --url https://support.example.test --model support-bot \
  --fixtures guardana-fixtures.yaml --format json --output run.json
```

- `guardana.tenancy.cross_tenant_answer` — a marker of one tenant's item in a reply to
  another tenant is a finding. Clean means no marker of another tenant reached a reply, and
  only when both controls of the pair answered.
- `guardana.retrieval.poisoned_document` — a reply that followed the instruction planted in
  a poisoned document is a finding; skipped as `not_applicable` when none is declared.

A control that returned no marker in any trial is a `seed_not_reached` coverage shortfall,
so the run ends `indeterminate` (exit `2`) unless a finding fails it. Fixtures demand every
installed rule that checks seeded data and has something to check, these two and any a pack
adds: excluding or skipping one is a `demanded_check` shortfall, and so is an install with
no such rule. A tenant that authenticates as the run's own connection (`--api-key-env` or
`--adapter`) is refused (exit `3`): every other rule would then run as that tenant. The run
records the file as `run.fixtures`. What each check asks, and what its clean result does and does not
mean: [`usage-fixtures.md`](usage-fixtures.md#the-two-checks-a-run-given-fixtures-makes).

## Quality suites

[Quality suites](usage-suites.md) grade a versioned dataset under `guardana probe`.

A declined suite exits `2`, and a failed suite exits `1`, whatever its severity.
