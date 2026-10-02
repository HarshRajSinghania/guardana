---
title: "guardana recipe"
nav_order: 88
summary: "`guardana recipe lock|run`: a repository recipe that pins what a team's checks are, refuses a run whose pins moved, and leaves one reviewable directory"
status: beta
---

# `guardana recipe` — the same checks against your application, every time

A recipe is a file in your repository that names the profile your checks come from and what
answers them. `guardana recipe lock` pins what those checks are; `guardana recipe run` refuses
to send anything when a pin moved, runs otherwise, and writes one directory a reviewer opens.

```bash
guardana recipe lock                 # write guardana-recipe.lock.yaml; review and commit it
guardana recipe lock --check         # in CI: fail when a pin moved, without writing
guardana recipe run                  # check the pins, run, write the artifact directory
```

Each command reads `./guardana-recipe.yaml` unless you name another recipe file.

## The recipe

You write the recipe; Guardana never rewrites it.

```yaml
schema_version: 1
name: support-bot
profile: guardana.yaml
subject:
  kind: application
  connection:
    url: http://127.0.0.1:8080
    model: support-bot
    api_key_env: SUPPORT_BOT_KEY
deployment:
  ai_system: support-bot
  environment: ci
output:
  directory: guardana-artifact
  exchanges: false
```

| Key | Required | Meaning |
|---|---|---|
| `schema_version` | yes | `2`, or `1` for a recipe without `subject.fixtures`. A newer version is refused with "upgrade Guardana". |
| `name` | yes | The recipe's name, recorded in the run. |
| `profile` | yes | The `guardana.yaml` the checks come from, beside the recipe. |
| `subject.kind` | with `connection` | What answers: `application` or `model_harness`. No default. With `recording` it may be left out when the recording's header declares `subject_kind`; a run where neither declares one, or the two differ, is refused before anything is graded (exit `3`). |
| `subject.connection` | one of the two | `url`, `model`, and optionally `provider`, `api_key_env`, `adapter`, `system_prompt_file`, with the meanings `guardana probe` gives the same flags. |
| `subject.recording` | one of the two | A recording to grade, as `guardana grade` reads it. Nothing is sent to the application. |
| `subject.fixtures` | no | With `connection` and `schema_version: 2`: the [fixtures file](usage-fixtures.md) declaring the synthetic data the application runs with — its tenants, seeded documents, records and tools. Refused with `recording`, and in a schema-1 recipe. |
| `deployment` | no | `ai_system`, `environment`, `deployment_id`, as the `probe` flags of the same names. |
| `output.directory` | no | The artifact directory, a subdirectory beside the recipe. Default `guardana-artifact`. |
| `output.exchanges` | no | `true` puts the replies the profile keeps into the artifact. Default `false`. |

Unknown keys are refused. Relative paths are read beside the recipe.

**Say what answers.** `application` is the endpoint your users reach, run in CI with your own
fixtures or test doubles behind it. `model_harness` is a model reached without your
application's prompt, tools and data: a result about the model, not about what your users
talk to. Guardana cannot tell the two apart from a URL, so it records what the recipe declares
and shows it in the run, the terminal report, the JUnit suite name, `run inspect` and `diff`.

## The lock

`guardana recipe lock` builds the plan of the recipe's run without sending a request and
without reading a key, and writes `guardana-recipe.lock.yaml` beside the recipe. It pins:

- the recipe (its parsed content, so a comment does not count), the Guardana version and the
  plugin trust in force;
- the profile's digest;
- every selected rule's digest, which for a quality suite covers its dataset, with the
  distribution and version that registered it and its trials per case;
- every evaluator a selected rule grades with: who registered it, its judge identity and the
  calibration in force for it;
- every rule the configuration skips, by reason;
- the adapter file the connection names, as written, and the text of its system-prompt file;
- the fixtures file `subject.fixtures` names, as written, and every tenant adapter it names
  (`fixtures`, `fixtures.tenants.<name>.adapter`).

It never pins a key or the recording: the recording is your application's answer, not your
configuration. A rule or evaluator from a distribution installed in editable mode or from a
direct URL can change its code under one version, so it is listed under `unpinned`.

## Exit codes

