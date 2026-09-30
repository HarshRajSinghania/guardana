# F2: a new user gets a failing result, fixes it, keeps the evidence and edits one check — offline, in ten minutes

Size: L · Started: 2026-09-30 · Owner: the 0.33.0 session · Status: planned, challenged and answered — building lane A

## Goal

ROADMAP "First goal: 1.0", row v0.33 = F2 (backlog B04, B13; B12 decided). A clean install runs an
offline starter that fails, is fixed, passes and saves evidence, with no account, key, model or
collector, under built-in trust only, and shows what an installed pack would execute. The user
edits one check and reruns it. Three short recipes separate a local scan, recorded answers and
the user's real application. Non-goals: F3's Python facade, F5's recorded-answer grading, B12's
data-only distributions (decided, built in the parallel lane), any network path in the starter.

## Decisions taken by the maintainer (2026-09-30)

- **B12 decision 1: B, data-only distributions.** Designed and built in the parallel lane after
  this release; F2's custom check is a local YAML file. The research moves to
  [`docs/design/non-executing-packs.md`](../design/non-executing-packs.md), decision recorded.
- **B12 decision 2: the CLI default becomes `builtins` in 0.33**, breaking, stated in the
  CHANGELOG, with a profile key so a team states its trust once.
- **If B: data-only content loads under `builtins` by default.** Recorded in the design for the
  parallel lane; nothing in 0.33 depends on it.
- **SECURITY.md: first response within 14 days** (shipped separately, before this plan).

## Open questions

- [ ] The starter's CLI name — default taken: `guardana init --starter DIR` (extends a command a
  new user already runs; a new top-level verb would be a contract for one tutorial).
- [ ] Who recruits the five external users and when — the owner, after 0.33.0 ships.

## Context (verified 2026-09-30)

- Every CLI command that discovers declares `--plugins` with the literal default `"all"`
  (20 signatures across `cli/*.py`); `resolve_trust` (`cli/_plugins.py:13`) turns flag values into
  a `PluginTrust`. Core's `PluginTrust()` defaults to `ALL` (`core/plugins.py:43`) and
  `Registry.discover(None)` uses it (`core/registry.py:267`); the example suites, the pack
  templates and `clean_install_check.py` call `Registry.discover()` from Python.
- A refused entry point is a `discovery` load error whose reason names the trust mode, not the
  remedy (`core/registry.py:279-294`). `doctor` reports every load error as FAIL
  (`cli/doctor.py:96-99`).
- The profile has no plugin key; unknown keys are refused (`core/profile/loader.py:16-31`). The
  profile carries no `schema_version`; a profile using the new key fails loudly on 0.32.
- **Trust bypass:** `pack validate` and `pack lock` read manifests through
  `importlib.resources.files(module)` (`core/pack/discover.py:195-205`), which imports the
  module, before they check `registry.load_errors` (`cli/pack.py:103`, `:184`). A pack
  `--plugins builtins` refused still runs its `__init__`.
- YAML rules run only against endpoints (`docs/writing-rules.md` field reference); a rule of
  another kind is neither selected nor skipped by a scan (`core/runner.py:356`). `guardana rule
  test` runs a YAML rule's fixtures offline (`docs/usage-rule-test.md`).
- `guardana init` writes a 6-line `guardana.yaml` (`cli/init.py`). `examples/vulnerable-model/`
  has planted artifacts; `scan` exits 1 on it.
- Recorded answers today: `analyze-trace` grades a recorded execution offline. F5 owns grading
  supplied answers; the recipe says so.

## Decisions (challenged by the reviewer on 2026-09-30; answers folded in)

