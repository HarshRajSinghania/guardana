---
title: "A guarded application, and the outcomes a run states honestly"
nav_order: 89
summary: "an application whose guard declines requests is graded on what the team declared a decline to mean, a target that fails part-way leaves the run it got so far, a request rate and a graded share are budgets a team can set, a recipe names an installed target, and a scan that read nothing, or could not read a model, says so under every preset"
status: accepted
---

# A guarded application, and the outcomes a run states honestly

**Status:** accepted, implemented — ships in the next release · **Written:** 2026-10-03 · **Serves:** ROADMAP v0.38 (the rest of F6)
and the backlog items it closes · **Amends:** [`team-recipes.md`](team-recipes.md) decisions 2
and 3, [`exit-codes.md`](exit-codes.md) (code `4` with a result)

## The question

A team's application sits behind a guard. The guard declines some requests, the gateway
rate-limits, and a request now and then times out. Today each of those ends the probe with exit
`4` and saves nothing: a guard that rejects one prompt with HTTP `400` reads as an unreachable
endpoint and the requests already graded are lost; a guard that answers `200` with
`{"blocked": true}` is graded as if the block text were the model's answer, or fails the
`response_path` and ends the run; a read timeout is a rule error while a refused connection
ends the run. The team cannot say how fast to send, cannot read the guard's own verdict into an
evaluator, and cannot point a recipe at the pack target it already uses with `probe --target`.

Separately, four outcomes are reported as passes or with the wrong cause: a scan of a path with
no file passes under every preset; an unreadable or unparseable model file is an inconclusive
finding that `--preset ci` passes; `pack validate` does not check who registers a declared
evaluator, target or taxonomy; MCP authorization discovery checks an address and then connects
by name.

## What exists, so this does not rebuild it

- `HttpAdapterTransport` (`core/target/adapter.py`): body template, headers, `response_path`,
  retries `429`/`503` through `read_with_retry` (`core/target/endpoint.py`). `ChatTransport.send`
  returns text only; `Exchange.meta` exists and nothing fills it.
- `Runner._run_rule` (`core/runner.py`) re-raises `URLError`/`EndpointError` for an `ENDPOINT`
  target; `Verifier` wraps it in `TargetUnavailableError` ("nothing partial is kept"); the CLI
  prints the cause through `run_against_endpoint` (`cli/_errors.py`, which quotes the redacted
  body) and exits `4`. A bare `TimeoutError` falls to the generic catch: a rule error.
  `JudgeUnavailableError` subclasses `EndpointError`.
- `StopReason` (`core/gate.py`): `budget_exhausted` → `6`, `interrupted` → `7`. A stop outranks
  the verdict; a stopped rule stays out of `rules_run`, its findings and assessments are kept.
- Coverage shortfalls (`core/report/shortfall.py`) have no switch: any one makes the run
  `indeterminate`. `RuleContext.shortfall` lets a rule report one.
- `UsageMeter.reserve` (`core/usage.py`) runs before every request and every retry, for
  endpoints, MCP servers and judges.
- The recipe lock lists rules and evaluators from a distribution with `direct_url.json` under
  `unpinned` (`core/recipe.py`, `moves_under_one_version`).
- The registry records evaluator and target origins (`evaluator:<id>`, `target:<class>`); the
  taxonomy group drops its origin (`registry.py`, `_ignoring_origin`).

## Decisions

### 1. A decline is declared in the adapter, read by the evaluator, never retried

The adapter file gains `declines:`, an ordered list. Each entry:

```yaml
declines:
  - name: content_filter          # required, unique, [a-z0-9][a-z0-9_.-]*; shown in evidence
    status: [400, 422]            # required: one status or a list
    path: error.code              # dotted as in response_path
    equals: content_policy        # string, number or boolean; required with path
    as: refusal                   # required: refusal | ungraded
  - name: input_rejected
    status: 413
    as: ungraded                  # a status alone may only say "ungraded"
```

- **What is refused when the file is read** (exit `3`): a status outside `200`–`299` and
  `400`–`499`; `401`, `403`, `404`, `407`, `408`, `425` or `429` (credentials, a wrong address,
  a timeout and a rate limit are never a decline); an unknown key; a duplicate name; `path`
  without `equals` or the reverse; `as: refusal` without `path` (a status alone cannot tell a
  policy block from a malformed request, and reading every `400` as a refusal would pass every
  security check against a broken body template); any `2xx` entry without `path`; a status that
  is also in `retry_statuses:` (decision 2). A judge block's adapter (`evaluators:`) refuses
  `declines:` and `metadata_paths:` and may set `retry_statuses:`: a judge either answers or is
  unavailable. `load_adapter` learns which it reads from its caller (`for_judge=True` from the
  judge path in `wire_config_evaluators`).
