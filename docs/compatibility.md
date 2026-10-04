---
title: "Compatibility"
nav_order: 57
summary: "what Guardana keeps compatible from 1.0 — the Python facade, the extension, output and kit contracts, the command line, the exit codes and every persisted document — how a name is deprecated before it goes, and where the generated surface and matrix live"
status: beta
---

# Compatibility — what stays put, and how a change is announced

This page states what an upgrade keeps working. The surface it covers is listed in full,
generated from source, in [`api-surface.json`](generated/api-surface.json); which document and
API versions each release writes is in the [compatibility matrix](generated/compatibility-matrix.md).

## The supported surface

| Surface | What is covered |
|---|---|
| Python facade | `guardana.core.verify.__all__` and `guardana.core.doubles.__all__` ([Python API](python-api.md)) |
| Extension contract | `guardana.core.__all__` except `Runner`, `guardana.core.target.protocols.__all__`, `guardana.core.target.WireProtocol`, `PythonSource` and `UnreadSource` from `guardana.core.source` (the types a `FileReader` returns), `CoverageShortfall` and `ShortfallKind` from `guardana.core.report.shortfall` (how a rule records what it could not cover), and from `guardana.core.rule.fixture`: `RuleFixture`, `DeclaredFixture`, `FixtureOutcome`, `DEMANDED_OUTCOMES`, `materialise` ([extending](extending.md)) |
| Output contract | `guardana.core.output.__all__` ([installed outputs](outputs.md)) |
| Conformance kit | `guardana.testing.__all__` and `guardana.core.testing.__all__` ([conformance kit](conformance-kit.md)) |
| Versions | the six entry-point groups, `EXTENSION_API_VERSION`, `SUPPORTED_EXTENSION_API_VERSIONS`, `OUTPUT_API_VERSION`, `SUPPORTED_OUTPUT_API_VERSIONS`, and the version of every persisted document |
| Command line | every command, its options and arguments, whether each is required, a flag, repeatable, hidden or defaulted |
| Exit codes | every `ExitCode` member and its value ([exit codes](exit-codes.md)) |
| Locators | the reserved target schemes, the target scheme and output name grammar, the reserved format and reporter names, `server://` |
| GitHub Action | every `action.yml` input, whether it is required and whether it has a default |
| Environment | the name of every `GUARDANA_*` variable Guardana reads |

For each Python name the snapshot records its kind, the module that defines it, its
parameters (name, kind, whether it has a default, and the annotation as written in source) and
return annotation, a class's public methods and fields, and an enum's members. Help text is not
part of the surface. The trace format is versioned by its own [JSON schema](usage-analyze-trace.md)
and is not repeated in the snapshot.

Everything else is internal and may change in any release: `Runner`, the registry's load
state, `guardana.cli.*`, and every module or name that starts with `_`.

## The policy

From 1.0:

- The supported surface changes incompatibly only in a major release.
- A name to be removed is deprecated first, for at least one minor release, and removed only in
  the next major. Deprecation means a `DeprecationWarning` where Python can raise one, and a
  "Deprecated" entry in the [changelog](../CHANGELOG.md) that names the replacement.
- Every 1.x release reads every document an earlier release wrote, and writes the current
  version. One exception: `load_verification` refuses a schema-1 run, which recorded no gate;
  `load_report` and `guardana run migrate` read it.
- Every 1.x release supports extension API 2 and output API 1. A new API version is opt-in
  through the range a pack's manifest declares, and support for an API version is dropped only
  in a major release.
- A Python version is supported until its upstream end of life. Dropping one is announced one
  minor release ahead.

Until 1.0, a breaking change can land in a minor release and is announced under
"Changed — breaking" in the changelog, with what to write instead.

## The collector envelope

A run reaches the collector as a versioned envelope. Every change to the envelope raises its
version. A collector accepts every envelope version from 2 up to its own. An agent newer than
its collector is refused with `422`, and the response names the versions the collector accepts,
so upgrade the collector before the agents that report to it. Dropping an envelope version is a
major release.

## How a change is caught

`scripts/api_surface.py` writes `api-surface.json` from source, and the documentation check
fails when the committed file no longer matches. A release candidate whose surface differs from
the previous release's is refused unless the changelog's unreleased section has a "Changed",
"Deprecated" or "Removed" section.