1. **One CLI default: `builtins`.** Every command that discovers resolves trust in one place,
   `cli/_plugins.py`: the `--plugins`/`--allow-plugin`/`--no-plugins` options are declared once
   there with a `None` sentinel, so "not passed" is distinguishable from a value. Resolution:

   | flags given | profile `plugins:` | result |
   |---|---|---|
   | `--plugins X` (with its `--allow-plugin` list) | any | the flag pair, replacing the profile's pair whole |
   | `--no-plugins` | any | `disabled` (deprecated alias, `scan` and `plan scan` only) |
   | `--plugins X --no-plugins` | any | refused, exit 3 |
   | `--allow-plugin` without `--plugins allowlist` | any | refused, as today |
   | none | set | the profile's pair |
   | none | absent, or `--preset` | `builtins` |

   `pack validate`/`pack lock` included; a pack author allowlists their own distribution.
2. **The profile key is honoured wherever a profile drives discovery.** `plugins: {mode, allow}`
   parses into `Profile.plugins: PluginTrust | None`. `rules`, `taxonomy`, `target inspect`,
   `pack validate` and `pack lock` gain `--profile` (additive), so a team states trust once per
   profile, and `guardana.testing.assert_secure` honours it. Nothing reads `guardana.yaml`
   without `--profile`; the recipes say so. A flag outranks the profile, so a pipeline checking
   untrusted contributions passes `--plugins builtins` as a flag, and `doctor` warns when the
   profile widens trust beyond `builtins`.
3. **Core keeps `ALL` until F3** for an *unstated* trust: `PluginTrust()` and
   `Registry.discover()` are the library, and F3's facade makes trust an argument (one break for
   library users, not two). A *stated* trust is honoured everywhere. The docstring in
   `core/plugins.py` and one sentence in SECURITY.md say exactly this.
4. **Refusals are a structured record, not a sentence to parse.** `Registry.refused` holds
   (group, entry point, distribution as spelled in metadata, module) and is built by the loop that
   decides trust; `plan`, the target locator, `doctor` and the CLI hint read it instead of
   matching `CheckError.reason`. A refusal is still a `discovery` error in the run, so the run
   schema does not move; the reason names the distribution, not a CLI flag.
5. **The hint never depends on the gate.** Whenever an unstated default refused anything, the
   command prints on stderr which distributions were refused and how to admit them:
   `--plugins allowlist --allow-plugin <dist>` first, the profile form second, `--plugins all`
   last. `scan` calls it (it does not today); `plan`'s "set fail_on_error: false" advice is
   removed for refusals. A team with `fail_on_error: false` still sees it; the CHANGELOG names
   that case.
6. **One enumeration.** A core function lists every entry point of the four groups with its
   distribution (from `ep.dist`, normalised per PEP 503 for comparison, printed as spelled),
   version (`ep.dist.version`) and the module `ep.load()` would import, without importing; an
   entry point with no distribution is listed as unknown and refused. `Registry.discover` walks
   the same list, so listed-as-refused equals not-imported. Allowlist and profile names are
   compared normalised. Wording everywhere: "Guardana entry points" — never "nothing third-party
   executed" (dependencies and `.pth` hooks run before any trust decision).
7. **Pack commands never import what trust refused.** They check `load_errors` before reading
   any manifest; the core functions take an optional trust (default `ALL`), filter per entry
   point, and return the refused entry points beside their result rather than a silent subset.
   `pack validate <unreadable manifest>` with a refusal present moves from exit 3 to 2 (pinned).
8. **`doctor`** lists third-party entry points with distribution, version and module, marks
   loaded or refused, and says the consequence: "with this profile (fail_on_error on),
   scan/probe/monitor exit 2 while these stay refused". A refusal is a warning; an import failure
   stays a failure. A test asserts `doctor`'s refused set equals `scan`'s discovery errors.
   `doctor` gains `--allow-plugin`. With nothing third-party installed it says so positively.
