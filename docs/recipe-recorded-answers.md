---
title: "Recipe: check a run your application recorded"
nav_order: 14
summary: "grade an execution your application already performed from its trace, offline, and what recorded answers do not cover yet"
status: stable
---

# Recipe: check a run your application recorded

Check an agent run that already happened, recorded as OpenTelemetry GenAI spans or in Guardana's native trace format. This works offline: it calls no model and invokes no tool.

```bash
guardana trace inspect trace.jsonl
guardana analyze-trace trace.jsonl --format json --output run.json
```

1. `trace inspect` shows what evidence the trace records. It also shows which rules cannot run because the trace lacks evidence they need.
2. `analyze-trace` grades the recorded execution and saves the run. If the trace lacks a type of evidence a rule needs, that rule does not run. The output identifies those rules; it never counts them as passed.

This does not grade answers you supply yourself, such as a file of questions and replies from your application. That is a separate roadmap item (F5) and is not available yet. `analyze-trace` grades what a trace records, as described in [`usage-analyze-trace.md`](usage-analyze-trace.md).
