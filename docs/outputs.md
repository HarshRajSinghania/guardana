---
title: "Installed outputs"
nav_order: 245
summary: "an installed format for --format and an installed reporter for --reporter: choosing one, plugin trust, the delivery line, exit 8, exporting a saved run from Python, and writing your own"
status: beta
---

# Installed outputs: formats and reporters a package adds

A package can add a format, selected with `--format`, and a reporter, selected with
`--reporter`. Guardana needs no change and no new flag for either. An installed output is
imported only when a command names it, and it receives what the saved run holds, never more.

`examples/output_pack` is a complete package with one of each: `acme-table`, a CSV export of
every outcome, and `acme-webhook`, a signed webhook.

## Choose one

```bash
pip install ./examples/output_pack
guardana scan models/ --format acme-table --output run.csv \
  --plugins allowlist --allow-plugin acme-guardana-outputs
guardana probe --url https://api.example.com --model m \
  --format json --output run.json \
  --reporter acme-webhook://env:ACME_WEBHOOK_URL \
  --plugins allowlist --allow-plugin acme-guardana-outputs
```

| Flag | Built in | Installed |
|---|---|---|
| `--format` on `scan`, `probe`, `grade`, `analyze-trace` | `human`, `json`, `sarif`, `junit` | any installed format name |
| `--reporter` on `scan`, `probe`, `analyze-trace` | `server://URL` or an `http(s)://` collector URL | `<name>://<locator>`; the reporter reads the locator |

`monitor` and `import-observations` take only the built-in forms, and refuse an installed one
with exit `3`. So do `scan --write-baseline` and `probe --write-mcp-pin`, which produce no
report for an output to receive.

Every command starts with Guardana's own distributions only, so an installed output is
refused until you admit its distribution: `--plugins allowlist --allow-plugin <distribution>`
or `plugins:` in a profile ([plugin trust](profiles.md#plugin-trust-plugins)). The output is
then selected before the run sends anything. An unknown name, a name two installed
distributions claim, a refused distribution or an output that fails to load exits `3` with the
reason, and nothing is sent. `guardana doctor` lists each installed output, imports none of
them, and says whether it would be refused.

## What an output receives

| | Format | Reporter |
|---|---|---|
| findings, unverified, errors, skips, shortfalls, cases | redacted under the profile, then again as the built-in formats are | the same |
| the run description and verdict | as saved | as saved, with the target's address redacted |
| kept exchanges | redacted again | never |

No option hands an output an unredacted result. The verdict comes from the saved run: an
output cannot decide that a run with open questions is clean.

## Delivery status

A reporter prints one line to stderr on every path, success included:

```
delivery: <status> — <name> to <destination>[ (HTTP <code>, <n> attempt|attempts)][: <detail>]
```

| Status | Meaning | Exit code |
|---|---|---|
| `delivered` | the receiver acknowledged it | the verdict's |
| `rejected` | the receiver answered and did not accept it | the verdict's |
| `unreachable` | the receiver did not answer | the verdict's |
| `not_sent` | nothing left the machine: the run ended before its report existed, or the reporter declined to send | the verdict's |
| `unknown` | the reporter failed, or ran past 30 seconds; whether anything left is unknown | `8` |

The destination is shown without a path, query or credential. The line's prefix and status
words are stable; a script may read them.

## Exit code 8

Exit `8` means an installed output failed: a format raised or returned no text, so nothing was
written, or a reporter's delivery is `unknown`. The verdict is printed first, as `the run's
verdict: <gate> (exit <code>)`, and the error names the distribution to report it to. A run
its target or budget stopped keeps exit `4` or `6`. See [exit codes](exit-codes.md).

## Export a saved run from Python

A paid probe saved with `--format json --output run.json` can be exported later, with no
request to anything:

```python
from pathlib import Path

from guardana.core.output import render, select_renderer
from guardana.core.plugins import PluginMode, PluginTrust
from guardana.core.verify import load_verification

trust = PluginTrust(mode=PluginMode.ALLOWLIST, allowed=frozenset({"acme-guardana-outputs"}))
table = render(select_renderer("acme-table", trust), load_verification(Path("run.json")))
Path("run.csv").write_text(table, encoding="utf-8", newline="")
```

`guardana recipe run` saves `run.json` in its artifact directory; export it the same way.

## The reference webhook

`acme-webhook` follows [Standard Webhooks](https://github.com/standard-webhooks/standard-webhooks):
a JSON body `{"type": "run.completed", "timestamp": …, "data": {…}}`, signed with
HMAC-SHA256 under `webhook-id`, `webhook-timestamp` and `webhook-signature`. A receiver verifies
it with any Standard Webhooks library and the secret in `ACME_WEBHOOK_SECRET` (`whsec_…`).

- **Destination.** `acme-webhook://https://host/path`, or `acme-webhook://env:VARIABLE` to keep
  a URL that carries a token out of shell history and CI logs. Plain `http` is accepted only for
  `localhost`, `127.0.0.1` and `::1`. You name the address, as you name a probe target; nothing
  else is contacted.
- **Content.** The run id, verdict, exit code, open questions, counts per outcome, the target,
  declared deployment fields, and up to 50 findings as rule id, severity and title. No evidence,
  prompt or reply is sent. That is still an inventory of what is wrong with a named deployment:
  send it only to a receiver you would show the report to.
- **Delivery.** At most three attempts within 25 seconds, retrying on no answer, `408`, `429`
  and `5xx`; redirects are not followed. `webhook-id` is the same on every attempt, so a
  receiver can drop a repeat.

## Write your own

An output is one entry point; its name is the output's name.

```toml
[project.entry-points."guardana.renderers"]
acme-table = "acme_outputs:provide_table"

[project.entry-points."guardana.reporters"]
acme-webhook = "acme_outputs:provide_webhook"
```

Name the package module, not a submodule, so `guardana pack validate` finds your manifest, and
import heavy code inside the provider so selecting one output never imports another. A name is
lowercase letters, digits and `-`, at most 40 characters; `human`, `json`, `sarif`, `junit`,
`server`, `http`, `https` and any name starting with `guardana` are reserved.

```python
from guardana.core.output import Delivery, DeliveryStatus, RendererSpec, ReporterSpec

def provide_table() -> RendererSpec:
    return RendererSpec(name="acme-table", summary="CSV of every outcome", render=to_csv)

def provide_webhook() -> ReporterSpec:
    return ReporterSpec(name="acme-webhook", summary="signed webhook", prepare=prepare)
```

- `render(verification)` returns the text. Read `verification.gate`, `exit_code` and
  `open_questions` for whether the run is clean; never decide it yourself.
- `prepare(ReporterRequest(locator))` checks the destination and credentials and sends
  nothing; raise `ValueError` with the reason to refuse. It returns an object with
  `destination` (shown in the delivery line), `sent_secrets()` (withheld from every line) and
  `deliver(verification) -> Delivery`.

Declare both in `guardana-pack.yaml` (schema 3) with the output API you were written against:

```yaml
schema_version: 3
name: acme-outputs
extension_api: ">=2,<3"
output_api: ">=1,<2"
provides:
  renderers: [acme-table]
  reporters: [acme-webhook]
```

`guardana pack validate` checks that each declared output is delivered by your distribution and
by no other, and `guardana pack lock` pins it ([`usage-pack.md`](usage-pack.md)). A lock that
pins an output is schema 3, which Guardana 0.39 refuses.