9. **The starter** (`guardana init --starter DIR`; excludes the positional path, refuses a
   non-empty DIR with exit 3, never writes `./guardana.yaml`) writes a model directory with one
   planted pickle built from bytes at run time (flagged HIGH or above, harmless if unpickled, and
   nothing under `packages/` that the dogfood scan flags), the safe replacement beside it, one
   local YAML check with an id outside `guardana.*` and finding, clean and inconclusive fixtures,
   and a README. Steps, every one written in the README exactly as the test runs it:
   `scan model --output before.json` (exit 1) → replace the model → `scan model --output
   after.json` (exit 0) → `diff before.json after.json` (the finding resolved) → `doctor` (what
   an installed pack would execute) → `rule test --rules checks 'starter.*'` → edit one keyword
   and its fixture → `rule test` again, with a changed result that proves the edit was read. The
   README says the check runs against an endpoint and that `scan` does not run it; `scan` prints
   one stderr line naming local rules that do not apply to an artifact target. It warns that a
   starter inside a repository fails a CI scan of `.` until fixed or deleted.
10. **The fixed run is checked, not just its exit code:** the replacement was observed as a
    component, `pickle_opcode` ran, nothing was waived, no errors, and the starter's files other
    than the model are byte-identical to what `init` wrote.
11. **F2 is not done when 0.33.0 ships.** The release carries the code, the recipes and the study
    kit; the "Now" row stays, marked study pending, until the sheet holds five consented rows. The
    anonymised sheet is data in the repository and `scripts/first_run_measure.py` generates the
    published measure (and "not measured" until then).
12. **Out of scope, into BACKLOG:** the run manifest does not record the trust in force (run
    schema 12, with `profile_digest`); the profile has no `schema_version`; stating `builtins`
    with a pack co-installed stays indeterminate (a "declined by statement" coverage note);
    `diff` ignores `result.errors` when judging completeness. The recipes say what the run does
    not record.

## Blast radius

- [x] CLI flag default (`--plugins`), new flags (`init --starter`, `--profile` on five commands,
  `doctor --allow-plugin`) → usage pages, index, FEATURES, CHANGELOG breaking note
