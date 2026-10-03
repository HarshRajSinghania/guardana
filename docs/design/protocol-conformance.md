---
title: "Protocol conformance against servers Guardana did not write"
nav_order: 91
summary: "both MCP revisions and one A2A v1 agent checked against servers built on the protocol owners' own SDKs, task listings and registry entries graded, a server that lacks what a rule examines recorded as missing coverage, and an MCP server that fails part-way stopping the run it leaves"
status: accepted
---

# Protocol conformance against servers Guardana did not write

**Status:** accepted, implemented — ships in the next release · **Written:** 2026-10-03 · **Serves:** ROADMAP v0.39
(F7) and the MCP items the backlog lists under the guarded-application release · **Amends:**
[`mcp-protocol-eras.md`](mcp-protocol-eras.md) (how a legacy revision is detected, version
handling), [`guarded-applications.md`](guarded-applications.md) decision 4 (MCP servers join
the stop)

## The question

Guardana speaks MCP `2025-11-25` and `2026-07-28`, and every server it has been tested against
is one it wrote: `ScriptedMcpServer` or a thread serving JSON. A client and a server written by
the same hands share one reading of the specification, so a misreading passes both. F7 asks for
proof against independent servers, for five MCP subjects — authorization, task identity, cache
scope, registry metadata and version changes — and for one A2A v1 agent covering the agent card,
caller identity and task visibility. A capability a server does not support is recorded as
missing coverage, never as a pass.

Four MCP gaps left by 0.38.0 belong to the same surface: an MCP server failing part-way leaves
rule errors instead of a stopped, saved run; the discovery guard does not unwrap NAT64 or 6to4
addresses; a third-party `Sender` must accept a `discovery` keyword or pinning is skipped; and
`is_local_address` is public with no caller.

The first independent server already disagreed with Guardana's reading: an `mcp` 2.3.0 server
lists only modern revisions in `server/discover` and still answers `initialize`
(`mcp/server/lowlevel/server.py`, `_handle_discover`). Guardana reads such a server as
modern-only, so `session_binding` is silent about the sessions it hands every legacy client.
Decision 3 settles that question by asking it.

## What exists, so this does not rebuild it

- Era negotiation (`core/target/_mcp_client.py`, `negotiate`): `server/discover` first, `-32022`
  re-chooses, anything else falls back to `initialize`. `SUPPORTED_VERSIONS` is `2026-07-28`,
  `2025-11-25`. Only `agreed` is recorded (`McpServerTarget.protocols()` → `coverage.protocols`).
  A legacy `initialize` answer is stored verbatim and never checked; `notifications/initialized`
  is never sent.
- `McpAuthorizationView` (`_mcp_authorization.py`): lazy sections `anonymous`, `discovery`,
  `foreign_token`, `sessions`, built from a copy of the negotiation taken before any handshake
  (`target/mcp.py`, `authorization()`); every request metered; a section that raised is not
  cached. Eight `guardana.mcp.*` rules read it; `agent.mcp_server_manifest` reads `list_tools()`.
- `McpError` is not an `EndpointError`: the view swallows it into observations; on the manifest
  path it is a rule error. The runner's stop (`_failed_send`, `failure_scope`,
  `StopReason.TARGET_UNAVAILABLE`) catches `URLError` and `EndpointError` for an `ENDPOINT`
  target; `McpServerTarget.kind` is `ENDPOINT`.
- The discovery guard (`_mcp_http.py`, `refusal_for`, `_refused_address`, `_inside`) unwraps
  IPv4-mapped addresses only: every `64:ff9b::/96` address is refused as reserved, a global one
  included, and `2002:a9fe:a9fe::` (the metadata address in 6to4 form) passes beside a local
  server.
- `Sender` carries `alongside` and `discovery`, which only discovery fetches use.
- `SkipReason` (`core/report/skipped.py`) has no reason a rule can raise at run time.
- No A2A code exists.

## Decisions

### 1. "Not offered" is a run-time skip, a coverage gap

`NotOffered(Exception)` (new, `guardana.core.rule`, exported beside `Rule`): `NotOffered(detail:
str, *, missing: tuple[str, ...] = ())`. A rule raises it, before yielding anything, when the
target does not offer what the rule examines. The runner records `SkippedRule(rule_id,
SkipReason.NOT_OFFERED, missing, f"{target.ref}: {detail}")` — worded like the other skips —
and the rule stays out of `rules_run`. `SkipReason.NOT_OFFERED = "not_offered"`;
`is_coverage_gap` is true, so `fail_on_skipped` (and `--preset release`) refuses a pass and the
default preset lists the skip.