- **Matching**, on every reply, before retry and before `response_path`: the first entry whose
  `status` holds the reply's status and whose `path` (when given) resolves to a JSON scalar
  equal in type and value to `equals`. An error reply's body is read within the 8 MiB cap and
  parsed as JSON only for a `path` entry; a body that is not JSON matches no `path` entry. A
  `2xx` match counts only when the reply carries no non-blank text at `response_path`: a guard
  that flags an answer and still delivers it is graded on what it delivered. A non-`2xx` reply
  no entry matched is raised as `HTTPError(url, status, reason, headers, io.BytesIO(body))`, so
  classification and quoting read its body as they read a provider's.
- **Never retried.** A matched decline is one request, metered like any other.
- **Typed, not text.** The transport raises `RequestDeclined(decline, meta)` — not an
  `EndpointError` or `URLError`, so it never ends a run — carrying
  `Decline(name, reading, status)` with `reading` a `DeclineReading` (`refusal` | `ungraded`).
  Both are exported from `guardana.core.target`. No reply text is invented; the guard's body
  is not graded.
- **How it is graded.** `Exchange` gains `decline: Decline | None`; a declined exchange ends on
  the user turn the application declined, so `reply_text` is `None`. `evaluator.base.grade`
  decides once (`grade` keeps its signature and returns the verdict; rules call
  `grade_decline(evaluator, exchange, expectation) -> tuple[Verdict, bool]`, whose flag says the
  verdict came from the decline rather than from earlier turns — only then do the tag and the
  correction rule below apply):
  1. If assistant turns are under grade (`graded_replies` is not empty — a scenario's earlier
     steps, a conversation scope), the evaluator grades the exchange as it is; a `fail` stands.
     A leak at step 2 is not taken back by a decline at step 3.
  2. Otherwise, or when that was not a `fail`: `ungraded` → `inconclusive`, rationale naming the
     decline and its status; `refusal` → `Evaluator.read_decline(exchange, expectation)`.
  - The base `read_decline` returns `inconclusive` ("grades reply text; a declined request has
    none"). Built-ins that override it: `keyword`, `canary`, `llm_judge`, `guard` → `pass` at
    `1.0` without a judge call; `answered`, `reference_judge` → `fail` at `1.0` (a declined task
    was not answered). Every other built-in (`contains`, `regex`, `exact_match`, `json_valid`,
    `length`, `amplification`, `tool_call`) keeps the base. A third-party evaluator keeps it
    until it overrides, so a decline never passes through an evaluator that did not say how.
  - The rule that turns a `pass` on an empty reply into `inconclusive` does not apply to a
    `pass` from `read_decline`.
- **Recorded.** An `inconclusive` verdict on a declined exchange is recorded with
  `UnmeasuredReason.TARGET_DECLINED` (`"target_declined"`), distinct from `declined` (an
  evaluator that could not decide): `from_verdict` takes `reason=`, and a rule passes it when
  its exchange carried a decline. Every assessment graded from a decline carries the tag
  `declined:<name>`; a suite's judge-error correction leaves those out and counts them as
  observed (a decline is a fact, not a judge's reading): corrected rate = (n_judged ×
  corrected_judged + passed_declined) / n, and each limit likewise from the judged limit. A
  finding's evidence names the decline
  instead of a reply (`declined by the application: content_filter (HTTP 400)`).
- **Which rules handle it.** A rule catches `RequestDeclined` around the send only, never around
  `grade` (a judge cannot decline). `YamlRule`, `SuiteRule` and `ScenarioRule` grade the
  declined exchange. A scenario stops at a decline: the declined step is graded, its later
  steps are not sent, and its conversation scope is graded once over the turns that were sent,
  with the decline. A step without `expect:` is not graded, so a decline there leaves the
  scopes it did not reach: each is recorded `inconclusive` with `TARGET_DECLINED` and the
  `declined:<name>` tag, so a trial never disappears. `output/secrets.py` records either reading as
  `inconclusive` with `TARGET_DECLINED`: it scans text, and a decline has none.
  `seeded/_base.py` grades in its own code: `Asked.reply` becomes `str | None` beside
  `decline: Decline | None`; a declined control question is seed not reached (its existing
  shortfall); a declined probe is `pass` at the rule's confidence under `refusal` (no marker can
  be in a decline) and `inconclusive` with `TARGET_DECLINED` under `ungraded`
  (`cross_tenant_answer.py`, `poisoned_document.py`). A rule that does not catch it — a
  trajectory rule, a third-party rule — gets a rule error (exit `2`), never a pass.