- [x] the profile (`plugins:`) → `docs/profiles.md`, loader tests, `config explain`
- [x] the extension contract (pack commands' trust) → three isolated example suites and
  `new_pack_check.py` green with `--no-cache`
- [x] scripts: `clean_install_check.py`, `new_pack_check.py`, new `first_run_measure.py` (ops row)
- [x] reader-facing wording → `text-broker`
- [x] a protected contract: CLI flags and exit codes → changed on purpose, both sides

What breaks under the new default and who owns it: `examples/custom_rule` (the `acme-prompts`
scan test and README, lane E), `new-pack`'s printed next steps and the pack template README
(lane B), `new_pack_check.py` (lane E), team CI running `pack lock --check` or scanning with a
pack installed, and images built on ours with a pack added (CHANGELOG). Not affected: the Action
(isolated `uvx`), the shipped images, Python callers of `Registry.discover()`, `baseline update`
(refuses on errors), `monitor` (alerts every cycle), `diff` (coverage lost, exit 1).

## Lanes

| # | lane | files | owner | depends on | verify |
|---|---|---|---|---|---|
| A | core: one enumeration, `Registry.refused`, PEP 503 names, pack discovery under trust, `Profile.plugins`, `assert_secure` | `core/plugins.py`, `core/registry.py`, `core/pack/discover.py`, `core/profile/{model,loader}.py`, `testing/assertion.py`, core tests | coder | — | fake distributions: a module that raises on import is listed and never imported; no-dist entry point refused; two dists naming one module both listed; editable install listed; pack functions return refusals |
| B | CLI: shared options and resolver, every `--plugins` command, `--profile` on five commands, hint, `pack.py` order, `plan`/target locator read `refused`, `scan` stderr line, `config explain`, `new-pack` next steps and template README | `cli/_plugins.py`, `cli/*.py` with `--plugins`, `cli/config.py`, `cli/new_pack.py`, `cli/pack_templates/readme.md.tmpl`, CLI tests | coder | A | Typer app inspection: every command with a `plugins` parameter defaults to the sentinel; the resolution table; hint printed with the gate off |
| C | `doctor` would-execute | `cli/doctor.py`, tests | coder | A, B | doctor's refused set equals scan's discovery errors; nothing imported |
| D | starter | `cli/init.py`, `cli/_starter/`, tests | coder | B | README commands extracted and run as written; decision 10's assertions; the edit changes `rule test`'s result |
| E | gates and examples | `scripts/clean_install_check.py` (starter end to end, and a third-party dist whose `__init__` writes a marker: listed by doctor, marker absent after scan, rules, pack validate, pack lock), `scripts/new_pack_check.py`, `examples/custom_rule/{tests,README.md}`, a docs test that reads the CLI default from the Typer app | main | B, C, D | `clean_install_check.py`, `new_pack_check.py`, example suites `--no-cache` |
| F | docs and recipes | three recipes; README; `docs/index.md`; FEATURES; SECURITY; `profiles.md`; usage pages for scan, baseline, monitor, calibrate, rules, target, plan, taxonomy, doctor, pack, init; `threat-model.md`; `product-status.md`; `install.md`; `extending.md`; `architecture.md`; CHANGELOG | text-broker + main | B–E | docs tests, `build_site.py --check` |
| G | study kit and measure | `docs/maintainers/first-run-study.md`, the sheet, `scripts/first_run_measure.py`, ops row | main + text-broker | — | the script says "not measured" on an empty sheet and refuses a row without consent |
| H | image attestation | `.github/workflows/release.yml`, `SECURITY.md` verify line | main | — | checked on the 0.33.0 release run |
| 8 | decision record | `docs/design/non-executing-packs.md`, `docs/index.md` | main | — | done in `3a0d9368` |

A runs first; B after A; C and D in parallel after B (disjoint files); E and F after; G and H
at any time. None touches `core/target`, `core/runner` or the trace code, so no worktree
isolation is needed.

## External evidence kit (the owner collects it; the session never does)

Instruction for the owner, per session: one participant who has not used Guardana, their own
machine, a clean virtual environment, the published 0.33.0, only the README; the owner watches
and does not help; the clock starts at the first command and stops when the saved run from the
fixed starter exists, or at 30 minutes.

Consent must say, in the participant's language: what is recorded (the timings, whether they
finished, where they got stuck, their own words if they agree), what is not (no screen
recording unless asked, no files from their machine, no telemetry — Guardana sends nothing),
where it is stored and for how long, that it is published only as counts and times without
names, and that they can withdraw before publication. The wording goes through
`scripts/text_model.py` before use.

Measurement sheet (one row per participant; kept outside the repository until consent is
confirmed, then only the anonymised columns are committed):

| column | values |
|---|---|
| `participant` | P1…P5 (no names) |
| `date` | ISO date |
| `os`, `python` | as reported |
| `install_seconds`, `first_failure_seconds`, `fixed_seconds`, `saved_run_seconds`, `edited_check_seconds` | seconds from start, empty when not reached |
| `finished_in_10_min` | yes / no |
| `maintainer_help` | none / hint / took over |
| `stuck_at` | the step, or empty |
| `consent_to_publish` | yes / no |

Until the sheet holds five rows with consent, every report and page says "not measured".

## Done-criteria

- [ ] the full gate green, verdict lines read; the clean-install check runs the starter end to end
- [ ] the documented starter run by hand in an empty directory, its saved run read
- [ ] reviewed (at most three rounds); a false-green hunt over the whole diff, above all "the
  starter passes" (a fix that hides the finding) and "builtins refused nothing" (a refusal that
  never reaches the run)
- [ ] five documentation places answered; CHANGELOG states the default change as breaking
- [ ] the study kit shipped; the measure generated from the sheet ("not measured" until five
  consented rows); the "Now" row stays, marked study pending
- [ ] this file deleted in the shipping commit; leftovers (decision 12) in `BACKLOG.md`

## Handoff

- Done: B12 decided and recorded (`3a0d9368`); this plan; the design challenge, answered in
  "Decisions"; lane 8.
- Next: lane A, then B; G and H alongside.
- How to verify where we are: `ls docs/work/`, this file's lane table.
