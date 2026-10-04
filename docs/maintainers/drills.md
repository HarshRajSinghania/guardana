---
title: "Drills"
nav_order: 15
summary: "The record of each runbook drill: when it ran, which runbook, which steps were exercised and which were not."
status: stable
---

# Drills

A runbook counts as exercised only for the steps a drill actually ran. Reading the repository
settings with `scripts/check_repo_settings.py` is not a drill. The collector's runbooks are
exercised by the tests [deployment](../deployment.md) names; this page records the drills a
maintainer runs by hand.

Add one row per drill. A step a drill skipped, simulated or ran against something other than
the real service goes under "steps not exercised", with the reason.

| date | runbook | steps exercised | steps not exercised |
|---|---|---|---|

No drill is recorded yet, so the [security runbook](security-runbook.md) has not been exercised.