- **Kept and regraded.** `EndpointTarget.chat_reply` keeps a declined exchange before it
  re-raises; a recording line holds either `reply` or `declined: {name, reading, status}`
  (recording format 3, decision 12; `recording._LINE_KEYS`, `_exchange`, `_exchange_record`,
  `keeping._omit`, which keeps `declined` and drops only the input text). A declined line is
  never `altered`; `RecordedTarget` raises `RequestDeclined` for it before the altered check, so
  `grade` reads it as the probe did. `case add` refuses a declined line (exit `3`,
  `promotion.select_exchange`): it has no reply to pair; `case list --show` previews it as
  `[declined: <name> (HTTP <status>)]`.
- **`target inspect`** catches `RequestDeclined` from its capability prompts and reports that
  capability as not established ("declined by the application: <name>"), never as supported.

Rejected: a decline as substituted refusal text (invents evidence and lets `json_valid` or
`length` pass a guard's error body); one reading for the whole adapter decided by the rule
(a content-policy block and a malformed-input reject are different facts the team knows and
Guardana does not); retrying a decline (the guard has answered).

### 2. `retry_statuses:` replaces the adapter's retried set

A list of statuses from `408`, `425`, `429` and `500`–`599`; absent means `[429, 503]`, `[]`
means never. The attempt cap (3) and `Retry-After` handling stay. Only the adapter reads it;
the built-in providers keep their fixed set. Every retry is metered (as today).

### 3. `metadata_paths:` fills `Exchange.meta`

```yaml
metadata_paths:
  guard_category: data.moderation.category
  request_id: meta.request_id
```

At most 16 names (`[a-z][a-z0-9_]*`), each a dotted path read from every JSON reply the adapter
parses, a declined one included. A string is copied; a number or boolean is copied as its JSON
text; an absent path, an object, a list, `null` or a value over 1,024 characters leaves the
name out — an evaluator reads a missing name as missing evidence.

- **Transport:** the injectable `Fetch` returns the status and the body bytes rather than parsed
  JSON, so the adapter can match declines on any status. `ChatReply` gains
  `meta: Mapping[str, str]`; a new optional protocol `MetadataReportingTransport.
  send_with_metadata(...) -> ChatReply` (not `UsageReportingTransport`: the adapter reports no
  token counts, and claiming that protocol would let a token ceiling through).
- **Target:** an optional protocol `ChatWithMetadata.chat_reply(messages) -> ChatReply`
  (`target/protocols.py`), implemented by `EndpointTarget` and the recorded views; `chat` stays
  and returns `chat_reply(...).text`. `YamlRule`, `SuiteRule` and `ScenarioRule` call
  `chat_reply` when the target has it and put `meta` on the `Exchange`; a scenario's exchange
  carries the last reply's. `SeededTarget` does not implement it: the seeded rules read no
  `meta`.
- **Kept:** exchanges carry `meta`, redacted by the run's policy; a value the redaction changed
  is left out of the kept `meta` (absent, so missing evidence on a regrade) and does not mark
  the reply `altered`. No built-in evaluator reads `meta`.

### 4. Whose failure it is decides the outcome; a stopped run is kept

The runner classifies what a rule's send raised, in `_run_rule`, after re-raising
`JudgeUnavailableError` untouched (a judge failure stays exit `4` with nothing saved):

| the send ended with | whose failure | outcome | exit |
|---|---|---|---|
| a declared decline | — | graded (decision 1) | the gate's |
| `HTTPError` `4xx` other than `401`, `403`, `404`, `407`, `408`, `425`, `429` | the request | an error of the rule that sent it (`stage="request"`, reason from `describe_failure`); the run continues and is saved | `2` |
| `HTTPError` `401`, `403`, `404`, `407`; `408`, `425`, `429` or `5xx` once its retries, if any, are spent | the target | the run stops, `stopped_by: target_unavailable`, saved | `4` |
| `URLError`: no connection, DNS failure | the target | the same | `4` |
| a connect or read timeout, a reset, malformed HTTP (made `EndpointError` by `read_with_retry`) | the target | the same | `4` |
| `EndpointError`: a redirect, a reply that is not JSON, lacks `response_path` or exceeds 8 MiB | the target | the same | `4` |

- A `4xx` names *this request*; an unreadable `2xx` reply is a mapping that does not fit the
  endpoint and would fail every request alike, so it stops the run early rather than spending
  one request per rule. An in-body guard block is what `declines:` is for.
- An error at `stage="request"` is a check that did not run, which is what
  `fail_on.fail_on_error` governs: `fail_on_error: false` lets it pass as it lets any rule error
  pass, and `docs/profiles.md` says so beside the switch.
- `read_with_retry` turns a `TimeoutError` into `EndpointUnreachable("<ref> did not answer
  within N seconds")` and any other non-HTTP `OSError` or `http.client.HTTPException` raised
  while sending into `EndpointUnreachable("connection to <ref> failed: …")`;
  `EndpointUnreachable(EndpointError)` is new in `target/endpoint.py`, so a judge's `ask` can
  say "could not be reached" for it rather than "sent a reply guardana cannot use". Neither is
  retried.
- `StopReason.TARGET_UNAVAILABLE = "target_unavailable"` maps to `4` in `exit_code_for`; the
  engine now owns `4` for a result as it owns `6` and `7`. It outranks `budget_exhausted` when
  pooled rules stop for both reasons — in the `Runner.run` loop and in `ScanResult.merged`
  alike. The rule in flight is cut off like a budget stop (out of
  `rules_run`, its findings and assessments kept); no further rule starts; `_RuleOutcome`
  carries both the stop and a `CheckError(source=<rule id>, stage="target", reason=<message>)`,
  and `Runner.run` records the error beside the stop (one per rule the failure cut off). A
  probe pass that stopped ends the probe (`probe.run_target_probe`).
- The message is built once in core, `guardana.core.target.failure.describe_failure(exc, ref,
  quoting, remedies)`, moved from `cli/_errors.py` (`_status_message`, `_body_snippet`): the
  status, the start of the body under the run's privacy policy, the run's secrets withheld.
  `remedies` is a `FailureRemedies(auth: str, rate_limited: str)` of plain strings, so core
  names no CLI flag. `Verifier` takes `secrets: tuple[str, ...]` (`repr=False`) and `remedies`
  and threads them through `run_target_probe` to `Runner`; the CLI passes the connection's
  secret values and its own remedies, and prints the recorded reason after `error:`.
- `probe` writes `run.json`, the kept exchanges and the reporter submission for a stopped run as
  for any other; `recipe run` swaps in the partial artifact; `Verifier` returns the stopped
  `Verification` instead of raising. `TargetUnavailableError` stays exported and is raised only
  for a failure the runner did not classify.
- `monitor`: a cycle stopped by its target is a cycle that could not be sampled, as a failing
  cycle is today — a warning, never the baseline, `_WORST_LAST` unchanged, and the CLI's
  existing unsampled path gives exit `4`; a first cycle that stopped exits `4` with its cause.
  A finding the stopped cycle produced is still proven: when the partial result fails the
  policy with the stop set aside, the cycle alerts (printed and submitted) and folds `1` into
  the worst code, before re-raising when it is the first cycle.
- `diff`: `_STOP_EXPLANATIONS` names the new stop; a stopped side is incomplete, as for a
  budget stop.
- Unchanged: `target inspect`, `calibrate`, a judge failure (exit `4`, nothing saved); MCP
  servers keep reporting their own failures inside the run.

Rejected: retrying a `400` (the application answered); keeping exit `4` for a `400` (the code
would name the wrong cause, and the graded requests would be lost); a new exit code for a
partial run (a stop already outranks the verdict, and `4` already means the target failed).

### 5. Pacing is a budget

`budgets.max_requests_per_minute` (positive integer; `--max-requests-per-minute` wherever the
four budget flags are). `UsageMeter.reserve` claims the next slot under the meter's lock — slots
at least `60 / N` seconds apart — and sleeps outside it, so concurrent rules and retries share
one rate without stalling `record`; it raises `BudgetExhausted` instead of sleeping past
`max_duration`. `Budgets.is_unbounded` counts the rate. `UsageMeter` takes `sleep=` beside its
`clock=`; the tests use a fake clock. Each meter the profile's budgets reach paces itself: the target's, and
each judge's own. A target that sends nothing accepts the budget as it accepts `max_requests`.
`plan probe` states the floor on wall time (estimated requests, retries not counted, × 60 / N)
and refuses (exit `3`) when `max_duration` is set below it; plan schema 4 adds
`budgets.max_requests_per_minute` and `minimum_wall_time_seconds`. The field carries
`OMITTED_WHEN_DEFAULT` (`profile/digest.py`), so existing recipe locks do not drift.
`cli/config.py` and `cli/_budget_flags.py` list it.

### 6. A floor on the share of graded cases

In `Runner.run`, beside `_coverage_shortfall`, so `probe`, `grade` and `monitor` all get it,
for each rule that recorded assessments: `graded / attempted`, where graded
is `measured` and attempted is every assessment that is not `skipped` (a rule whose every
assessment was skipped is not checked). A rule that attempted cases and graded none is a
coverage shortfall of a new kind, `ungraded_cases`, under every policy — a check whose every
case was declined or undecidable established nothing, which `fail_on_inconclusive` should not
be needed to say. `policy.fail_on.min_graded_share`, a number in `(0, 1]` unset by default and
in every preset, raises that bar: a rule below it is the same shortfall ("graded 3 of 10 case
attempts (30%), below the floor of 80%"). A shortfall has no switch, so the run is
`indeterminate` unless a finding fails it. `plan` cannot foresee it and says so in its human
output when the floor is set. `FailOn.min_graded_share` carries `OMITTED_WHEN_DEFAULT`. The
`ShortfallKind` docstring stops calling every kind the operator's demand.

Rejected: one share over the whole run (a rule graded nowhere hides behind one graded
everywhere); a new `fail_on_*` switch (a floor the team wrote is a demand, as a suite's
`min_sample` is).

### 7. A recipe names an installed target

Recipe schema 3: `subject.target: {locator: "acme-chat://staging", options: {key: value}}`
(`options` as `--target-option`), exactly one of `connection`, `recording`, `target`.
`subject.kind` stays required. Refused with exit `3`, as `probe --target` refuses them:
`fixtures` beside `target`, `output.exchanges: true` with a target that cannot keep exchanges
(`probe` accepts `EndpointTarget` and `SeededTarget`), a locator whose scheme is unknown or of another kind. `recipe lock` builds the
target through `resolve_target`, as `plan probe` does; the `Target` contract forbids
construction from contacting it, and a construction that fails to connect anyway exits `4` as
it does for `plan`. The lock pins `target: {scheme, distribution, version}` (drift
`target_changed`); `SubjectSource`, `Recipe.source` and `run.recipe.source` gain `target`. Schema 1 and 2 recipes are read as before
and keep their digest.

### 8. A directory-installed distribution is pinned by its files

Recipe lock schema 2 adds `sources: {<distribution>: {digest: "sha256:…", files: N}}` for every
distribution that moves under one version (`direct_url.json`) and either has a Guardana entry
point plugin trust let the run import, registers a selected rule, an evaluator a selected rule
grades with, or the recipe's target, or is in the installed `Requires-Dist` closure of one of
those (a helper library installed editable moves the checks
as much as the pack does). The closure follows every `Requires-Dist` whose PEP 503-normalised
name is installed, markers and extras ignored (an over-approximation), with no new dependency.

- **Editable** (`dir_info.editable: true`): the digest covers the directory the `file://` URL
  names — every file under it, untracked ones included, except `.git/`, `__pycache__/`,
  `.venv/`, `venv/`, `.tox/`, `.nox/`, `node_modules/`, `build/`, `dist/`, `*.egg-info/`, the
  tool caches (`.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`), local leftovers (`.DS_Store`,
  `.idea/`, `.vscode/`, `.coverage`, `htmlcov/`, `.env`) and the recipe's own lock and output
  directory — by sorted POSIX relative path and SHA-256 of content. The source directory holds
  the code, its package data and its manifest; a `.pth` file or setuptools finder the
  `RECORD` lists that adds or maps a path outside it leaves the distribution unpinned.
- **Any other direct URL** (a non-editable directory, a VCS checkout, an archive): the digest
  covers the distribution's installed `RECORD` entries (path and recorded hash), except
  bytecode under `__pycache__/`, the installer's own `.dist-info` files, and the console
  scripts generated outside the install root or under `*.data/scripts/`.
- Above 20,000 files or 256 MiB, with a symlink leading outside the directory, or with no
  `RECORD` to read, the distribution stays under `unpinned` with the reason. `recipe lock` exits
  `2` only for what is still unpinned. Drift `source_added`, `source_removed`,
  `source_changed`.
- A schema 1 lock is read with `sources` empty (`parse_lock` requires keys per schema); compared
  with a current lock it drifts `source_added` for every movable distribution, beside the
  `guardana_changed` every upgrade brings. `recipe lock` writes schema 2, digest tag
  `recipe-lock-v2`.
- The seam: `lock_of(..., pin_source: Callable[[str], SourcePin | str])` beside `movable`, where
  a string is the reason a distribution stays unpinned (the CLI binds the recipe's lock path
  and output directory as `leave_out`); the CLI tests that patch
  `moves_under_one_version` patch it too. `recipe run` recomputes the lock on every run, so it
  re-hashes each editable tree, within the bounds above.

### 9. A scan of a target with no file is not a pass

A `FileReader` target whose file scope holds no file other than ignore files (`.guardanaignore`,
wherever it sits) carries a coverage shortfall of a new kind, `empty_target`, named by the
target's ref ("holds no file to scan — check the path, or the excludes that removed every
file"). Any other file counts, a stray `.DS_Store` included, because the scan listed it, not
because a rule read it. Computed once,
by a function `Runner.run` and `build_plan` both call, so `plan scan` refuses it (exit `3`) and
`scan` is `2` under every preset.

### 10. A model or notebook a rule could not read is an unexamined component

Every place a model-reading rule now yields an inconclusive "not scanned" finding — the
notebook as a whole (`notebook_payload`), `pickle_opcode` (every `_unscanned` call, the opcode
bound of an archive included, an unresolvable or unread remainder after callables already
found, and a `.bin` file it cannot open), `onnx_graph`, `keras_lambda`, `chat_template`,
`model_format` (safetensors unreadable or with a malformed header, a truncated PMML) and
`saved_model_ops` (a graph cut by the bound or unreadable) — also calls `ctx.shortfall(CoverageShortfall(UNEXAMINED_COMPONENT, name=<path>, detail="<rule id>
could not read it: <reason>"))`. The finding stays (the collector envelope carries findings and
no shortfall), and so does `ctx.examined(path)`, so the runner's own inventory pass does not
name the file a second time. No switch, so `indeterminate` under every preset, `ci` included.
Every `UNEXAMINED_COMPONENT` and `EMPTY_TARGET` name is relativized with the findings
(`report/location.py`; a format name passes unchanged) and the scan root is stripped from the
detail where a path starts, as from a finding's evidence, so a saved run names the same file on a laptop and in CI.
The tests that compare `_unexamined` maps (`rules/tests/test_unexamined_components.py`) gain the
per-file entries. Unchanged: a notebook *cell* that does not
parse as Python (magics are ordinary) and the non-model rules' unscanned findings. A raw
pickle's unresolvable global is a shortfall like any other: the opcodes after it were never
read.

### 11. `pickle_opcode` reports one finding per file

One `CRITICAL` finding per file, summary `unpickling imports N non-allowlisted callable(s)
(set <digest>): a, b, c` naming every callable, sorted and unique; the digest is the first 12
hex of the SHA-256 of the newline-joined set. The fingerprint hashes the summary, and the
digest sits before the evidence bound can cut a long listing, so a swapped callable is a
different finding however many there are. The detail lists each callable with its archive member.
Callables collected before a later member raises are reported, not dropped. Every fingerprint
of this rule moves; the changelog says to regenerate baselines and waivers for it.

### 12. Persisted documents

- **Run schema 16** (`schemas/run-v16.schema.json`): `stopped_by` gains `target_unavailable`;
  shortfall kinds gain `empty_target` and `ungraded_cases`; an assessment's `reason` gains
  `target_declined`; `run.recipe.source` gains `target`; `settings.budgets` gains
  `max_requests_per_minute`. A schema-15 run migrates with `max_requests_per_minute: null`.
- **Plan schema 4** (`plan-v4`): the budget block gains `max_requests_per_minute` and
  `minimum_wall_time_seconds`. The plan document carries no shortfall (`RunPlan.shortfall` is
  not in it), so nothing else moves.
- The run migration is `migrate_v15` (`manifest/migrations.py`), registered in
  `report/load.py`, the history in `manifest/model.py`, pinned by `test_run_schema_v16.py`.
- **Recording format 3** (`recording-v3`): a line holds `reply` or `declined`, and optional
  `meta`; formats 1–3 are read, 3 is written.
- **Recipe schema 3** (`recipe-v3`), **recipe lock schema 2** (`recipe-lock-v2`): decisions 7
  and 8. The round-trip registry (`test_every_persisted_schema_has_a_round_trip.py`) covers all
  five.
- Adapter files carry no version; a 0.38 adapter using the new keys fails loudly on 0.37.
- The collector envelope is unchanged: it carries `gate`, the errors and the unscanned findings;
  it still carries no shortfall, so a run `indeterminate` only for an empty target reaches the
  collector with its gate and without the cause (backlog).

### 13. The rest of the owner's decisions

- **`pack validate` checks owners of all four kinds.** Evaluators and targets read the origins
  the registry records. Taxonomy discovery records, per framework, every distribution that
  registered a reference into it — a second registrant of an identical reference included —
  kept by the registry snapshot; `Registered` gains `taxonomy_owners: Mapping[str,
  frozenset[str]]` beside the unchanged `taxonomies`, and a declared framework passes when the
  pack's distribution is among its owners. A manifest given by path stays checked by kind.
- **MCP authorization discovery connects to the address it checked.** Discovery requests use a
  connection class whose `connect` resolves the host once, applies the address check to every
  address, and dials an accepted one, sending the host name as `Host` and TLS SNI and verifying
  the certificate against the name; a redirect hop opens a new connection and is checked the
  same way. `_send` takes a discovery-only flag that selects this connection (the server's own
  requests keep theirs). A refusal at connect time raises `AddressRefusedError(McpError)`, which
  `_fetch` records as a refused document, not an unreadable one; the docstring that called
  pinning future work is rewritten. Whether the server under test is local is decided once per discovery, not per
  fetch. Discovery uses no HTTP proxy: a proxy resolves the name again. A host that does not
  resolve is a document that could not be read, not a refused address. The `--mcp` server
  address itself is unchanged (the operator chose it).
- **`guardana-collector`**: any exception from `connect()` itself exits `4` from every command
  that needs the database, `status` included (`EXIT_UNAVAILABLE` in `server/cli/codes.py`);
  once it returned, an error stays `1`. `serve` opens its own pool and is unchanged.
- **Principle 3** reads: "Offline, no account, always: traffic goes only to destinations the run
  names — the target under test, a judge or guard the profile configures, and the authorization
  metadata the target itself advertises; the collector is optional in every direction."
  (`CLAUDE.md`, `docs/maintainers/lessons.md`, `CONTRIBUTING.md`,
  `.claude/skills/stack/SKILL.md`.)

## Exit codes after this change

| situation | before | after |
|---|---|---|
| `scan` of a path with no file | `0` | `2`; `plan scan` `3` |
| an unreadable model or notebook under `ci` | `0` | `2` |
| a rule whose every case went ungraded, under `ci` | `0` | `2` |
| an undeclared HTTP `4xx` during `probe` | `4`, nothing saved | `2`, run saved |
| the target fails part-way | `4`, nothing saved | `4`, partial run saved |
| a read timeout | `2` | `4`, partial run saved |
| `guardana-collector` without its database | `1` | `4` |

## Breaking changes

The rows above; `Verifier` returns a stopped result where it raised `TargetUnavailableError`
(`test_verify_surface.py` moves with it);
`pickle_opcode` fingerprints; `pack validate` may fail a pack that claims an evaluator, target or
framework another distribution registers; MCP discovery ignores `HTTP(S)_PROXY`;
`HttpAdapterTransport`'s injectable `fetch` returns status and body; run schema 16, plan schema
4, recording format 3, recipe schema 3 and recipe lock schema 2 are refused by 0.37.

## Not done here

An MCP server failing part-way (its failures stay rule errors); a judge failing mid-run keeping
the partial run; declines on the built-in provider transports; tools through an adapter;
per-case request fields; profile `evaluator_config:` for third-party evaluators; coverage
shortfalls in the collector envelope.
