---
title: "guardana plan"
nav_order: 170
summary: "`guardana plan`: what a run would cost, before it costs anything"
status: stable
---

# `guardana plan` — what a run would cost, before it costs anything

`guardana plan` estimates request costs when you need to budget a probe or scan without sending a request.

```bash
guardana plan probe --url https://api.example.com --model gpt-4o-mini
```

```text
14 rule(s) would run, 9 skipped.
requests: at least 14, at most 47
trials: 1 attempt(s) per case, counted in the requests above
judge calls: none — no selected rule grades with a judge

No request was sent to produce this estimate.
```

```bash
guardana plan scan .
```

```text
19 rule(s) would run, 0 skipped.
requests: 0 — every selected rule declares it sends nothing

No request was sent to produce this estimate.
```

A file scan of the built-in rules is free and complete: every one of them reads
files, never a model, and declares that about itself — see
[Where the numbers come from](#where-the-numbers-come-from). A third-party
artifact rule that stays silent about its cost is not assumed to be free; it
shows up in `unknown_cost` exactly like an undeclared endpoint rule would.

`--format json` gives the same numbers to a pipeline, with a `schema_version`.

## Flags

`plan scan` and `plan probe` both discover plugins to build the same registry the
run they are pricing would use, so both take the same plugin-trust flags
`scan`/`probe` do:

| Flag | Default | Meaning |
|---|---|---|
| `--target SCHEME://LOCATOR` | none | Build a trusted installed target of the kind selected by `plan scan` or `plan probe` |
| `--target-option KEY=VALUE` | none | Repeatable, non-secret configuration passed to that target |
| `--plugins [all\|builtins\|allowlist\|disabled]` | `builtins`, or the profile's `plugins:` | Which installed plugins to load — same meaning as on `probe` |
| `--allow-plugin TEXT` | none | Distribution to trust; repeatable, needs `--plugins allowlist` |
| `--trials INTEGER` | `1` (or `trials:` in the profile) | `plan probe` only: price the run at this many attempts per case, as `probe --trials` would make them |
| `--max-requests`, `--max-input-tokens`, `--max-output-tokens`, `--max-duration` | the profile's `budgets:` | `plan probe` only: check the plan against these ceilings, as `probe` would apply them |

`plan scan` also keeps `--no-plugins` as a deprecated alias for `--plugins disabled`,
exactly like `guardana scan` does.

Target construction is configuration-only: `plan` calls the same
`from_locator` classmethod as the real command, but a conforming target does not
contact the system until a run or inspection starts.

## Where the numbers come from

Each built-in rule shape declares an upper bound on the requests it will send
(`Rule.estimated_requests`): a YAML rule knows how many prompts it has, a
scenario how many steps, an agent rule its step budget. The plan sums the rules
the profile selects and the target can satisfy — the same selection the runner
would make.

`Rule.estimated_requests` defaults to unknown for every target kind, artifact
included: `guardana-core` has never read a rule's code, so it cannot promise an
artifact rule sends nothing — a third-party rule can do its own network I/O
exactly like an endpoint rule can. The 19 built-in artifact rules declare the
zero themselves, on their own base class in `guardana-rules` — not a public
extension point, so a third-party artifact rule declares its own
`estimated_requests` rather than inheriting theirs.

The declaration is **measured, not trusted**, on both sides of that split. A
gate in `guardana-rules` runs every shipped endpoint rule against a model that
never refuses, counts the requests it actually sends, and fails if any rule
spends more than it declared. A second gate runs every shipped artifact rule
with outbound connections blocked at the socket layer, and fails — naming the
rule — if one ever tries to open one: for a rule that only reads files, zero is
the only honest number, so there is nothing to spend less or more of. Either
way, the ceiling is a claim somebody checks, not a promise.

## Pricing repeated trials

`--trials N` multiplies what each rule that repeats will send, and the plan says which
rules will not repeat, so the count is the run's, not an estimate of it:

```bash
guardana plan probe --mcp https://mcp.example.com --trials 5
```

```text
9 rule(s) would run, 14 skipped.
requests: at least 9, at most 59
trials: 5 attempt(s) per case, counted in the requests above
  9 rule(s) make one attempt per case whatever --trials says, because their verdict does not depend on a sampled reply:
    • guardana.agent.mcp_server_manifest
    • guardana.mcp.unauthenticated_access
    …
```

`--format json` carries the same facts as `trials.per_case` and `trials.single_attempt`
(plan schema `3`, [`schemas/plan-v3.schema.json`](../schemas/plan-v3.schema.json)). See
[`usage-probe.md`](usage-probe.md#repeated-trials) for what a trial is.

## Pricing judge calls

A rule graded by a judge configured under `evaluators:` — `llm_judge`,
`reference_judge` or `guard` — spends judge calls as well as target requests, and
each judge meter is bounded by `max_requests` on its own. `plan probe` builds those
judges from the profile, sends them nothing, and prices each meter: the verdicts a
rule grades (`Rule.graded_verdicts`: prompts × K, cases × K for a suite, graded steps
× K for a scenario, sessions × K for an agent run) times the calls one verdict costs
(`Evaluator.judge_calls_per_verdict`: `min_agreement` for `llm_judge` and
`reference_judge`, which share one meter; `1` for `guard`).

```text
requests: at least 1, at most 90
judge calls: at most 270
  llm_judge, reference_judge (one judge, its own meter): at most 270 call(s) against a budget of 100
⚠ this plan does not fit its request budget — the run would stop early,
  and a run that stops early reports no verdict
```

That is a 30-case suite graded by `reference_judge` at `--trials 3` with
`min_agreement: 3`. A rule or evaluator that does not declare its judge calls is
named under the judge line like an unknown-cost rule; while a judge is configured,
such a plan does not claim to fit. `plan scan` never prices judges, because `scan`
never builds one. In JSON, `judge_calls` carries `max`, `meters`, `unknown_cost` and
`complete`, and is `null` for `plan scan`. Judge tokens are not predicted.

## Plan the run you are going to make

`plan probe` takes `--safety` and `--allow-destructive`, with the same meaning
they have on `probe`. They are not decoration: the runner refuses a rule that
reaches further than the run permits, and until 0.7.1 the plan did not apply that
check — so pricing a `--safety passive` probe listed every active rule that run
would go on to refuse. The selection is now literally the runner's, called from
one place, so a second copy cannot drift from the first.

```bash
guardana plan probe --url https://api.example.com --model m --safety passive
```

## Pricing an MCP server

`plan probe --mcp` prices an MCP run the same way, and it is where this command
earns its keep. Reading a manifest costs three requests; the authorization checks
send around a dozen, which is exactly the number somebody wants before pointing
this at production.

```bash
guardana plan probe --mcp https://mcp.example.com/mcp
```

**The ceiling is higher than any run spends, on purpose.** Each rule declares what
it would cost *alone*, because a plan cannot know which rule runs first — and the
first one to look buys an observation the rest then share — including the single
`server/discover` call that settles which revision of the protocol the server
speaks. A whole MCP probe declares around sixty requests and spends around a
dozen. An upper bound that is too
high refuses a budget that would have fitted, which is the safe direction to be
wrong in; the other way round is a ceiling that lets a run overspend.

**An stdio server is priced by refusing.** Working out what one would cost means
starting it, and starting the thing under examination is the one thing this
command must not do. `guardana probe --mcp … --allow-exec` is where that intent is
stated out loud.

## Pricing a grade

`plan grade RECORDING` previews [`guardana grade`](usage-grade.md): it selects the rules
the grade would run, lists every rule the recording does not answer as skipped
`not_recorded`, prices the judge calls, and counts no target request, because every answer
comes from the recording. It takes `--profile`, `--preset`, `--rules`, `--plugins`,
`--allow-plugin`, `--trials`, `--max-requests` and `--format`, and refuses an unreadable
recording with exit `3`.

```bash
guardana plan grade answers.jsonl --rules rules/ --profile guardana.yaml
```

## When the plan does not know

A rule that declares no request count — anything third-party that has not
implemented `estimated_requests` — is **named, not counted as free**:

```text
7 rule(s) would run, 0 skipped.
requests: at least 7, at most 22 — plus 2 of unknown cost
  these rules do not declare a request count, so the ceiling above is a
  lower bound on the worst case:
    • acme.custom.deep_probe
    • acme.custom.fuzzer
```

A plan with an unknown-cost rule never reports that it fits a budget, whatever
the numbers look like. Its ceiling is not a ceiling.

## Checking against a budget

If the profile (or a flag) sets `max_requests` and the worst case — of the target
or of any judge meter — exceeds it, the plan says so and exits `3` — invalid
configuration, found before the run rather than halfway through it:

```text
⚠ this plan does not fit its request budget — the run would stop early,
  and a run that stops early reports no verdict
```

A token ceiling a judge's transport cannot enforce is refused with `3` too, the same
way `probe` refuses it.

## A run that could not pass

The plan exits `3` as well when the run it describes could not pass, and says why
on stderr, one line per cause:

- **no rule would run** — the profile, the flags and the target select none, and a
  run that verifies nothing reports no verdict;
- **a rule it would skip while `fail_on.fail_on_skipped` is on** — a capability the
  target does not declare, or a safety mode that refuses the rule;
- **a file under `calibrations:` that would stop the run** — missing, unreadable, or
  measuring an evaluator another file measures too;
- **an error the run would record before its first rule** — a rule file that does not
  load, a plugin the trust mode refuses (the line names the distribution and how to
  admit it: `--plugins allowlist --allow-plugin <distribution>`, the profile's
  `plugins:`, or `--plugins all`), a rule whose `expect:` block its evaluator cannot grade, or a
  capability the target declares without implementing. The plan reads these from the
  same function the run does, so the two never list different errors.

With `fail_on.fail_on_error: false` the errors are printed as a warning and the plan
keeps its exit code, as the run would pass them. The JSON document on stdout is the
same either way.

The plan decides with the gate's own list of what leaves a run unanswered, applied to the
rules it would run, the rules it would skip and the errors it would record, so the plan and
the run cannot disagree about a skip, an error or an empty selection. The
[`release` preset](profiles.md#release-complete-coverage-or-no-pass) turns
`fail_on_skipped` on.

## What it cannot tell you

Capabilities are read from what the target declares locally, so an endpoint that
turns out not to support tool calls will skip more rules than the plan predicted.
Asking the endpoint would make this command cost money, which is the one thing it
must not do. `guardana target inspect` is where that question belongs.

Whether a check reaches a verdict is known only when it runs. With
`fail_on_inconclusive` or `fail_on_skipped` on, as in `--preset release`, the plan says so
on stderr, whether or not it refuses:

```text
note: fail_on_inconclusive is on — only the run can tell whether a check declines to reach a verdict, so this plan cannot promise a pass
note: fail_on_skipped is on — an endpoint may turn out not to support what it declares, and the run would then skip more rules than this plan lists
```

The second note appears for `plan probe` only.

A selected rule that grades with an evaluator nobody configured is refused by the plan in
the words the run would record. The plan finds the evaluator through the rule's declared
expectations, so a Python rule that reads an evaluator it does not declare is caught only
when it runs.

Tokens and wall time are not predicted. Nothing can know what a request will cost
before it is answered, and a guessed figure is one a team would budget against.

## See also

- [`docs/profiles.md`](profiles.md) — the `budgets:` block in `guardana.yaml`
- [`docs/exit-codes.md`](exit-codes.md) — what `3` and `6` mean
- [`docs/usage-run.md`](usage-run.md) — what a finished run actually cost
