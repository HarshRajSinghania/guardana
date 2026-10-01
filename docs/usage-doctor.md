---
title: "guardana doctor"
nav_order: 120
summary: "`guardana doctor`, `config validate|explain`"
status: stable
---

# `guardana doctor` and `guardana config`

`guardana doctor` helps explain a scan when you need to troubleshoot its behavior. Use these commands to check configuration too.

```bash
guardana doctor
guardana config validate
guardana config explain
```

## `doctor` — what this installation is

```text
✓ guardana-core: 0.34.0
✓ guardana-rules: 0.34.0
✓ guardana-cli: 0.34.0
✓ guardana-report: 0.34.0
✓ plugin trust: builtins (not stated, the default)
✓ rules discovered: 51
✓ evaluators discovered: 10
✓ target schemes: none (installed targets are Python-only)
✓ installed packs: no third-party Guardana entry points are installed; 2 built-in Guardana entry point(s)
✓ profile: default parsed
! budgets: no ceiling set — a probe against a paid endpoint has no upper bound

0 problem(s), 1 thing(s) worth knowing.
```

## What an installed pack would execute

If a pack is installed and you have not set trust, `doctor` lists every Guardana entry point the pack advertises. It also lists the module `--plugins all` would import. It reads installed metadata without importing the module:

```text
! pack acme-guardana-rules 1.2.0: 2 Guardana entry point(s) — 2 refused
    guardana.rules acme → module acme_rules: refused
    guardana.evaluators acme_eval → module acme_rules: refused
! refused packs: with this profile (fail_on_error on), scan and probe exit 2, and monitor alerts every cycle, while these stay refused; to load them, narrowest first: --plugins allowlist --allow-plugin acme-guardana-rules
    or plugins: {mode: allowlist, allow: [acme-guardana-rules]} in guardana.yaml, used with --profile guardana.yaml
    or --plugins all, which loads every installed distribution
```

A refusal is a warning because it reflects a trust choice. An admitted pack that fails to import is a failure. Each failure is shown on the entry point that raised it, whatever other entry points share its name. The list covers only Guardana entry points. A package's dependencies and `.pth` startup hooks run when Python starts, before Guardana decides trust; `doctor` does not claim to cover them. Like other commands, `doctor` accepts `--plugins`, `--allow-plugin` and `--profile`. It warns when a profile's `plugins:` widens trust beyond the built-ins. A pipeline checking untrusted contributions should pass a flag to keep trust on `builtins`.

**It contacts nothing.** A diagnostic that costs money or shows up in somebody's
production logs is one people avoid running, which defeats the purpose.

It answers the questions that are otherwise guessed at:

- **which distributions are installed, and whether they agree.** A stale
  `guardana-rules` beside a current CLI is a different tool than the version
  string suggests, and it is invisible until a rule behaves oddly.
- **which plugins loaded, which were refused, and which failed to import.** A refused
  or failed one is a check that will not run.
- **whether third-party rules are installed.** An admitted pack is code a run imports;
  `doctor` reads a refused pack's metadata without importing it.
- **which settings weaken the gate.** Each is a legitimate choice; making it
  silently is what must not happen.

Exit `3` when something is broken — no rules discovered, a plugin that failed to
load. Warnings alone exit `0`: they are things worth knowing, not faults.

## `config validate` — fail before you pay

Parses the profile and stops. Useful as an early pipeline step: a typo in
`guardana.yaml` should fail in a second rather than after a probe has spent its
budget finding out.

## `config explain` — what is actually in force

```bash
guardana config explain --format json
```

A profile file shows what somebody wrote. The question they actually have is what
is *in force*, and most of a gate is defaults — including the ones nobody typed.
`explain` prints the resolved settings: thresholds, budgets, privacy, safety, plugin
trust (with whether the profile stated it), and
the privacy policy digest that a run manifest also records, so a saved run can be
matched back to the configuration that produced it.

## See also

- [`profiles.md`](profiles.md) — what each setting means
- [`exit-codes.md`](exit-codes.md) — what `3` means here