- `Runner._run_rule` catches `NotOffered` before the generic `except Exception`. Findings already
  yielded are kept, as for any error, and the rule records `CheckError(stage="run",
  reason="raised NotOffered after reporting")` instead of a skip.
- `_RuleOutcome` gains `skipped: SkippedRule | None`. `_RuleOutcome.ran` is false for it and
  `Runner.run` appends it to the skipped rules after the selection skips, in rule order;
  `ScanResult.merged` keeps it. `verify.py` catches it before its own generic catch.
- `detail` passes through `bounded_reason`. The human report prints it like any skip; JSON lists
  it; SARIF and JUnit list no skip, as today. The reporter already sends a skip's reason as a
  string and the collector stores any string (`server/envelope.py`), so the envelope does not
  move; a collector test round-trips `not_offered`.
- `FixtureOutcome.NOT_OFFERED = "not_offered"` is new and `verify_rule` reports a rule that
  raised `NotOffered` as that outcome, never as `inconclusive`. `_gaps` still demands finding,
  clean and inconclusive fixtures only, so no existing rule gains a gap.
- `docs/writing-rules.md` documents it beside `inconclusive`: `NotOffered` is "this target has
  none of what I examine"; `inconclusive` is "I asked and could not tell".

Rejected: a coverage shortfall (any shortfall makes a run `indeterminate` under every preset, so
every server without tasks would fail every gate); silence (reads as a verified invariant); an
inconclusive finding (says a question was asked and not answered).

**Unchanged on purpose.** `cache_scope` stays silent on a legacy server and `session_binding` on a
server observed to be modern-only ([`mcp-protocol-eras.md`](mcp-protocol-eras.md)). There the
revision in use has no such mechanism and the server observably used none — the question was
answered. `NotOffered` is for an optional capability the server shows it does not have.

### 2. An MCP server that fails part-way stops the run and keeps it

Decision 4 of [`guarded-applications.md`](guarded-applications.md) now covers MCP servers. The
classification happens in exactly two places: `HttpMcpTransport.request` (and the stdio
transport) — **the conversation** — and `_Probe._call` — **the probes**, the view's own requests
to the server URL. `_fetch`, the discovery GETs, never stops a run, whatever host it reaches,
the server's own origin included: a protected-resource document's `404` stays the finding
`authorization_discovery` reports today.

In order, first match wins:

| what came back | conversation | probes |
|---|---|---|
| the sender raised (no reply): any `McpError` but `RedirectRefusedError` and `AddressRefusedError` | stop, `EndpointUnreachable` | stop, `EndpointUnreachable` |
| `401`, `403`, `407` to a request that carried the operator's credential | stop, `HTTPError` (credential remedy) | — (probes carry no credential, or strip it on purpose) |
| a JSON-RPC error member (`error` is an object with an integer `code`, the test `error_from` applies) | an answer: `McpProtocolError`, as today | an observation, as today |
| `-32022` once the era is settled | decision 3 | decision 3 |
| `401`, `403` without a credential configured | `McpError`, a rule error, as today | an observation, as today |
| `404`, `408`, `425`, `429`, `5xx` | stop, `HTTPError` | an observation, as today |
| another `4xx` | `HTTPError`, an error of the rule (`stage="request"`); remembered | an observation, as today |
| a `2xx` that is not a JSON-RPC response object | stop, `UnreadableReply` | an observation, as today |

- `UnreadableReply(EndpointError)` and `TargetChanged(EndpointError)` are new in
  `target/endpoint.py`, beside `EndpointUnreachable`; their messages name the target, and
  `describe_failure` quotes all three verbatim (today an `EndpointError` other than
  `EndpointUnreachable` reads "could not reach endpoint", which is wrong for a reply that
  arrived). Messages: "the MCP server at `<ref>` did not answer: `<cause>`"; "the MCP server at
  `<ref>` sent a reply that is not JSON-RPC (HTTP `<status>`, `<n>` bytes)". An HTTP failure is
  raised as `urllib.error.HTTPError(display_url, status, reason, headers, BytesIO(body[:4096]))`
  with the headers as an `http.client.HTTPMessage`, so `failure_scope` and `describe_failure`
  read it as they read an endpoint's. None of these subclasses `McpError`, so the view's
  handlers cannot swallow them; they leave `rule.run` and reach `_failed_send` unchanged.
- **Remembered:** a request-scoped failure of the conversation is cached and re-raised by every
  later reader without sending again, so a `400` costs one request, not one per rule.
- A `404` in the conversation while a legacy session is in force re-opens the session once, as
  the `2025-11-25` binding requires; a second `404` stops the run.
