---
title: "Recorded answers and regrading"
nav_order: 86
summary: "grading answers an application already gave — supplied or kept by a probe — through a target that answers from a recording, with the execution's identity kept apart from the grading's, and missing evidence never read as a pass"
status: accepted
---

# Recorded answers and regrading

**Status:** accepted, implemented — ships in the next release · **Written:** 2026-10-01 ·
**Serves:** ROADMAP F5, backlog B07 · **Supersedes:**
[`regrading-stored-exchanges.md`](regrading-stored-exchanges.md)

## The question

A team has answers its application already gave: a file of questions and replies, or the
replies a probe received. It wants to grade them with its rules without calling the
application again, and to grade the same replies again when a rule, an expectation or a
judge changes. Two things must hold: a new grader on old replies is never read as the system
changing, and an answer that is missing, or that redaction changed, is never read as a pass.
The [earlier design](regrading-stored-exchanges.md) answered the second half for kept
exchanges; this one answers both halves with one mechanism.

## Decisions

### 1. One recording format, beside the dataset

A recording (`guardana_recording: 1`, JSONL) holds what answered: a header with `name`,
`version` and a required `verbatim`, and one line per answer naming the rule whose question it
answers. The same format carries answers a team supplies and the exchanges
`probe --keep-exchanges` keeps. The dataset stays the grading side (questions and
expectations, versioned by their author); the recording is the execution side.

Rejected: an `answer` on dataset lines, which could then not run live and would let a probe
rewrite the team's dataset; answers inside `run.json`, which gives replies and verdicts one
retention period.

### 2. Replay through a target

`RecordedTarget` is a built-in endpoint target that declares `chat` only and answers each rule
from the recording. Every rule runs unchanged, so suite gates, findings, trials and judge-error
correction behave as in a probe; rules that need a planted canary, tool offers or an MCP server
are skipped for a missing capability, as on any endpoint that lacks it.

Rejected: re-evaluating stored assessments without the rules, which needs stored expectations
and a second code path for every gate and finding.

### 3. Per-rule views, not ambient state

The runner asks a target that implements `RuleScoped` for a view per rule. The recorded
target's view answers only that rule's lines, matched by the digest of the messages the rule
sends (`key`, written by a probe) or by its exact `input`; repeated lines are trials in order.
The built-in endpoint's view keeps that rule's exchanges when keeping is on. Neither depends on
which thread a rule runs in.

### 4. Missing or altered evidence is never a pass

- A rule no line names, and that the recording's origin does not list, is skipped
  `not_recorded` by rule selection, so `plan` and the run agree; it is a coverage gap.
- A recorded rule that asks an unrecorded question or reaches an altered reply is logged on the
  target. A suite records that trial ungraded (`not_recorded` as an error, `reply_altered` as
  inconclusive) and keeps it in its denominator; any other rule ends as an error, even if it
  swallowed the exception.
- Lines of a rule that ran but were never read, and lines naming a rule no loaded rule has, are
  errors.
- `verbatim: false`, a line marked `altered`, and a reply holding a placeholder Guardana's
  redactor writes are altered replies.
- A probe's recording graded at other trials per case than it kept is refused before grading.

### 5. Keeping is opt-in and narrow

`privacy.keep_exchanges` or `probe --keep-exchanges` keeps the built-in endpoint's plain pass,
as each rule sent it, never the system prompt, canary passes or tool offers. Inputs and replies
pass the run's redactor, matched spans only and without the size bound; a secret is removed at
every mode. The key is taken before redaction. A changed reply is marked altered; a changed
input needs no mark, because a regrade re-sends the rule's own input and matches by key.
Keeping refuses `metadata_only`, an MCP server and a pack's target.

### 6. Two identities

The execution is the recording's SHA-256: `target.document` in a graded run, `exchanges.digest`
in the probe that kept it. The grading is `rules[]` and `evaluators[]`, which record each
judge's identity. The `recording` block is what the recording declares, not verified; only
digests link two runs. `source.kind` stays the launcher, and a graded run's target reference is
`recording:<subject>`, so it never shares a fingerprint or a baseline waiver with a live
target.

### 7. Traffic is declared

`grade` sends nothing to the target. Judges are built, metered and bounded as in a probe;
`grade` states where their calls go and how many there can be before the first, and
`plan grade` prices them without making any.

### 8. `diff` never reads a grading change as a system change

A rule graded by another evaluator or judge identity is left out of finding and measurement
comparison, and the comparison is incomplete, as for a changed trial count. Two runs sharing an
execution digest get a note saying so. Agreement statistics between two graders wait for M1.

## The contract M1 builds on

Two assessments are compatible only when their `case_id`, rule digest, dataset identity and
digest, assessor and judge identity, and trials per case are equal. Equal execution digests say
a difference is the grader's; unequal ones that it may be the system's. Every trial that was not
measured carries a status and a `reason` (`not_recorded`, `reply_altered`, `declined`), so a
pairing can tell evidence that was never there from evidence nobody could grade.

## Not done here

- Third-party endpoint targets keeping exchanges: they would need a protocol of their own.
- Keeping tool offers and canary passes, and so regrading agent and canary rules.
- The collector receiving recordings or graded runs: its tenancy and retention were designed for
  findings and measurements.
- Labelling a slice of kept replies for judge-error correction.

## See also

- [`usage-grade.md`](../usage-grade.md) — the command and the recording format
- [`privacy-and-redaction.md`](privacy-and-redaction.md) — the redactor every kept reply passes
- [`assessment-channel.md`](assessment-channel.md) — the assessments a pairing reads
- [`paired-regression-statistics.md`](paired-regression-statistics.md) — what M1 builds on this
