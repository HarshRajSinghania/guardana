---
title: "One redacted export and one webhook"
nav_order: 92
summary: "an installed package adds a format to --format and a reporter to --reporter, each imported only when selected, both handed what the saved run holds; a webhook says whether it was delivered, a failed output has its own exit code, and offline use sends nothing"
status: proposed
---

# One redacted export and one webhook

**Status:** proposed · **Written:** 2026-10-04 · **Serves:** ROADMAP v0.40 (F4), BACKLOG B06 ·
**Narrows:** [`output-plugins.md`](output-plugins.md), which this supersedes

## The question

`--format` is a closed enum of four renderers and `--reporter` knows one destination, the
collector, so a team that needs another output edits the CLI. F4 asks for one redacted local
export and one webhook that reports its delivery status, supplied by an independently installed
package and selected without a new flag or command. Both go through the common redaction
boundary, collision checks, plugin trust and pack locks. Offline use sends nothing. The general
renderer and reporter contract (diff renderers, binary formats, streaming, several reporters in
one run) waits for a team that needs it.

## What exists, so this does not rebuild it

- `--format` (`cli/_formats.py`, `OutputFormat`) is accepted by `scan`, `probe`, `grade`,
  `analyze-trace` and `import-observations` and resolved by `guardana.report.get_renderer`
  (`report/__init__.py`), which wraps each built-in in `_Redacting` with a default
  `EvidenceRedactor()`. `plan`, `config explain` and `target inspect` use the same enum and only
  ask whether it is `json`; `diff`, `rules`, `taxonomy` and `trace inspect` have their own.
  `recipe run` takes neither flag and always writes human, JUnit and `run.json`.
- `--reporter` is taken by `scan`, `probe`, `analyze-trace`, `import-observations` and
  `monitor`; `grade` has none. `check_reporter_url` is the first statement of each command.
  `submit_safely` runs after `emit`, whatever the gate: it warns on an outage or a rejection and
  propagates anything else, such as a bad URL or a serialization defect (`cli/_reporting.py`).
  `HttpReporter` redacts the result again and redacts the source at `redacted` even under
  `metadata_only` (`core/reporter.py`).
- `Verification` (`core/verify.py`) is the F3 result boundary: `result` redacted under the
  profile's privacy policy with the run's secrets withheld and the baseline applied, `manifest`,
  `gate`, `exit_code`, `open_questions`, `document()`. `stop_messages` and `judge_stops` are CLI
  wording, never saved; `stop_messages` are taken before redaction. `exchanges` are the kept
  prompts and replies, redacted span by span. `scan`, `probe` and `grade` produce one;
  `analyze-trace` and `import-observations` hold the same three values (`result`, `run`,
  `outcome`). `load_report` (`core/report/load.py`) reads a saved run of any schema into a
  `RunReport(manifest, result)`; `ResultSummary.gate` is the recorded verdict, `None` in a
  migrated schema-1 run.
- Trust: `PluginTrust.allows(distribution)` (`core/plugins.py`). `installed_entry_points()`
  (`core/entrypoints.py`) lists the four groups from metadata and imports nothing; it is the
  one enumeration every trust decision walks. `Registry.discover` imports every admitted entry
  point and records each refusal as a load error. `guardana doctor` lists each third-party entry
  point, its state taken from the registry (`_classify`), and warns of the gate consequence of a
  refusal (`_consequence`).
- Packs: `guardana-pack.yaml` schema 2 (`provides.rules|evaluators|targets|taxonomies`,
  `core/pack/load.py`; `_migrate_v1_to_v2` refuses a v1 manifest naming `taxonomies`).
  `discover_packs` reads a manifest from the module an admitted entry point names, through
  `importlib.resources.files`, which finds a package's manifest on Python 3.11 only when the
  module is the package itself. `check_pack` checks every declared id and its owner.
  `pack validate` and `pack lock` refuse when trust refused or failed anything
  (`_discover_completely`, `cli/pack.py`; SECURITY.md). `guardana-lock.yaml` schema 2 pins rules
  by digest, evaluators and targets by id, catalogues by digest, and lists ids no manifest
  declares as `unlocked`; an older `_pack` ignores keys it does not know, and a lock taken under
  another `extension_api` is refused as incomparable (`core/pack/lock.py`). `schemas/` holds no
  pack or lock schema. The recipe lock does not reference the pack lock (`team-recipes.md`).
- `new-pack` writes `schema_version: PACK_SCHEMA_VERSION` (`cli/new_pack.py`).
- Isolated example suites install a package with `uv run --isolated --no-cache` and run its own
  tests (`scripts/ci_local.sh`, `.github/workflows/ci.yml`); `examples/custom_rule` registers the
  four groups.

## Evidence from outside