- `negotiate()` still falls back to `initialize` on whatever its `server/discover` probe meets —
  `McpError`, `EndpointError`, `URLError`, `OSError` — and never on `BudgetExhausted`, which
  stops the run as a budget stop. Over stdio, requests carry increasing ids, a timed-out
  `server/discover` does not break the stream, and a reply to an id nobody awaits is discarded
  (at most 16 such lines per request, then `UnreadableReply`). An stdio server that exited,
  closed its output or did not answer a later request within the read timeout is
  `EndpointUnreachable`; an over-long or non-JSON line is `UnreadableReply`; a command that
  could not be started exits `4` with its message, before any rule.
- `Sessions.sampling_error: str | None` is set when a handshake was answered with a JSON-RPC
  error or a status other than a result before any id was collected; `session_binding` reports it
  as inconclusive ("session sampling stopped: `<reason>`") rather than "the server issues no
  session id". A `2xx` result without `Mcp-Session-Id` stays "issues no session id".
- `run_mcp_probe` passes `Verifier` remedies naming `--mcp-token-env` (and the A2A command
  `--a2a-token-env`); `EndpointFlag` and `remedies_for` (`cli/_errors.py`) gain both flags.
- `write_pin` (`cli/_mcp_run.py`) catches `EndpointError` and `HTTPError` beside `McpError` and
  exits `4` with `describe_failure`'s message.
- `probe --mcp` against a server that does not answer exits `4` and writes `run.json` with
  `stopped_by: target_unavailable`; `Verifier` returns the stopped `Verification`.

Rejected: keeping MCP failures as rule errors (exit `2` names the wrong cause and spends one
failure per rule); stopping on a probe's status (an auth proxy that answers the anonymous probe
with a login page, or a session-bound server that answers the stripped request `404`, would stop
a run whose conversation works).

### 3. One live negotiation; version changes are outcomes, never a mixed-revision pass

- **The view reads the target's negotiation, not a copy.** `McpServerTarget` owns one locked
  `Negotiation` and one cached **opening** — the `initialize` result (`version`, `capabilities`,
  `server_info`) of the conversation, opened with the operator's credential when one is
  configured — and the view receives callables for both. `initialize()` returns that opening
  record instead of the version alone.
- **Every handshake checks the revision it was answered with** — the conversation's, the
  anonymous probe's, the session sampler's and the legacy probe's below. `2025-11-25`: accepted.
  `-32022` with `data.supported` before the era is settled: settled again, as
  `_open_the_handshake_era` does today. Any other revision, or none: `Negotiation.unsupported` —
  "the server answered initialize with `<v>`" or "… with no revision"; "guardana speaks
  2026-07-28 and 2025-11-25". The specification says a client SHOULD disconnect from a revision
  it does not support; today the run speaks `2025-11-25` at such a server and records the older
  revision, claiming a conversation that did not happen in it. The anonymous probe returns
  `Anonymous(error=<that sentence>)`, so every authorization rule is inconclusive; the manifest
  rules report it as they do for a modern server with no revision in common.
- **Settled** means `Negotiation.agreed is not None` or a modern wire was chosen. After that, a
  `-32022` on any request, conversation or probe, raises `TargetChanged`: "the MCP server at
  `<ref>` stopped accepting revision `<agreed>` during the run; it now offers `<list>`" (or "…
  and named no revision it offers"). The run stops, saved, exit `4`, with
  `StopReason.TARGET_CHANGED = "target_changed"` (new): the server still answers, so
  `target_unavailable` would name the wrong cause. It outranks `budget_exhausted`;
  `target_unavailable` outranks it; `diff`'s `_STOP_EXPLANATIONS` names it.
- **Whether a legacy revision is still offered is asked, not read.** When `server/discover`
  listed no legacy revision, the sections that need the legacy era (`sessions`, `tasks`) buy one
  `initialize` over `LEGACY_WIRE`, with the operator's credential when configured, cached for
  the run: a result naming `2025-11-25` → dual-era, `legacy_wire` is `LEGACY_WIRE`; a result
  naming another revision → a legacy revision Guardana does not speak; a JSON-RPC error, `400`,
  `404` or `405` → modern-only; `401` or `403` → unknown. `legacy_wire` is never anything but
  `LEGACY_WIRE`. `session_binding` is silent only on a server observed to be modern-only; a
  legacy revision Guardana does not speak, or an unknown answer, is inconclusive, naming the
  revision or `--mcp-token-env`.
- **`notifications/initialized`** is sent after every accepted `initialize` that a request
  follows in the same session, as the `2025-11-25` lifecycle requires of a client; it is metered.
- **Between runs** nothing new is recorded: `coverage.protocols` holds what the server answered,
  and `diff` reports a change in it as *reach changed*. The conformance suite pins that.

### 4. The address guard judges the IPv4 address an IPv6 address carries

