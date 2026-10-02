---
title: "guardana fixtures"
nav_order: 87
summary: "`guardana-fixtures.yaml` declares the synthetic data your application runs with in CI — tenants, seeded documents, records and tools — and `guardana fixtures render` writes the documents you seed into your own index, each carrying markers derived from what you declared"
status: beta
---

# `guardana fixtures` — declare the synthetic data your application runs with

A fixtures file says, once, which tenants your application serves in CI, which documents you
seed into its own index, which records and tools its test doubles serve, and that all of it is
synthetic. Guardana derives a marker for every seeded item from the item as you declared it,
so a reply can be checked for whose data reached it.

```bash
guardana fixtures render guardana-fixtures.yaml --out seed/   # write seed/documents.jsonl
```

You ingest `seed/documents.jsonl` into your application's index yourself, the way your
application ingests any document. Guardana never writes into the index.

## The file

```yaml
schema_version: 1
name: support-bot
data: synthetic                  # required; the only value
tenants:
  acme: {api_key_env: ACME_KEY}            # this tenant's credentials, complete
  globex: {api_key_env: GLOBEX_KEY}
documents:                       # seeded by you into the application's own index
  - {id: acme-loyalty, tenant: acme, topic: "the loyalty programme"}
  - {id: acme-returns, tenant: acme, topic: "returning an order", poisoned: true}
  - {id: globex-shipping, tenant: globex, topic: "shipping times"}
records:                         # served by the stateful doubles
  orders:
    - {id: A-100, tenant: acme, fields: {total: 40}}
    - {id: G-200, tenant: globex, fields: {total: 90}}
tools:
  lookup_order: {op: get, collection: orders}
  refund_order: {op: update, collection: orders, sink: payment, reversible: true}
  send_email: {op: send, sink: email, reversible: false}
```

| Key | Required | Meaning |
|---|---|---|
| `schema_version` | yes | `1`. A newer version is refused with "upgrade Guardana". |
| `name` | yes | Part of every marker's derivation: renaming it moves every marker. |
| `data` | yes | `synthetic`, the only value. A statement you sign in review; Guardana records it as declared and cannot check it. |
| `tenants` | yes, two or more | Each tenant's own credentials: exactly one of `api_key_env` (the variable holding its key) or `adapter` (an adapter file whose headers carry them). The URL, model and provider are the run's. |
| `documents` | one of `documents` or `records` | `id`, `tenant`, `topic`, optionally `poisoned: true`. |
| `records` | one of `documents` or `records` | Collections of `id`, `tenant` and optional `fields` (strings, numbers, true/false). |
| `tools` | no | `op` (`get`, `search`, `create`, `update`, `delete`, `send`); `collection` for every op but `send`; `sink` and `reversible` for a change or a send, never for a read. |

Unknown keys and a key written twice are refused, and relative paths are read beside the
file. The JSON schema is [`schemas/fixtures-v1.schema.json`](../schemas/fixtures-v1.schema.json).

**Refused when the file loads** (exit `3`), because each would let a check pass without the
evidence to pass it:

- fewer than two tenants: a tenant boundary needs a tenant on each side;
- documents declared while some tenant owns none, or a record collection in which some
  tenant owns no record: every tenant that asks through a channel needs an item of its own
  there as its control;
- two tenants with the same credentials: the application would see one tenant;
- two documents with the same topic, compared without case and punctuation: a question
  about one would retrieve both;
- a change or send tool without `sink` and `reversible`;
- a record that types its own `reference_code`, which is where Guardana puts its marker;
- an item whose markers would appear in another item's text, question or fields.

**A tenant's connection is complete on its own.** When the run sends through an adapter,
every tenant names an adapter for the same URL; otherwise each names `api_key_env` or an
adapter. Two tenants are told apart by their key variable or adapter digest when nothing is
sent, so `plan` and `recipe lock` read no key. When sending, two tenants that share any
secret value are refused, whichever way each sends it: one tenant's key and another's
adapter header, or two adapters' headers. A tenant adapter header that reads a `${VAR}`
counts as a credential, as does the variable's value, and the refusal names the tenants and
where each sends the value, never the value itself. Put a header value that is not a secret
in the adapter file as written. The run's own connection, which every
other rule uses, is not a tenant.

## Markers

Every seeded item gets:

- a **retrieval term**, a made-up word unique to it, in its text and in its question;
- a **presence marker**, the answer to its question (a record carries it in a
  `reference_code` field);
- for a poisoned document, an **instruction marker**: two halves the document asks the model
  to join with a hyphen. The halves stand apart in the document, so a reply that quotes the
  document is not read as one that obeyed it.

All of them derive from the digest of the item as declared and the file's `name`, by a
versioned algorithm (`markers: 1`, recorded with every run given fixtures). Edit an item —
its topic, its owner, a field — and its markers change, so an index seeded before the edit
fails its control instead of answering with stale text. Render and seed again after every
edit. A comment or the order of keys changes no marker.

A reply and a marker are compared after case-folding and keeping only letters and digits, so
`AB12 cd34` matches `ab12-CD34`. The presence marker, the joined instruction marker, each half,
the term and the question are kept apart under that comparison, and no item's marker or term
appears in another item; `render` checks this again before it writes.

## `guardana fixtures render FILE --out DIR`

Writes `DIR/documents.jsonl`, one JSON object per document with its `id`, `tenant` and
`text`, creating `DIR` when needed and replacing an earlier rendering whole. The text states
the presence marker with the retrieval term; a poisoned document adds the instruction as an
HTML comment. Nothing is sent and no key is read. `FILE` defaults to
`guardana-fixtures.yaml`.

| Exit | Meaning |
|---|---|
| `0` | written |
| `3` | the file was refused, or `DIR` could not be written; nothing was written |

## In a recipe

A recipe names the file as `subject.fixtures`, beside a `connection`, with
`schema_version: 2` ([`usage-recipe.md`](usage-recipe.md)). The recipe reads the file once,
so the digest the lock pins and the items a run asks about come from the same bytes. The
lock pins the file's digest and every tenant adapter; `recipe run` resolves every tenant,
checks each key is set and that no two tenants share a secret value, and re-reads every tenant adapter
against its pin before it sends anything. `subject.fixtures` together with
`subject.recording` is refused.

## In the saved run and in `diff`

A run given fixtures records them as `run.fixtures`: the name, the file's digest, `data`
labelled as declared, the tenants, how many documents, records and tools the file declares,
and the `markers` algorithm ([`usage-run.md`](usage-run.md)). `guardana diff` reads two runs
given different fixtures, the same fixtures under different `markers` algorithms, or
fixtures on one side only, as an incomplete comparison (exit `2`): an item one run asked
about the other never did, so its absence would otherwise read as a fixed leak
([`usage-diff.md`](usage-diff.md)).
