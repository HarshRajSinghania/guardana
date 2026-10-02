---
title: "Recipe: probe your real application"
nav_order: 15
summary: "probe the endpoint your application exposes, with its own prompt, tools and data, bounded by a budget, ending with a saved run"
status: stable
---

# Recipe: probe your real application

Probe the system your users talk to. A model server without your application's system prompt, tools or data tests the model, not the application. Point the probe at the endpoint your application exposes.

```bash
guardana plan probe --url https://staging.example.com --model my-app --max-requests 50
guardana target inspect --url https://staging.example.com --model my-app
guardana probe --url https://staging.example.com --model my-app --max-requests 50 --format json --output run.json
```

1. `plan probe` estimates the cost and lists what would run without sending a request.
2. `target inspect` asks the endpoint what it can do. If a rule needs a capability the endpoint lacks, the rule is visibly skipped instead of counted as passed.
3. `probe` sends at most `--max-requests` requests and saves the run. The saved run records the plugin trust in force (`run.configuration.plugins`). If your endpoint uses its own request and response format, map it with `--adapter` ([guarded endpoints](usage-probe.md#probing-a-guarded-endpoint)).

Probe staging, not production. Your application can act on the model's output, and real probe requests can cost money. Read [safe testing](safe-testing.md) first. Run your own checks, such as the starter's `checks/`, with `--rules checks`.

This does not check the files you ship ([local scan](recipe-local-scan.md)) or runs that already happened ([recorded runs](recipe-recorded-answers.md)).