One function, used by `_refused_address`, the cloud-metadata check, `_inside` and
`_named_local`, replaces an IPv6 address by the IPv4 address it embeds before any check:

| form | prefix | IPv4 taken from |
|---|---|---|
| IPv4-mapped | `::ffff:0:0/96` | the last 32 bits (as today) |
| IPv4-compatible (deprecated) | `::/96`, except `::` and `::1` | the last 32 bits |
| NAT64 well-known | `64:ff9b::/96` (RFC 6052) | the last 32 bits |
| 6to4 | `2002::/16` (RFC 3056) | bits 16–47 |

An address in NAT64 local-use `64:ff9b:1::/48` (RFC 8215) or Teredo `2001::/32` (RFC 4380) is
refused under every scope: "`<address>` embeds an IPv4 address guardana cannot judge"; `_inside`
is false for it (unknown is not local). A literal URL, a resolved name and a redirect hop are
judged alike, and the result no longer depends on which Python patch release calls `2002::/16`
private. `64:ff9b::808:808` is accepted as `8.8.8.8`; `64:ff9b::a9fe:a9fe` and
`2002:a9fe:a9fe::` are refused as the metadata address everywhere; `2002:7f00:1::` is loopback.
`is_local_address` does not use it (decision 6).

### 5. Discovery has its own sender; `Sender` loses `discovery` and `alongside`

`Sender` becomes `(url, *, method="POST", body=None, headers=None) -> RawReply`, the server's own
requests; its docstring states the contract: raise `McpError` when no reply arrived, return a
`RawReply` for every status. Discovery documents go through `discovery_sender: DiscoverySender`,
the current full signature with `alongside` and `discovery`, exported from
`guardana.core.target`. `McpServerTarget(url, *, …, sender=None, discovery_sender=None)`: with
neither, both are the built-in pinned `send`; a `sender` supplied without a `discovery_sender`
raises `ValueError` at construction — "a supplied sender needs a discovery_sender too: pass the
same scripted server, or `guardana.core.target.send` for the built-in pinned client" — so a pack
transport can neither skip the pin by ignoring a keyword nor send a test suite's discovery to
the live network. `ScriptedMcpServer` satisfies both and its docstring shows both. A caller
passing its own `discovery_sender` owns the guard; the docstring says it must honour `discovery`.

### 6. `is_local_address` is deprecated

Calling it emits `DeprecationWarning`: "`guardana.core.target.is_local_address` is deprecated and
will be removed before 1.0; `McpAuthorizationView.server_is_local` says whether a server is local
from the addresses a run reached." Behaviour unchanged; tests that call it expect the warning.

### 7. Task identity: `guardana.mcp.task_identity`

Only `tools/call` creates a task in either revision and Guardana calls no tool, so the rule reads
what a caller without a credential is shown. The `2025-11-25` text decides what that can prove:
a server with context binding MUST list only the requestor's tasks, and needs unguessable ids
only "if context-binding is unavailable". So an empty anonymous listing is the conforming answer,
counter ids on a gated server conform, and the ids matter only where there is nothing to bind a
task to.

**The observation** is a new lazy section of `McpAuthorizationView`, `tasks: Tasks`:

- one anonymous `tasks/list`, sent whatever the server declares: over the legacy wire, in the
  anonymous probe's session (`Anonymous.session`, new), when the server is legacy or dual-era;
  over the modern wire otherwise (no extension declared in `clientCapabilities`). One page; the
  cursor is ignored;