- Standard Webhooks 1.0.0 is a vendor-neutral sending convention: headers `webhook-id`,
  `webhook-timestamp` (Unix seconds) and `webhook-signature`, an HMAC-SHA256 over
  `msg_id.timestamp.payload` written as `v1,<base64>`, a symmetric secret written `whsec_<base64>`,
  a body of `type`, `timestamp` and `data`. "2xx status code (status codes 200-299)" is a
  successful delivery; "410 Gone" means the receiver wants no more. It recommends payloads
  "smaller than 20kb", thin payloads, and `webhook-id` as the receiver's idempotency key, the same
  on every retry of one event.
  ([spec](https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md),
  read 2026-10-04)
- OpenAI ("following the Standard Webhooks specification"; 3xx "treated as failures") and the
  Gemini API ("strictly follows the Standard Webhooks specification for security headers")
  deliver with it, so receivers already verify it.
  ([OpenAI](https://developers.openai.com/api/docs/guides/webhooks),
  [Gemini](https://ai.google.dev/gemini-api/docs/webhooks), read 2026-10-04)
- `standardwebhooks` 1.1.0 (MIT) is the specification's reference verifier for Python; its PyPI
  metadata declares no dependency. ([PyPI](https://pypi.org/project/standardwebhooks/), read
  2026-10-04)
- The CloudEvents HTTP binding "does not introduce any new security features for HTTP", so it
  would leave signing to be invented.
  ([binding](https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/http-protocol-binding.md),
  read 2026-10-04)
- A cell an attacker controls can become a spreadsheet formula. OWASP: for Excel, "prefix any cell
  starting with `=`, `+`, `-`, or `@`" so it reads as text.
  ([CSV injection](https://community.owasp.org/attacks/CSV_Injection), read 2026-10-04)

## Decisions

### 1. Two entry-point groups, imported only when selected, with their own API version

`guardana.renderers` and `guardana.reporters` (constants `RENDERER_GROUP`, `REPORTER_GROUP`,
tuple `OUTPUT_GROUPS` in `core/entrypoints.py`). This is a deliberate change to a protected
contract: the four groups become six, and CLAUDE.md, the `entrypoints.py` docstring and
`.claude/rules/examples.md` say so.

They are **not** added to `GROUPS`: `Registry.discover` never walks them, so an installed output
is never imported, and never recorded as a refused or failed load, by a run that does not select
it. `installed_entry_points(groups=GROUPS)` gains the parameter and stays the only enumeration;
selection, `doctor` and the pack commands pass the groups they need. Trust is decided per
distribution, so admitting an output distribution admits any rules it also ships; `doctor` lists
every entry point of a distribution together.

One entry point is one output, and **its entry-point name is the output's name**. A provider
returns a `RendererSpec` or a `ReporterSpec` whose `name` equals that entry-point name. Because
the name is in the metadata, a collision and a trust refusal are decided before anything is
imported.

A name matches `[a-z][a-z0-9-]*`, at most 40 characters. Reserved: renderer names `human`,
`json`, `sarif`, `junit`; reporter names `server`, `http`, `https`; any name starting with
`guardana`. The built-ins are not registered through the groups: `--plugins disabled` loads no
entry point and must still print and still forward to a collector. `RESERVED_RENDERER_NAMES`
and `RESERVED_REPORTER_NAMES` live in `core/output.py`; a test in
`packages/guardana-report/tests/` asserts `guardana.report.RENDERER_NAMES` is a subset. An
installed entry point with a reserved or invalid name can never be selected: `doctor` warns, and
`pack validate` refuses a manifest declaring one.

`OUTPUT_API_VERSION = 1` (`core/output.py`), with `SUPPORTED_OUTPUT_API_VERSIONS = {1}`, versions
`RendererSpec`, `ReporterSpec`, `ReporterRequest`, `Deliverer` and `Delivery`.
`EXTENSION_API_VERSION` stays `2`: the rule, evaluator and target contracts do not move, and a
lock compares only `extension_api`, so bumping it would make every lock incomparable for no
change in what it pins. The output contract is part of the extension surface the 1.0
compatibility matrix lists; it grows by adding to version 1 or by a version 2 a pack opts into.

### 2. Selection: decided before the run, refused with exit 3

New module `guardana.core.output`. `OutputSelectionKind(StrEnum)`: `unknown`, `reserved`,
`collision`, `refused`, `broken`, `unsupported`. `OutputSelectionError(Exception)` carries
`kind`, `name`, `message` and `distributions: tuple[str, ...]`.

```python
select_renderer(name: str, trust: PluginTrust) -> SelectedRenderer      # (name, spec, origin)
select_reporter(name: str, locator: str, trust: PluginTrust) -> PreparedReporter
                                                    # (name, spec, deliverer, origin)
```

`origin` is `guardana.core.origin.Origin(distribution, version)`. Steps, in order:

1. `name` reserved → `reserved`. `name` not matching the pattern → `unknown`.
2. The group's entry points named `name`, through `installed_entry_points(groups=(group,))`. None
   → `unknown`.
3. Entry points named `name` that differ in distribution (PEP 503 form; an unnamed one is
   distinct), in `value`, or in version → `collision`, naming each; none is imported. So an
   editable and a wheel install of one distribution side by side collide too, and the output
   that runs never depends on install order or `sys.path`.
4. `trust.allows(distribution)` false → `refused`, with `distributions` set.
5. Import the entry point and call its provider. Any exception except `KeyboardInterrupt`
   (`SystemExit` included), a value that is not the expected spec, or `spec.name != name` →
   `broken`.
6. Reporters only: `spec.prepare(ReporterRequest(locator=locator))`. Any exception except
   `KeyboardInterrupt`, or a value without a callable `deliver`, a `str` `destination` and a
   callable `sent_secrets`, → `broken`. `prepare` validates and sends nothing.

Messages, which tests pin (`<dist>` is `distribution version`, or `an unnamed distribution`):

```
the format acme-tabel is not installed; built-in: human, json, sarif, junit; installed: acme-table (admitted)
the reporter acme-hook is not installed; built-in: server://URL or an http(s) collector URL; installed: acme-webhook (refused)
acme-table is a built-in format name, so no installed format can use it
the format acme-table is installed by 2 distributions (acme-a 1.0, acme-b 2.0), so neither is used
the format acme-table comes from acme-guardana-outputs 0.1.0, which plugin trust builtins does not admit
the format acme-table from acme-guardana-outputs 0.1.0 could not be loaded: ValueError: <reason>
```

After a `refused` message the CLI appends the admission forms (`cli/_plugins.py`), as
`hint_refused_plugins` words them. Every reason taken from plugin code passes the sanitiser of
decision 5.

**CLI.** `--format` on `scan`, `probe`, `grade` and `analyze-trace` becomes a `str` option with
the default `human` and help `human|json|sarif|junit, or an installed format`.
`cli/_formats.py: resolve_format(value, trust) -> OutputFormat | SelectedRenderer` turns a
built-in name into `OutputFormat` and selects anything else; every helper typed `OutputFormat`
today (`_keeping`, `_finish_probe`, `refuse_incomparable_output`) takes the union, and
`--keep-exchanges` stays refused unless the format is `json`. `import-observations --format`
stays the enum: the command loads no plugins.

`cli/_reporting.py: split_reporter(value) -> tuple[str, str] | None` returns `(name, rest)` for
`<name>://<rest>` when `<name>` matches the name pattern and is not `server`, `http` or `https`.
It runs first; `check_reporter_url` runs only when it returns `None`, so every collector value,
including a bare `host:port`, keeps today's path and message. The `unknown` reporter message
names the collector forms, so `htps://collector` still points at them.

Both selections run on the line after `resolve_trust`, before `Registry.discover`, before any
target or meter is built and before any request is sent.

Refused with exit `3` before anything is sent, without reading metadata, kind `unsupported`:

- `monitor --reporter <name>://`: "monitor runs cycles, not a saved run; an installed reporter
  runs with scan, probe or analyze-trace".
- `import-observations --reporter <name>://`: "import-observations loads no plugins; it forwards
  to the collector only".
- `scan --write-baseline` or `probe --write-mcp-pin` with an installed format or reporter: "an
  installed output needs the run's report, which --write-baseline (or --write-mcp-pin) does not
  produce".

Every `OutputSelectionError` prints `error: <message>` and exits `3`.

### 3. The input is a `Verification` holding what the saved run holds

Both kinds receive a `Verification`, the F3 boundary. It already says what makes a run not
clean: `gate`, `exit_code` and `open_questions` come from `core.gate`, and an output adds no
condition of its own (`.claude/rules/cli-report.md`). `scan`, `probe` and `grade` pass the one the
verifier returned; `analyze-trace` builds `Verification(result=result, manifest=run,
gate=outcome)`.

**The boundary** is `outbound(verification, *, leaves_machine: bool) -> Verification` in
`core/output.py`, returning `dataclasses.replace(verification, ...)` with:

| Field | Renderer | Reporter |
|---|---|---|
| `result` | `EvidenceRedactor().redact_result(result)`: the second pass `_Redacting` and `HttpReporter` give the built-ins | the same |
| `manifest` | as saved | as saved, `target.ref` redacted by the `redacted`-mode redactor `HttpReporter` uses for its source |
| `stop_messages`, `judge_stops` | `()`: never saved; the CLI prints them itself | `()` |
| `exchanges` | as kept: written beside the saved run already | `None`: the collector never receives them either |
| `judge_usage` | as recorded | as recorded |

So no output sees more than the saved run holds, and nothing that leaves the machine holds more
than the collector would receive. No argument asks for an unredacted result. If `outbound`
raises, the output is not called (decisions 4 and 5).

A test plants one fake credential in every channel of `result`, in `manifest.target.ref`, in a
stop message and in a kept exchange, then runs every built-in renderer, the collector reporter, a
recording discovered renderer and a recording discovered reporter, and asserts none sees it.

`guardana.core.verify.load_verification(path) -> Verification` reads a saved run of any schema
through `load_report`, sets `gate` from `manifest.result_summary.gate`, and leaves `exchanges`
`None`. A run that records no gate raises `ReportLoadError("<path> records no gate, so its
verdict cannot be read")`; a migrated schema-1 run is one. This is how a run is exported after the
fact, and the documented way to get both a comparable run and an export from one paid probe:

```python
trust = PluginTrust(mode=PluginMode.ALLOWLIST, allowed=frozenset({"acme-guardana-outputs"}))
table = render(select_renderer("acme-table", trust), load_verification(Path("run.json")))
```

`recipe run` takes no output flag; its `run.json` is exported the same way.

### 4. A renderer returns text; a failed one has its own exit code

```python
@dataclass(frozen=True, slots=True)
class RendererSpec:
    name: str
    summary: str                                  # one line, shown by pack validate
    render: Callable[[Verification], str]
```

`render(selected, verification) -> str` (`core/output.py`) applies `outbound` and calls the spec.
`OutputError(Exception)` (`core/output.py`, attributes `name`, `origin`, cause chained) is raised
for any exception except `KeyboardInterrupt` (`SystemExit` included), for a result that is not a
`str`, and for an empty string: every format writes at least a header, so an empty file would
read as a successful export of nothing. A failure of `outbound` is an `OutputError` with reason
`redaction failed: <type>`.

The command writes the text through `emit(rendered, output, name, verbatim=True)`: written with
`newline=""` and printed without an added newline, so CSV line endings survive. `--output`
behaves as today, including the warning that `diff` cannot read the file;
`refuse_incomparable_output` still refuses only `human`.

**Exit `8`, new:** "an installed output failed". It is a new code because the outcome is new and
its cause is not Guardana: exit `5` sends a bug report to Guardana, and this one belongs to the
distribution that shipped the output. On an `OutputError` the command prints, in order: the
verdict line `the run's verdict: <gate> (exit <code>)`, then `error: the format <name> from
<dist> failed: <reason> — nothing was written; report it to <distribution>`, then the delivery
line of decision 5 if a reporter was selected, and exits `8`. Exit `8` replaces `0`, `1` and `2`;
a run that stopped keeps `4`, `6` or `7`, because a stop outranks the verdict and the output
alike. `ExitCode.OUTPUT_FAILED = 8` joins `cli/exit_codes.py`, `docs/exit-codes.md` and its test.

### 5. A reporter returns its delivery status

```python
@dataclass(frozen=True, slots=True)
class ReporterSpec:
    name: str
    summary: str
    prepare: Callable[[ReporterRequest], "Deliverer"]

@dataclass(frozen=True, slots=True)
class ReporterRequest:
    locator: str                                  # what followed <name>:// on the command line

class Deliverer(Protocol):
    destination: str                              # display form, fixed by prepare
    def sent_secrets(self) -> tuple[str, ...]: ...  # withheld from every line printed
    def deliver(self, verification: Verification) -> "Delivery": ...

class DeliveryStatus(StrEnum):
    DELIVERED = "delivered"        # the receiver acknowledged it
    REJECTED = "rejected"          # the receiver answered and did not accept it
    UNREACHABLE = "unreachable"    # no answer from the receiver
    NOT_SENT = "not_sent"          # decided before sending; nothing left the machine
    UNKNOWN = "unknown"            # the reporter failed; whether anything left is unknown

@dataclass(frozen=True, slots=True)
class Delivery:
    status: DeliveryStatus
    detail: str = ""
    attempts: int = 0
    http_status: int | None = None
```

`deliver(prepared, verification) -> Delivery` (`core/output.py`):

1. Applies `outbound(..., leaves_machine=True)`. A failure returns `NOT_SENT`, detail
   `redaction failed: <type>`.
2. Calls `deliverer.deliver` in a daemon thread and waits at most `DELIVERY_DEADLINE_SECONDS =
   30`. Past it: `UNKNOWN`, detail `did not finish within 30 s`. A `KeyboardInterrupt` in the
   waiting thread propagates, so an interrupted run still exits `7`.
3. Any exception except `KeyboardInterrupt` (`SystemExit` included): `UNKNOWN`, detail
   `<type>: <message>`. A value that is not a `Delivery`, or one whose `status` is not a
   `DeliveryStatus`, whose `attempts` is not a non-negative `int`, whose `http_status` is
   neither `None` nor an `int`, or whose `detail` is not a `str`: `UNKNOWN`, detail `returned an
   invalid delivery`. `UNKNOWN` is never written as anything else.
4. Sanitises `destination` and `detail`: every `sent_secrets()` value is withheld as written,
   then `EvidenceRedactor().redact_text`, then control characters (C0, DEL, C1) are dropped, then
   `bounded_reason`. A renderer's failure reason and a `broken` reason go through the same
   sanitiser with no secrets.

**The delivery line** is a documented, stable contract (`docs/outputs.md`), printed once to
stderr for every selected reporter on every path that reaches a `Verification`:

```
delivery: <status> — <name> to <destination>[ (HTTP <code>, <n> attempt|attempts)][: <detail>]
```

The parenthesis lists what is set and is omitted when neither is. Examples:

```
delivery: delivered — acme-webhook to https://hooks.example.com (HTTP 204, 1 attempt)
delivery: rejected — acme-webhook to https://hooks.example.com (HTTP 410, 1 attempt): the receiver no longer accepts deliveries
delivery: unreachable — acme-webhook to https://hooks.example.com (3 attempts): timed out
delivery: not_sent — acme-webhook to https://hooks.example.com: the run's report was not produced
delivery: unknown — acme-webhook to https://hooks.example.com: did not finish within 30 s
```

**Where and when.** In each command the delivery replaces the place of `submit_safely`: after
`emit`, before `exit_with`, whatever the gate, stopped runs included; in `_finish_probe` it sits
where `submit_safely` sits, before `report_target_stop`. From the moment `prepare` succeeds, a
command that ends before delivery prints `not_sent` with the reason: the format failed, the
report could not be written, the target or judge was unavailable, the run was interrupted, or
the budget was refused before sending. A `try`/`finally` around the command body after selection
does it.

**Exit code.** `delivered`, `rejected`, `unreachable` and `not_sent` keep the verdict's exit
code: the receiver's state is not the run's, and that is the collector's rule for an outage or a
rejection. `unknown` is a defect in the reporter, as a bad URL or a serialization error is a
defect the collector path lets end the command: it ends with exit `8` under the precedence of
decision 4. A Python caller reads the `Delivery`. The built-in collector keeps its messages and
its envelope; moving it onto the delivery line would change a shipped output nobody asked to
change.

### 6. Trust and `doctor`

Selection uses the `ResolvedTrust` the command already resolved from `--plugins`,
`--allow-plugin` and the profile. Under the unstated default (`builtins`) a third-party output is
`refused`.

`doctor` decides the state of an output entry point from metadata and trust, never from the
registry, which never sees it: `_State` gains `ON_SELECTION` (`imported only when selected`),
`REFUSED_OUTPUT` (`refused if selected under plugin trust <mode>`) and `UNSELECTABLE` (`never
selectable: reserved name` / `invalid name`). An entry point in a collision gets its own `WARN`
check: `the format acme-table is installed by 2 distributions (a, b); selecting it is refused`.
Output states are left out of `_consequence`, whose gate sentence is false for them, and do not
raise a distribution block above `WARN`. The "N loaded, M refused" counts keep counting
`GROUPS` only, and a block lists the output entry points under them.

### 7. Manifest and lock

**Pack schema 3**, written only when a manifest declares an output:

```yaml
schema_version: 3
name: acme-outputs
extension_api: ">=2,<3"
output_api: ">=1,<2"
provides:
  renderers: [acme-table]
  reporters: [acme-webhook]
```

`output_api` is required exactly when `provides` names a renderer or reporter, refused
otherwise, and read like `extension_api` (an `ApiRange`); a range outside
`SUPPORTED_OUTPUT_API_VERSIONS` is a `check_pack` problem in the words `why_not_any` uses. A
schema 2 manifest naming `renderers`, `reporters` or `output_api` is refused, as v1 refuses
`taxonomies`. `load_manifest` refuses an output name that is invalid or reserved. `new-pack`
writes `schema_version: 2` explicitly, so a scaffolded pack still validates on 0.39.

**Discovery for pack commands.** `discover_outputs(trust) -> OutputDiscovery` (`core/output.py`)
imports every admitted, non-colliding output provider:

```python
@dataclass(frozen=True, slots=True)
class OutputDiscovery:
    renderers: Mapping[str, Origin]
    reporters: Mapping[str, Origin]
    refused: tuple[InstalledEntryPoint, ...]
    failed: tuple[tuple[InstalledEntryPoint, str], ...]   # provider raised or spec mismatched
    collisions: Mapping[str, tuple[str, ...]]             # "renderer:<name>" -> distributions
```

Only `pack validate` and `pack lock` call it. They exit `2`, before `discover_packs` reads any
manifest, when it reports anything refused, failed or colliding, with the message
`_discover_completely` uses, so SECURITY.md's promise covers outputs. `discover_packs` walks
`GROUPS + OUTPUT_GROUPS`. An output entry point must name the package module
(`acme_outputs:provide_table`, not `acme_outputs.table:provide`): on Python 3.11
`importlib.resources.files` finds no manifest from a submodule. The unmanifested warning in
`pack validate` names renderers and reporters too.

**`pack validate`.** `Registered` gains `renderers`, `reporters` (name → distribution) and
`output_collisions`. `check_pack` checks them as it checks evaluators: declared and not
delivered, delivered by another distribution, and `declares renderer acme-table, which 2
distributions provide (a, b) — selecting it is refused`.

**Lock schema 3**, written only when a pack pins an output or an output is unlocked; otherwise
`pack lock` writes schema 2 exactly as today, so a lock without outputs still reads on 0.39. Each
pack entry gains `renderers: [...]` and `reporters: [...]` after `targets`, both always present in
a schema 3 lock. `LockedPack` and `Installed` gain both, pinned by name as evaluators are, with
the distribution version as the coarse pin. One spelling everywhere ids are pooled: `provides`,
`Installed.ids()`, `lock_of`'s declared set and `unlocked` use `renderer:<name>` and
`reporter:<name>`. `_undelivered` covers outputs (declared and not provided raises `PackError`),
`_pack_drift` reports `added` and `removed` outputs, `_READABLE_LOCK_SCHEMAS` becomes `{1, 2, 3}`,
and a schema 1 or 2 lock carrying `renderers` or `reporters` is refused. A schema 2 lock with an
output now installed reports it as `added`.

"Pack locks" means drift that `pack lock --check` reports; selection does not read
`guardana-lock.yaml`, as rule discovery does not. A directory or editable install changes its
code under one version; that limit is the one evaluators and targets already have, and the
recipe lock's `sources` digests remain the way to pin such code.

`schemas/` gains `pack-manifest-v3.schema.json` and `pack-lock-v3.schema.json`, validated by a
round-trip test in `packages/guardana-core/tests/`; earlier versions are not backfilled.
Migration tests from schema 2 sit beside the existing pack tests.

### 8. Offline use sends nothing

A run without `--reporter` contacts nothing new. A discovered renderer is trusted code, so this
is proven, not enforced: the reference renderer and the reference reporter's `prepare` are tested
under a socket guard. An installed reporter that is not selected is never imported (decision 1).
A reporter named in `--reporter` is a destination the run names, as the collector is.

### 9. The independently installed package

`examples/output_pack/`, distribution `acme-guardana-outputs`, package `acme_outputs`, Apache-2.0
like the other examples, `dependencies = ["guardana-core"]`, standard library only. It is not
published; it is installed in isolation in CI to prove a third party needs no change to
Guardana.

```toml
[project.entry-points."guardana.renderers"]
acme-table = "acme_outputs:provide_table"
[project.entry-points."guardana.reporters"]
acme-webhook = "acme_outputs:provide_webhook"
```

`acme_outputs/__init__.py` holds only the two providers, each importing its module inside the
function, so selecting the table never imports `acme_outputs.webhook`. `guardana-pack.yaml` is
the schema 3 manifest above.

**`acme-table`**, CSV under RFC 4180: `csv` module, `QUOTE_ALL`, `\r\n`, one header row:
`run_id,gate,outcome,check,case,severity,location,title,status,detail`. `run_id` and `gate`
repeat on every row, so a filtered sheet still shows the verdict. An empty cell is written for
what a row does not have. Severity is `Severity.name`. Rows, in this order, each channel in result
order:

| `outcome` | from | `check` | `case` | `severity` | `location` | `title` | `status` | `detail` |
|---|---|---|---|---|---|---|---|---|
| `run` | the run | | | `result.max_severity()` | `manifest.target.ref` | | `exit <code>` | every open question, `;`-separated, `stopped` written `stopped:<stopped_by>` |
| `finding`, `unverified`, `waived` | each channel | `rule_id` | | its severity | `target_ref` | `title` | | `evidence.summary` |
| `error` | `errors` | `source` | | | | | `stage` | `reason` |
| `skipped` | `rules_skipped` | `rule_id` | | | | | `reason` | `detail`, then `; missing: a, b` when any |
| `shortfall` | `coverage_shortfall` | `name` | | | | | `kind` | `detail` |
| `case` | `assessments` | `rule_id` | `case_id`, `#<trial>` appended when set | | `subject_ref` | | below | below |
| `suite` | `suites` | its key | | | | | `outcome` | `reason` |
| `ran_no_finding` | each of `rules_run` named by no row above | the rule | | | | | | |

A `case` row's `status` is `passed` or `failed` for a measured case with a verdict, `measured`
for a measured case without one, and the `AssessmentStatus` value otherwise. Its `detail` is
`value <v> <unit>, threshold <t>` when a value was measured, then `reason <UnmeasuredReason>`
when set, then the `rationale`, joined with `; `. A cell whose first non-whitespace character is
`=`, `+`, `-`, `@`, `＝`, `＋`, `－` or `＠`, or which starts with a tab or a carriage return, is
prefixed with `'`. Nothing is truncated: the redactor's bound already applies. A test walks the
fields of `ScanResult`, `Assessment` and `SuiteSummary` and fails on one the table neither
exports nor excludes by name (`observations`, `usage`, `protocols`, `trials_per_case`, `scope`).

**`acme-webhook`**, `--reporter acme-webhook://https://hooks.example.com/guardana` or
`--reporter acme-webhook://env:ACME_WEBHOOK_URL`, which reads the destination from that
variable so a URL carrying a token stays out of shell history and CI logs:

- `prepare` refuses, with a reason: an unset variable; a destination that is not `https`, unless
  its host is `localhost`, `127.0.0.1` or `::1`; userinfo; `ACME_WEBHOOK_SECRET` unset or not
  `whsec_` followed by base64. `destination` is `scheme://host[:port]`: no path, query or
  fragment is ever shown. `sent_secrets()` returns the secret and the full URL.
- Body, Standard Webhooks shape, compact JSON, at most 20480 UTF-8 bytes:

  ```json
  {"type": "run.completed", "timestamp": "2026-10-04T12:00:00+00:00",
   "data": {"run_id": "…", "tool_version": "0.40.0", "gate": "indeterminate", "exit_code": 2,
            "stopped_by": null, "open_questions": ["unverified"],
            "counts": {"findings": {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 0, "INFO": 0},
                       "unverified": 2, "waived": 0, "errors": 0, "skipped": 1, "shortfalls": 0,
                       "cases": {"passed": 0, "failed": 0, "measured": 0, "inconclusive": 0,
                                 "error": 0, "skipped": 0},
                       "suites": {"pass": 0, "fail": 0, "inconclusive": 0}},
            "target": {"kind": "endpoint", "ref": "…"}, "deployment": {"environment": "staging"},
            "findings": [{"rule_id": "…", "severity": "HIGH", "title": "…"}],
            "findings_truncated": false}}
  ```

  `timestamp` is `completed_at`, else `started_at`; a run with neither is `not_sent`. Every
  severity and every count key is present, zero included; `deployment` holds declared fields
  only. `findings` lists up to 50, most severe first, then dropped from the end until the body
  fits; `findings_truncated` is always present. It carries no evidence text, no prompt and no
  reply, so `full` evidence never leaves through it. A test walks the counts against the
  channels of `ScanResult`, so a channel added later cannot be dropped silently.
- Headers: `content-type: application/json`; `webhook-id: msg_<digest(type, run_id)>`, the same
  on every attempt, so a receiver drops a repeat and a re-delivery of a saved run reads as the
  replay it is; `webhook-timestamp` and `webhook-signature` computed per attempt, with HMAC-SHA256
  keyed by the base64-decoded part after `whsec_`, over `id.timestamp.body`.
- Sending: `urllib`, redirects not followed (a 3xx is `rejected`), one monotonic deadline of 25 s
  across all attempts, each attempt's timeout the smaller of 10 s and what remains, at most 3
  attempts, at most 64 KiB of a response read. It retries on no answer, `408`, `429` and `5xx`,
  after 1 s and then 2 s, or after a `Retry-After` in seconds; a `Retry-After` that is not a
  number of seconds, or that would pass the deadline, ends the retries. The final attempt
  decides: 2xx `delivered`; another answer `rejected` (`410`: "the receiver no longer accepts
  deliveries"); no answer `unreachable`. A body over the bound after truncation is `not_sent`.
  `sleep` and the clock are injectable for tests. Nothing is sent before `deliver`.

### 10. Tests that prove it

- **Engine** (`packages/guardana-core/tests/`): each selection kind, with entry points faked
  over `importlib.metadata` and nothing installed; a collision imports neither module; a
  provider, `prepare`, `render` and `deliver` that call `sys.exit(0)` are `broken`, `OutputError`
  and `unknown`; `deliver` past its deadline is `unknown`; every invalid `Delivery` shape is
  `unknown`; the planted-credential test of decision 3; `load_verification` over
  `tests/saved_runs/` and each schema's migrated document, a schema-1 run raising; manifest and
  lock schema 3 round trips, the schema 2 refusals, and lock schema 2 still written without
  outputs.
- **CLI** (`packages/guardana-cli/tests/`): exit `3` for each refusal, before any request to a
  scripted endpoint; the `unsupported` refusals; exit `8` with the verdict line printed and no
  file written for a renderer that raises or returns `""`; exit `8` for an `unknown` delivery, and
  a stopped run keeping `4`; a delivery of each other status printing its line and keeping the
  verdict's code; `not_sent` printed on each early exit after `prepare`; `doctor` listing output
  entry points, collisions and reserved names without importing them; `pack validate` and
  `pack lock` exiting `2` on a refused output.
- **The package** (`examples/output_pack/tests/`, isolated, installing core, rules, cli and
  report): `scan` and `grade` select `acme-table` under `--plugins allowlist --allow-plugin
  acme-guardana-outputs` with `socket.socket.connect` patched to raise
  (`examples/output_pack/tests/conftest.py`), and `acme_outputs.webhook` is absent from
  `sys.modules` afterwards. `probe` against a scripted `http.server` endpoint exports a failed
  run, an indeterminate run and a run stopped by `--max-requests 1`, each with its verdict and
  every open question. Formula cells, including `;=`, ` =` and `＝`, are neutralised. A declined
  suite and a stopped run produce no `ran_no_finding` row for their rules. `pack validate` and
  `pack lock` cover both names.
- **Against a receiver Guardana did not write**: a standard-library `ThreadingHTTPServer` whose
  handler verifies every delivery with `standardwebhooks.Webhook(secret).verify(body, headers)`
  (the specification's reference verifier) and answers by script. `204` is delivered; `503` then
  `204` is delivered in 2 attempts with one `webhook-id`; `410` is rejected without a retry; a
  closed port is unreachable after 3 attempts; with a different secret the verifier refuses, the
  handler answers `401`, and the delivery is rejected. The suite adds
  `--with standardwebhooks==1.1.0`, test-only; nothing in the package or in `packages/*/src`
  imports it.
- **Everything else that installs a pack**: the four existing isolated suites,
  `scripts/new_pack_check.py`, and `scripts/clean_install_check.py`, which also runs
  `guardana scan --format no-such-format .` and expects exit `3`.

## Documentation

A new page, `docs/outputs.md`: choosing an installed format or reporter, trust, the delivery line
grammar, exit `8`, exporting a saved run from Python, writing one, and what the webhook payload
reveals (rule ids, severities and titles per deployment, plus declared commit and image
digests). It is linked from `docs/index.md`. Edited: `docs/extending.md` (six groups),
`docs/architecture.md` and `docs/how-it-works.md` (the group counts), `docs/usage-scan.md`,
`docs/usage-probe.md`, `docs/usage-analyze-trace.md` (`--format` and `--reporter`),
`docs/usage-grade.md` (`--format`), `docs/usage-monitor.md` and
`docs/usage-import-observations.md` (their refusals), `docs/usage-pack.md` (schema 3 manifest and
lock, `renderer:`/`reporter:` entries), `docs/usage-doctor.md`, `docs/python-api.md`
(`load_verification`, `guardana.core.output`), `docs/exit-codes.md` (code 8), `docs/privacy.md`
(what each output receives; the collector or an installed reporter receives results only with
`--reporter`), `docs/threat-model.md` (a selected output is trusted code; the operator names the
webhook's destination, as with a probe target; the payload is a vulnerability inventory and
carries no evidence), `SECURITY.md` (trust covers six groups; a refused output is an error only
when selected), CLAUDE.md and `.claude/rules/` (six groups, exit 8, the new isolated suite).
`FEATURES.md`, `CHANGELOG.md` (with an upgrade note: a lock or manifest that pins an output is
refused by 0.39) and `docs/product-status.md` get the change; `ROADMAP.md` moves F4 at release
and its link to `output-plugins.md` points here, as does `docs/design/target-locators.md`.
`site/index.html`: not applicable, no headline claim changes. `examples/output_pack/README.md`
is the walkthrough. The isolated suite joins `scripts/ci_local.sh`, `.github/workflows/ci.yml`
and `docs/maintainers/ops-catalogue.md`.

## Rejected

- **Adding the groups to `GROUPS`.** Every run would import every installed output and record a
  refused one as a load error, so a webhook package nobody selected would change a verdict and
  execute code the run never needed.
- **Choosing the winner of a collision by install order.** The output that ran would depend on
  something nobody reviewed.
- **A new flag (`--export`, `--webhook`) or command (`guardana export run.json`).** F4 is the
  proof that an output needs no CLI change; a saved run is exported from Python.
- **Reusing exit `5` for a failed output**: it sends the report to the wrong project, and a code
  is never given a second meaning.
- **Keeping the verdict's exit code when a reporter raises**: a broken reporter would stay green
  in CI forever. A receiver that refuses or cannot be reached is an outage, as for the collector.
- **A delivery receipt beside the saved run**: a new persisted document nothing needs; the
  stable delivery line, exit `8` and the Python value answer "was it delivered".
- **Handing outputs the unredacted result**, or a flag asking for it. No format needs a secret
  present to say one was found.
- **Bumping `EXTENSION_API_VERSION`** instead of an output API (decision 1).
- **CloudEvents** for the webhook: its HTTP binding defines no signature.
- **Retrying for days**, as Standard Webhooks advises a service: a CLI run ends, so the reference
  bounds itself to 25 s and says what happened.
- **An HTTP framework for the test receiver**: the reference verifier is the independent part; a
  standard-library server adds no dependency.
- **Shipping the export and webhook in `guardana-report`** or as a sixth published package. The
  row asks for an independently installed package, and a published one is a support promise
  nobody has asked for yet. Whether the 1.0 reference pack carries an output is v0.41's question.

## Open questions, with the default this design takes

- Principle 3 lists the collector and no other reporter. The default reads a reporter named in
  `--reporter` as a destination the run names, as the collector already is; naming reporters in
  the principle is the owner's wording to change.
- A team that wants a `rejected` or `unreachable` delivery to fail its job: the default keeps the
  verdict's exit code, as for the collector. A setting for it waits for a team that asks.