| Situation | `recipe lock` | `recipe lock --check` | `recipe run` |
|---|---|---|---|
| written, or every pin holds | `0` | `0` | the run's own code |
| a pin moved | — | `1` | `3`, nothing sent |
| a regression pair of a selected suite no longer holds: a side graded the wrong way or declined, the evaluator raised, or it cannot regrade without sending | `1`, nothing written | `1` | `3`, nothing sent |
| the run could never pass: a check the fixtures demand that the profile does not select, or a recording whose run stopped | `3`, nothing written | `3` | runs, and is `2` |
| something selected is `unpinned` | `2`, written | `2` | runs, and the run records what is unpinned |
| nothing selected, plugin trust refused an installed extension, or a selected check would not grade (a rule file that did not load, an evaluator nobody registered) | `2`, nothing written | `2` | `3` (the lock cannot match) |
| recipe or lock missing, unreadable, or from a newer Guardana | `3` | `3` | `3` |

`--check` never writes, so a first run cannot pass by creating its own lock. `recipe run`
sends nothing until the pins hold; then the run's gate decides its exit code as it does for
`probe` and `grade`. A drifted pin is named by kind, both directions — `rule_changed`,
`rule_added`, `rule_removed`, `judge_changed`, `calibration_changed`, `profile_changed`,
`trust_changed`, `guardana_changed`, `recipe_changed`, `distribution_changed`,
`skip_changed`, `trials_changed`, `subject_file_changed`, `evaluator_added`,
`evaluator_removed`. Review the change, then run `guardana recipe lock` again.

All three commands regrade the regression pairs of every selected suite
([`guardana case add`](usage-case.md)) before they compare anything, sending nothing: each
pair's `observed` must still grade `fail` and its `accepted` `pass` with the rule as it is
now. A pair that no longer holds, or a suite whose evaluator cannot regrade without sending,
is a refusal rather than a drifted pin, because it is broken in the lock and in the
configuration alike; the refusal names each case by its rule and dataset line.

`recipe run` takes no selection, trust, trials or profile flags: those are what the lock pins.

Every rule the lock pins must run to completion. One that the run skips — a recording that
holds no answer for it is the usual cause — that errors or that is never reached is a
`demanded_check` coverage shortfall: the run is `indeterminate` (exit `2`) unless a finding
fails it, whatever the profile's `fail_on_*` switches say.

Before it sends anything, `recipe run` also checks what the lock does not cover: the
subject's key variable and every judge's key variable must be set, and an adapter file read
again to send must still have the digest the lock holds. With fixtures, every tenant's key
variable must be set, no two tenants may send a secret value in common, as a key or in an adapter header, and
every tenant adapter read again must still have its pinned digest; the fixtures file is read
once, so the items a run asks about are the bytes the lock compared. Each refusal exits `3` and is
written into the artifact. When the lock lists unpinned checks, the run says so on stderr,
at the end of `report.txt` and in `guardana run inspect`.

## The artifact

`recipe run` claims `output.directory` before it starts: it writes a `junit.xml` with one
error ("the run did not finish") and a `report.txt` saying so. When the run ends it replaces
the directory whole. An interrupted run leaves the placeholder; a refused run writes the
refusal into the same two files. A CI step that uploads the directory therefore never shows an
earlier run's green.

| File | What it is |
|---|---|
| `run.json` | the saved run, with `run.recipe` (name, recipe and lock digests, kind, source, unpinned) |
| `report.txt` | the terminal report without colour, then the lock comparison |
| `junit.xml` | the JUnit report; its suite is named after the subject kind |
| `guardana-recipe.yaml`, `guardana-recipe.lock.yaml` | the recipe and the lock the run held |
| `run.exchanges.jsonl` | only when the profile keeps exchanges and `output.exchanges` is `true` |
| `guardana-artifact.json` | the files above; it marks the directory as one a run may replace |

An existing directory holding a file that `guardana-artifact.json` does not list is refused, never deleted. A recipe that cannot be read marks as refused the artifact directory it names, or `guardana-artifact` beside it when even that cannot be read, if an earlier run wrote one there; it creates none. A recipe so broken that it no longer names its directory can leave an earlier run in a custom directory, so treat the command's exit code as the verdict, not the directory alone. A
profile that keeps exchanges without `output.exchanges: true` is refused: a CI artifact is a
copy of your application's replies that nobody controls.