- its answer: `answered` (a `2xx` result holding a `tasks` list: the count, the `taskId` values
  kept in memory only), `refused` (`401`, `403`), `unknown_method` (JSON-RPC `-32601`, any
  status) or `other` (the status, quoted under the run's policy);
- `offer`, from the declarations, `listing` over `unlisted` over `none`: `listing` when the
  legacy capabilities hold `tasks.list`; `unlisted` when they hold `tasks` without `list` or the
  modern ones hold `extensions["io.modelcontextprotocol/tasks"]`; `none` otherwise. Legacy
  capabilities come from the anonymous probe's `initialize` when it was answered, else from the
  opening, else from the legacy probe; modern ones from `server/discover`.

Evidence holds counts, never an id.

**The rule** decides before yielding:

1. The server could not be reached or shares no revision → inconclusive (`unreachable()`).
2. `answered` with at least one task → HIGH: "lists `<n>` task(s) to a caller who presented no
   credential" — a fresh anonymous session owns none, so they are somebody else's. On a server
   that served tools anonymously, and at least two ids whose structure `id_structure` names, a
   second HIGH: "task ids are `<structure>`; with no authorization context to bind a task to,
   the id is all that guards it".
3. `answered` with none: on a server that served tools anonymously → inconclusive, "no task is
   visible to a caller without a credential, so whether task ids can be guessed — the only
   guard a server without authentication has — cannot be graded"; on a gated server → silent.
4. `refused` → silent.
5. `unknown_method`: `offer` `none` → `raise NotOffered("the server declares no tasks and answers
   tasks/list as an unknown method", missing=("tasks",))`; `unlisted` → inconclusive, "the
   server issues task ids only to a tools/call, which guardana never sends"; `listing` →
   inconclusive, "the server declares tasks.list and answers it as an unknown method".
6. `other` → inconclusive, quoting the status.

`id_structure(ids, *, ordered: bool) -> str | None` moves out of `session_binding` into
`rules/mcp/_ids.py`: a repeated id, an id shorter than 16 characters, or ids that count up.
`ordered=True` keeps the issue order (sessions); `ordered=False` sorts the numeric tails first
(a listing's order is the server's). Meta: `INSPECT_AUTHORIZATION` (over stdio a
`missing_capability` skip), taxonomy `MCP07:2025`, `MCP10:2025`, `ASI03:2026`, one request,
read-only.

Rejected: grading the operator's own listing (owner-bound ids need not be random, so a finding
there would accuse a conforming server); trusting the declaration alone (a server that declares
nothing and lists everyone's tasks would never be asked).

### 8. The authorization server's `issuer` must be the one it was fetched for

`authorization_discovery` reports, at the severity of its missing-PKCE finding, an
authorization-server metadata document whose `issuer` is absent, not a string ("names no
issuer"; RFC 8414 §2 makes it REQUIRED) or not identical — compared as strings, no normalization
— to the entry its well-known URL was built from (`_named_issuer`, the first entry
`_first_issuer` used). RFC 8414 §3.3 and `2026-07-28` both say a client MUST NOT use such a
document. Existing fixtures gain the matching `issuer`.

### 9. Registry metadata: `guardana.mcp.registry_entry`

Neither revision defines registry metadata a client can observe, and `serverInfo` is
self-reported. What a team can check is whether the server it deployed is the one its registry
entry publishes, so the entry is an input the operator supplies — never fetched (principle 3).

- `probe --mcp TARGET --mcp-registry-entry FILE`, over HTTP or stdio, and the same on `plan
  probe`; `McpServerTarget(…, registry_entry=RegistryEntry)`. `RegistryEntry.load(path)` reads
  the registry's `server.json` (at most 1 MiB): `name` matching `^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$`,
  a non-empty string `version`, optional `remotes` as objects with string `type` and an `http`
  or `https` `url`; other keys are ignored. Anything else raises `RegistryEntryError(ValueError)`,
  which `probe` and `plan probe` refuse as a usage error (exit `3`) before anything is sent. Module `core/target/_mcp_registry.py`;
  `RegistryEntry`, `RegistryEntryError` and `ReportedServer` exported from `guardana.core.target`.
  The manifest records nothing new; the findings carry the entry's name and version.
- `Capability.REGISTRY_ENTRY = "registry_entry"`, declared only when an entry was given, so
  without one the rule is a `missing_capability` skip. Protocol `RegistryEntryInspector`:
  `registry_entry() -> RegistryEntry`, `reported_server() -> ReportedServer | None` (`name`,
  `version` from the opening's `serverInfo` or `server/discover`'s `_meta`; None when absent, and
  a `version` of `""` counts as absent) and `server_url() -> str | None` (None over stdio). Both
  new capabilities enter `CAPABILITY_SURFACE` (`target/protocols.py`).
- The rule, URL half (HTTP only): the server URL matches no `remotes[].url` → MEDIUM, "the server
  at `<display_url>` is not a remote its registry entry `<name>` publishes" (an entry without
  remotes publishes none). URLs compare with scheme and host lowercased, the default port
  dropped, one trailing `/` of the path dropped, the query verbatim and the fragment ignored; a
  `{variable}` in a published URL matches one or more characters other than `/`. Version half:
  a reported version that differs → LOW, worded as self-reported; none reported → inconclusive,
  "the server reports no version to compare with `<version>`". Taxonomy `MCP09:2025`,
  `MCP04:2025`, `ASI04:2026`; no request beyond the opening.

### 10. An A2A v1 target

`A2aAgentTarget(url, *, credential=None, other_credential=None, sender=None)` in
`core/target/a2a.py` (observations in `_a2a_view.py`, the JSON-RPC binding in `_a2a_wire.py`).
Kind `ENDPOINT`; capability `Capability.INSPECT_A2A = "inspect_a2a"` with protocol
`A2aInspector.a2a() -> A2aView`; `apply_budgets` meters every request, the card included;
`protocols()` returns `{"a2a": "1.0"}` once a `result` or an A2A-defined error (`-32001` to
`-32009`) came back. `Verifier` runs it as it runs an MCP server: rules only, no probe passes.
Selected by `probe --a2a URL`, `--a2a-token-env NAME` and `--a2a-other-token-env NAME`, and by
`plan probe --a2a`. `--a2a` excludes `--mcp` and the endpoint options as `--mcp` does; the second
variable without the first, or both holding the same value, is a usage error. `ScriptedA2aAgent`
in `guardana.core.testing.a2a` (exported) doubles the agent for unit tests.

**Origin.** Every request goes to the origin the operator named, through `sender`. The card is
`url` itself when its path ends in `.json`, otherwise `<origin>/.well-known/agent-card.json`.
The interface is the first `supportedInterfaces` entry with `protocolBinding` `JSONRPC` and a
`protocolVersion` whose major and minor are `1.0`; none, or one on another origin, sets
`A2aView.unsupported` naming what the card offers ("the card's JSON-RPC 1.0 interface is on
`<origin>`; guardana sends only to the origin it was given — run --a2a against that origin")
and nothing is sent to it. A credential never leaves the operator's origin.

**Security declared by the card**, read from the proto JSON the v1 SDKs write
(`securitySchemes.<name>.httpAuthSecurityScheme | oauth2SecurityScheme |
openIdConnectSecurityScheme | apiKeySecurityScheme | mtlsSecurityScheme`,
`securityRequirements[].schemes`), or from `security`, the prose spelling, when
`securityRequirements` is absent: **required** when the requirements list is non-empty and no
entry is empty; **optional** when an entry is empty; **none** otherwise. A credential is sent, as
`Authorization: Bearer`, only when some entry consists of bearer-capable schemes alone
(`httpAuthSecurityScheme` with scheme `bearer` in any case, `oauth2SecurityScheme`,
`openIdConnectSecurityScheme`); otherwise every credentialed half is inconclusive, naming the
schemes the card requires.

**What it sends**, all idempotent reads, JSON-RPC `POST`s with `Content-Type: application/json`
and `A2A-Version: 1.0`: anonymous `GetTask {"id": <random UUID>}`, `ListTasks {"pageSize": 1}`,
and `GetExtendedAgentCard {}` when `capabilities.extendedAgentCard` is true; the first caller's
`ListTasks {"pageSize": 5}`; the second caller's `GetTask` on up to three of the first caller's
ids. Never `SendMessage`, `CancelTask`, a subscription or a push configuration.

**Reading answers.** HTTP `401` or `403` → `refused`; `-32001` → `not_found`; a `result` →
`answered`; `-32004` → `not_offered`; `-32601` → `not_offered` once an A2A-defined code came back
from this agent, `other` before; `-32009` → `A2aView.unsupported`; anything else → `other`. The
card `GET` and the first caller's requests are the conversation of decision 2 — no reply, `404`,
`408`, `425`, `429`, `5xx`, an unreadable `2xx`, and `401`/`403` to the first caller's credential
stop the run; another `4xx` on the card is `A2aView.card_error`. The anonymous and second-caller
requests are probes: only a missing reply stops. A card field that is absent, an empty string or
an empty list is missing.

**Values learned during the run.** `sent_secrets()` returns both credentials and every task id
the target learned; `Verifier` reads the target's secrets again after the run, before it writes
anything, so an id a server echoed into an error is withheld from `run.json`. `McpServerTarget`
does the same for the session ids it collected.

### 11. Three A2A rules

| rule | fires | inconclusive | not offered | taxonomy |
|---|---|---|---|---|
| `guardana.a2a.agent_card` | a required field missing (`name`, `description`, `supportedInterfaces`, `version`, `capabilities`, `defaultInputModes`, `defaultOutputModes`, `skills`); a requirement naming a scheme `securitySchemes` does not declare; a JSON-RPC 1.0 interface on plain `http` with a non-local card host — MEDIUM, one finding listing each | `card_error` | — | `ASI07:2026`, `ASI04:2026` |
| `guardana.a2a.caller_identity` | security **required** and an anonymous `GetTask`, `ListTasks` or `GetExtendedAgentCard` `answered` → HIGH; security **none** and one `answered` → HIGH, LOW when the card host is local; the extended card `answered` anonymously → HIGH under any security — one finding per shape | `unsupported`; every anonymous request `other`; `GetTask` answered `-32601` before any A2A code | — | `ASI03:2026`, `ASI07:2026` |
| `guardana.a2a.task_visibility` | an anonymous `ListTasks` `answered` with a task or `totalSize` above 0 → HIGH; the second caller `answered` a `GetTask` for the first caller's task → HIGH | `unsupported`; the cross-caller half when a credential is missing or could not be sent (naming the two flags or the card's schemes); the first caller listed no task; the second caller `refused` | every `ListTasks` sent answered `not_offered`, at least one sent | `ASI03:2026`, `ASI07:2026` |

A `not_found` is never graded: the specification asks a server not to tell "does not exist" from
"not yours", and a random id exists for nobody. An optional requirement makes an anonymous
answer what the card declared. Silent otherwise. Agent-card signatures are not verified
(decision 14).

### 12. The fixtures: servers built on the protocol owners' SDKs

A dev-only dependency group, `conformance`, pinned exactly — `mcp==2.3.0`,
`a2a-sdk[http-server]==1.2.1`, `uvicorn` at the workspace's version — and added to `[tool.uv]
default-groups`. Principle 6's justification, also beside the group in `pyproject.toml`: F7
requires servers Guardana did not write; the SDKs are the protocol owners' reference
implementations; nothing under `packages/*/src` may import `mcp` or `a2a` — an import-linter
`forbidden` contract over every `guardana.*` root, with `include_external_packages = true`,
enforces it; the clean-install check and the isolated example suites never install the group.

Servers run in-process on `127.0.0.1`: a socket bound to port `0`, then `uvicorn.Server(config)
.run(sockets=[sock])` in a thread, in `packages/guardana-rules/tests/conformance/`
(`mcp_servers.py`, `a2a_servers.py`, `test_mcp_conformance.py`, `test_a2a_conformance.py`). The
wire, era routing, caching hints, bearer middleware and protected-resource metadata are the
SDK's; the fixture writes only the policy under test, through the SDK's seams:

- MCP era selection: legacy-only replaces `server/discover` with a handler raising
  `METHOD_NOT_FOUND`; modern-only adds a `Server.middleware` that rejects `initialize`; a revision
  restriction or a mid-run change is a middleware raising `-32022` with `data.supported`, in
  JSON-response mode; an `initialize` answered with `2025-06-18` is a middleware editing the
  result. `cacheScope` is `Server(cache_hints={"tools/list": CacheHint(scope="public")})`. A
  `2025-11-25` `tasks/list` is `add_request_handler("tasks/list", …)` plus a `Server` subclass
  advertising `tasks.list` from `get_capabilities`; the modern extension is
  `server.extensions["io.modelcontextprotocol/tasks"] = {}`. Authorization-server metadata is a
  static document on the same origin whose `issuer` equals the protected-resource document's
  `authorization_servers[0]` byte for byte.
- A2A: a Starlette `AuthenticationMiddleware` on the JSON-RPC route only, whose backend maps a
  bearer token to a user and whose `on_error` answers `401`; tasks stored with
  `InMemoryTaskStore.save(task, ServerCallContext(user=…))` under the owner the backend yields; a
  no-op `AgentExecutor`; a handler subclass whose `on_list_tasks` raises
  `UnsupportedOperationError`; a small method-reading gate for the anonymous extended card.

| fixture | expected |
|---|---|
| MCP legacy-only, modern-only, dual-era — each gated by one bearer token, probed with it | exactly the two findings the SDK's defaults earn: `scope_breadth` (its `401` challenge names no scope) and `issuer_identification` (the authorization-server metadata does not advertise `iss`); `task_identity` silent, because the anonymous listing is refused; `coverage.protocols` holds what each answered; the dual-era server's sessions are graded |
| the same, probed without a credential | `unauthenticated_access` silent; `session_binding` inconclusive naming `--mcp-token-env`; `token_audience` silent, because the forged token is refused and that needs no operator credential to observe; `task_identity` no finding; exit `2` |
| open (no auth) | `unauthenticated_access` LOW (loopback); `token_audience` inconclusive |
| accepting any token | `token_audience` fires |
| modern and dual-era, gated, `cacheScope: public` on `tools/list` | `cache_scope` fires; the legacy one is silent |
| legacy `tasks.list`, owner-bound, gated | silent |
| legacy `tasks.list` listing to anonymous callers, with counting ids, open | two HIGH |
| open legacy `tasks.list`, no task stored | inconclusive |
| modern with the tasks extension | inconclusive (`unlisted`) |
| metadata `issuer` differing from its URL, and absent | `authorization_discovery` fires |
| registry entries listing / not listing the URL, matching / other / no version | decision 9 |
| a registry entry that cannot be read or is not an entry | usage error, exit `3`, nothing sent |
| a server that stops answering after N requests | exit `4`, `run.json` kept, `stopped_by: target_unavailable` |
| a server whose revisions change after discovery | `stopped_by: target_changed` with decision 3's message |
| legacy answering `initialize` with `2025-06-18` | no `agreed`; authorization rules inconclusive |
| legacy-only then dual-era; modern then legacy-only | `diff` reports reach changed |
| A2A v1, bearer required, tasks keyed by owner, one task stored for caller A, both credentials | no finding; `coverage.protocols` `a2a: 1.0` |
| … security declared, nothing enforced | `caller_identity` HIGH |
| … no security declared | `caller_identity` LOW (loopback) |
| … a constant owner | `task_visibility` HIGH through the second caller |
| … extended card served anonymously | `caller_identity` HIGH |
| … no `ListTasks` | `task_visibility` `not_offered` |
| … a card missing a required field, a requirement naming an undeclared scheme | `agent_card` |
| … a JSON-RPC interface on another origin | every call rule inconclusive; nothing sent there |

Unit tests use `ScriptedMcpServer` and `ScriptedA2aAgent` and refuse real name lookups. Each new
rule ships finding, clean and inconclusive fixtures, so `_FULLY_SAMPLED` in
`test_builtin_fixture_coverage.py` rises by five; `test_probe_cost.py` gains an A2A run shape (ceiling 20, a whole
run 8 requests) and `REGISTRY_ENTRY` in the MCP shape. The MCP ceiling rises from 60 to 79:
`notifications/initialized` and the legacy probe are metered, and `task_identity` and
`registry_entry` declare their own; a whole MCP probe still spends at most 20.

Rejected: hand-written fixtures (Guardana's own reading on both sides); the official MCP
conformance suite's TypeScript everything-server (a Node toolchain and an npm fetch in CI and on
every contributor's machine).

### 13. Persisted documents

- **Run schema 17** (`schemas/run-v17.schema.json`): `result_summary.rules_skipped[].reason`
  gains `not_offered`; `result_summary.stopped_by` gains `target_changed`; the
  `coverage.protocols` description names `a2a`. `migrate_v16` (`manifest/migrations.py`) only
  moves the version: no schema-16 document holds a new value. Registered in `report/load.py`,
  history in `manifest/model.py`, pinned by `test_run_schema_v17.py`, covered by the round-trip
  registry.
- Plan schema 4 lists skipped rule ids without reasons and is unchanged. The collector envelope
  carries skip reasons as strings and no stop reason, and is unchanged.

### 14. What is deliberately not built

| left out | reason |
|---|---|
| Agent-card signature verification | JWS over RFC 8785 needs a JOSE or crypto dependency in the engine (principle 6); the card is graded on what it declares, and the docs say signatures are not checked |
| A2A HTTP+JSON and gRPC bindings, and interfaces on another origin | one fixture, one binding; credentials stay on the origin the operator named |
| Creating an A2A or MCP task to watch its id | a `SendMessage` or `tools/call` is a side effect on somebody's system |
| Grading the operator's own task ids | owner-bound ids need not be random (decision 7) |
| Fetching registry entries from the registry API | a destination the run does not otherwise name |
| Server Cards (`.well-known/mcp.json`) | an open proposal, in neither revision |
| `cacheScope` on prompt and resource lists | Guardana does not send those requests |
| Older handshake revisions (`2025-06-18`, `2025-03-26`) | new protocol coverage; decision 3 reports them as no revision in common |

## Exit codes after this change

| situation | before | after |
|---|---|---|
| `probe --mcp` against a server that does not answer | `2` | `4`, run saved |
| an MCP server failing part-way, or its conversation answered `429`/`5xx` | `2` | `4`, partial run saved |
| an MCP server dropping the agreed revision mid-run | `2` | `4`, `stopped_by: target_changed` |
| a legacy server answering `initialize` with an older revision | `0`/`1` | `2` (inconclusive and errors) |
| a rule the server does not offer, under `--preset release` | — | `2` |

## Breaking changes

The rows above; `Sender` drops `alongside` and `discovery`, and a `sender` given without a
`discovery_sender` raises; `is_local_address` warns; run schema 17 is refused by 0.38;
`session_binding` is inconclusive on a failed sampling and on a server whose legacy offer could
not be settled; the dual-era session check now covers a server whose `server/discover` lists
only modern revisions; one more `initialize` is sent to a modern server when a section needs the
legacy era; `notifications/initialized` is sent; NAT64 global addresses are accepted and 6to4
forms of inside addresses refused beside a local server; `authorization_discovery` fires on an
absent or mismatched `issuer`.

## Related

- [`mcp-protocol-eras.md`](mcp-protocol-eras.md), [`mcp-authorization-depth.md`](mcp-authorization-depth.md)
- [`guarded-applications.md`](guarded-applications.md) — decision 4, which decision 2 extends
- [`capability-protocols.md`](capability-protocols.md) — why a capability is a protocol
- [`../usage-probe.md`](../usage-probe.md)
