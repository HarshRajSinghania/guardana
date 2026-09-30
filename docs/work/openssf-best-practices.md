# OpenSSF Best Practices Badge: the passing-level answer sheet

Size: S · Started: 2026-09-30 · Owner: the maintainer (registration and sign-off) · Status: waiting for the
project ID on bestpractices.dev

## Goal

Every criterion of the passing level answered with a status, a one-sentence justification and an evidence
URL, ready to paste into the form at `https://www.bestpractices.dev/en/projects/<ID>/passing`. Deleted in
the commit that adds the badge to the README.

## How this sheet was checked

- The criteria: `criteria/criteria.yml` and `config/locales/en.yml` from
  `coreinfrastructure/best-practices-badge` (`main`), fetched 2026-09-30 — 67 active criteria at level 0,
  none `future` or `obsolete`.
- Every status was checked against the tree at `8f921634` (v0.32.0) or the GitHub API on 2026-09-30, not
  from memory. The API answers used:
  - `repos/guardana/guardana`: public, Apache-2.0, issues and discussions on, secret scanning and push
    protection enabled, Dependabot security updates enabled.
  - `repos/guardana/guardana/private-vulnerability-reporting`: `{"enabled": true}`.
  - `repos/guardana/guardana/issues?state=all`: 48 entries, all pull requests (47 Dependabot, 1
    maintainer), no issue.
  - `repos/guardana/guardana/security-advisories`: 0. Dependabot alerts open: 0. Secret-scanning
    alerts: 0.
  - Code scanning: 1 open alert, `py/implicit-string-concatenation-in-list` (a quality note in
    `scripts/tests/test_sitegen_diagram.py`, no security severity). The only two alerts with a security
    severity ever raised, #1 `py/cookie-injection` (medium) and #2 `py/incomplete-url-substring-sanitization`
    (high), were dismissed on 2026-09-09 with written reasons: a false positive behind full key
    authentication, and a test assertion outside any production data flow.
- The evidence URLs are guardana.dev pages (served without `.html`) or files on `main`.

Result: every MUST is Met or has a justified N/A. The Unmet entries are SUGGESTED only:
`dynamic_analysis` and `dynamic_analysis_enable_assertions`.

## Decisions for the maintainer before pasting

- **`report_responses` and `enhancement_responses` are Met vacuously.** The form offers no N/A for them;
  the issue tracker has never received a bug report or an enhancement request, so there is nothing
  unanswered. The justification says exactly that.
- **`dynamic_analysis` is marked Unmet, as instructed.** The criterion's own text also accepts "an
  automated test suite with at least 80% branch coverage", and CI enforces 90% branch coverage
  (`pyproject.toml`, `[tool.coverage]`, `branch = true`, `fail_under = 90`). Under that reading it
  would be Met. It is your call; the sheet does not stretch it.
- **`sites_https` is Met, with one gap.** `https://guardana.dev` sends HSTS (`max-age=31536000;
  includeSubDomains`), but a plain `http://guardana.dev/` request is answered `200` rather than
  redirected. The criterion only urges the redirect. It is a Cloudflare zone setting (SSL/TLS → Edge
  Certificates → Always Use HTTPS), not something in this repository.
- **`know_secure_design` and `know_common_errors` are about a person.** The appendix lists what you
  are attesting to; sign only what you recognise.

## The sheet

URLs below are shortened with two prefixes: `site:` = `https://guardana.dev`, `gh:` =
`https://github.com/guardana/guardana/blob/main`.

### Basics

| # | criterion | level | status | justification | evidence |
|---|---|---|---|---|---|
| 1 | `description_good` | MUST | Met | The home page and README state what Guardana does: it checks AI model and code artifacts, live AI endpoints and MCP servers, and recorded runs, and returns reproducible evidence and a verdict. | https://guardana.dev/ · https://github.com/guardana/guardana#readme |
| 2 | `interact` | MUST | Met | The documentation index explains how to install Guardana, links the contribution guide (issue forms for bugs and features, Discussions for questions) and the security policy. | https://guardana.dev/docs/ · https://guardana.dev/docs/install |
| 3 | `contribution` | MUST | Met | CONTRIBUTING.md describes the process: GitHub pull requests, one commit per PR, conventional-commit titles, and the gates each PR must pass. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#commits-and-pull-requests |
| 4 | `contribution_requirements` | SHOULD | Met | CONTRIBUTING.md states the code standards, the lint and type rules, the test requirements and a pull-request checklist. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#code-standards |
| 5 | `floss_license` | MUST | Met | All five distributions are released under the Apache License 2.0. | https://github.com/guardana/guardana/blob/main/LICENSE |
| 6 | `floss_license_osi` | SUGGESTED | Met | Apache-2.0 is approved by the Open Source Initiative. | https://opensource.org/license/apache-2-0 |
| 7 | `license_location` | MUST | Met | The license is the top-level `LICENSE` file of the repository. | https://github.com/guardana/guardana/blob/main/LICENSE |
| 8 | `documentation_basics` | MUST | Met | The documentation covers installation, a quickstart, one usage page per command, and how to run active checks safely. | https://guardana.dev/docs/ · https://guardana.dev/docs/install · https://guardana.dev/docs/safe-testing |
| 9 | `documentation_interface` | MUST | Met | Every CLI command has a reference page, the exit-status contract and the versioned JSON schemas of every persisted document are published, and the extension API and collector routes are documented. | https://guardana.dev/docs/ · https://guardana.dev/docs/exit-codes · https://guardana.dev/docs/extending · https://github.com/guardana/guardana/tree/main/schemas |
| 10 | `sites_https` | MUST | Met | The website, the repository, PyPI and ghcr.io are all served over HTTPS; guardana.dev sends HSTS. | https://guardana.dev/ · https://github.com/guardana/guardana · https://pypi.org/project/guardana-cli/ |
| 11 | `discussion` | MUST | Met | GitHub Issues, pull requests and Discussions are public, searchable, URL-addressable and need no proprietary client. | https://github.com/guardana/guardana/discussions |
| 12 | `english` | SHOULD | Met | All documentation, code and the issue forms are in English, and reports are accepted in English. | https://guardana.dev/docs/ |
| 13 | `maintained` | MUST | Met | The project ships releases regularly; the latest, 0.32.0, was published on 2026-09-30. | https://github.com/guardana/guardana/releases |

### Change control

| # | criterion | level | status | justification | evidence |
|---|---|---|---|---|---|
| 14 | `repo_public` | MUST | Met | The source is in a public Git repository on GitHub. | https://github.com/guardana/guardana |
| 15 | `repo_track` | MUST | Met | Git records what changed, who changed it and when, for every commit. | https://github.com/guardana/guardana/commits/main |
| 16 | `repo_interim` | MUST | Met | Every commit between releases is public on `main`, not only the release commits. | https://github.com/guardana/guardana/compare/v0.31.0...v0.32.0 |
| 17 | `repo_distributed` | SUGGESTED | Met | The repository uses Git. | https://github.com/guardana/guardana |
| 18 | `version_unique` | MUST | Met | Each release has a unique version number, shared by all five distributions, bumped by a script and published once to PyPI. | https://github.com/guardana/guardana/blob/main/RELEASING.md |
| 19 | `version_semver` | SUGGESTED | Met | Versions follow Semantic Versioning (pre-1.0 `0.MINOR.PATCH`). | https://github.com/guardana/guardana/blob/main/CHANGELOG.md |
| 20 | `version_tags` | SUGGESTED | Met | Every release is an annotated `vX.Y.Z` Git tag. | https://github.com/guardana/guardana/tags |
| 21 | `release_notes` | MUST | Met | CHANGELOG.md gives a human-readable summary of every release, and each GitHub Release carries that section. | https://github.com/guardana/guardana/blob/main/CHANGELOG.md · https://github.com/guardana/guardana/releases |
| 22 | `release_notes_vulns` | MUST | N/A | No publicly known vulnerability (CVE or advisory) has ever affected Guardana's own code, so no release has had one to list. | https://github.com/guardana/guardana/security/advisories |

### Reporting

| # | criterion | level | status | justification | evidence |
|---|---|---|---|---|---|
| 23 | `report_process` | MUST | Met | Bugs are reported through GitHub Issues, with bug-report and feature-request forms. | https://github.com/guardana/guardana/issues/new/choose |
| 24 | `report_tracker` | SHOULD | Met | GitHub Issues tracks individual issues. | https://github.com/guardana/guardana/issues |
| 25 | `report_responses` | MUST | Met | No bug report has been submitted in the last 2–12 months (the tracker has received none), so none is unacknowledged. | https://github.com/guardana/guardana/issues?q=is%3Aissue |
| 26 | `enhancement_responses` | SHOULD | Met | No enhancement request has been submitted in the last 2–12 months (the tracker has received none), so none is unanswered. | https://github.com/guardana/guardana/issues?q=is%3Aissue |
| 27 | `report_archive` | MUST | Met | Issues, pull requests and Discussions are a public, searchable archive. | https://github.com/guardana/guardana/issues?q= |
| 28 | `vulnerability_report_process` | MUST | Met | SECURITY.md publishes the process, and the documentation index links it. | https://github.com/guardana/guardana/blob/main/SECURITY.md · https://guardana.dev/docs/ |
| 29 | `vulnerability_report_private` | MUST | Met | Private vulnerability reporting is enabled, and SECURITY.md directs reporters to a private GitHub Security Advisory submitted over HTTPS. | https://github.com/guardana/guardana/blob/main/SECURITY.md#reporting-a-vulnerability · https://github.com/guardana/guardana/security/advisories/new |
| 30 | `vulnerability_report_response` | MUST | N/A | No vulnerability report has been received in the last 6 months; SECURITY.md commits to a first response within 14 days. | https://github.com/guardana/guardana/blob/main/SECURITY.md |

### Quality

| # | criterion | level | status | justification | evidence |
|---|---|---|---|---|---|
| 31 | `build` | MUST | Met | Each distribution builds from source with `uv build` (hatchling backend); the release workflow rebuilds all five from the tagged commit. | https://github.com/guardana/guardana/blob/main/.github/workflows/release.yml |
| 32 | `build_common_tools` | SUGGESTED | Met | The build uses standard Python packaging tools: uv and hatchling. | https://github.com/guardana/guardana/blob/main/pyproject.toml |
| 33 | `build_floss_tools` | SHOULD | Met | Every build tool (CPython, uv, hatchling) is FLOSS. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#setup |
| 34 | `test` | MUST | Met | The pytest suite is in the repository under Apache-2.0; CONTRIBUTING.md documents how to run it, and CI runs it on every push. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#tooling-gates · https://github.com/guardana/guardana/blob/main/.github/workflows/ci.yml |
| 35 | `test_invocation` | SHOULD | Met | The suite runs with the standard `uv run pytest`. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#tooling-gates |
| 36 | `test_most` | SUGGESTED | Met | CI fails below 90% branch coverage across the codebase and enforces higher floors on critical paths. | https://github.com/guardana/guardana/blob/main/pyproject.toml · https://github.com/guardana/guardana/blob/main/scripts/critical_coverage.py |
| 37 | `test_continuous_integration` | SUGGESTED | Met | GitHub Actions runs the full suite on every push and pull request. | https://github.com/guardana/guardana/actions/workflows/ci.yml |
| 38 | `test_policy` | MUST | Met | CONTRIBUTING.md requires a positive and a negative fixture for every new rule and tests for every new evaluator or target; untested code fails the coverage gate. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#code-standards |
| 39 | `tests_are_added` | MUST | Met | Recent feature commits carry their tests, e.g. the release preset and the fact-or-lead rule classification in 0.32.0. | https://github.com/guardana/guardana/commit/ef3cfb14 · https://github.com/guardana/guardana/commit/31378787 |
| 40 | `tests_documented_added` | SUGGESTED | Met | The test requirement is in CONTRIBUTING.md and in the pull-request template's checklist. | https://github.com/guardana/guardana/blob/main/.github/PULL_REQUEST_TEMPLATE.md |
| 41 | `warnings` | MUST | Met | ruff (about 30 rule families, including the bandit-derived `S` rules) and `mypy --strict` run in pre-commit and CI. | https://github.com/guardana/guardana/blob/main/CONTRIBUTING.md#the-lint-ruleset |
| 42 | `warnings_fixed` | MUST | Met | CI fails on any ruff or mypy finding, so no warning is outstanding on `main`. | https://github.com/guardana/guardana/actions/workflows/ci.yml |
| 43 | `warnings_strict` | SUGGESTED | Met | mypy runs in strict mode over the whole repository, tests included, and ruff enables a broad rule set. | https://github.com/guardana/guardana/blob/main/pyproject.toml |

### Security

| # | criterion | level | status | justification | evidence |
|---|---|---|---|---|---|
| 44 | `know_secure_design` | MUST | Met | The lead maintainer applies secure-design principles throughout the project (fail-safe defaults, complete mediation, least privilege, separation of privilege, open design); see the security contracts and threat model. | https://guardana.dev/docs/threat-model · https://guardana.dev/docs/design/security-contracts |
| 45 | `know_common_errors` | MUST | Met | The lead maintainer knows the common vulnerability classes for this kind of software (unsafe deserialization, command injection, path traversal, injection, broken authentication and authorization, secret leakage, fail-open checks) and their mitigations, which are applied in the code. | https://guardana.dev/docs/threat-model |
| 46 | `crypto_published` | MUST | Met | Guardana uses only published, reviewed primitives: SHA-256, HMAC constant-time comparison, the OS CSPRNG, and TLS from Python's `ssl` module. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 47 | `crypto_call` | SHOULD | Met | Guardana implements no cryptography of its own; it calls Python's `hashlib`, `hmac`, `secrets` and `ssl`. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 48 | `crypto_floss` | MUST | Met | Every cryptographic function comes from CPython's standard library and OpenSSL, both FLOSS. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 49 | `crypto_keylength` | MUST | Met | Collector API keys carry 256 random bits and are hashed with SHA-256; TLS parameters come from the platform OpenSSL, where weaker ones can be disabled. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 50 | `crypto_working` | MUST | Met | No security mechanism uses a broken algorithm; the only hash is SHA-256. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 51 | `crypto_weaknesses` | SHOULD | Met | No SHA-1, and no CBC or other weak mode, is used by any security mechanism. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 52 | `crypto_pfs` | SHOULD | N/A | Guardana implements no key-agreement protocol: outbound TLS is negotiated by Python's `ssl` module, and the collector expects TLS to be terminated by the operator's proxy. | https://guardana.dev/docs/deployment |
| 53 | `crypto_password_storage` | MUST | N/A | Guardana stores no user passwords: the collector authenticates with 256-bit random API keys, kept only as SHA-256 digests. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 54 | `crypto_random` | MUST | Met | Keys and canary tokens are generated with Python's `secrets` module (the OS CSPRNG); `random` is never used for them. | https://github.com/guardana/guardana/blob/main/packages/guardana-server/src/guardana/server/auth.py |
| 55 | `delivery_mitm` | MUST | Met | Releases are published to PyPI over HTTPS by OIDC trusted publishing with PEP 740 and Sigstore build-provenance attestations; container images go to ghcr.io over HTTPS with provenance and SBOM attestations. | https://github.com/guardana/guardana/blob/main/SECURITY.md#what-a-release-publishes-and-how-to-check-it-yourself |
| 56 | `delivery_unsigned` | MUST | Met | No install path fetches a hash over HTTP; installation goes through pip or uv from PyPI over HTTPS, and verification uses signed attestations. | https://guardana.dev/docs/install |
| 57 | `vulnerabilities_fixed_60_days` | MUST | Met | There is no known unpatched vulnerability: no advisory, no open Dependabot alert, and CI audits the dependencies on every push. | https://github.com/guardana/guardana/blob/main/SECURITY.md#how-we-hold-ourselves-to-this |
| 58 | `vulnerabilities_critical_fixed` | SHOULD | Met | No critical vulnerability has been reported; Dependabot security updates are enabled and folded into each release. | https://github.com/guardana/guardana/blob/main/.github/dependabot.yml |
| 59 | `no_leaked_credentials` | MUST | Met | Secret scanning with push protection is enabled and has no alerts, a pre-commit hook refuses private keys, and test fixtures are built in code. | https://github.com/guardana/guardana/blob/main/SECURITY.md#how-we-hold-ourselves-to-this |

### Analysis

| # | criterion | level | status | justification | evidence |
|---|---|---|---|---|---|
| 60 | `static_analysis` | MUST | Met | CodeQL (`security-and-quality` queries) runs on every push and pull request to `main` and weekly; ruff with the bandit-derived `S` rules and `mypy --strict` gate every change. | https://github.com/guardana/guardana/blob/main/.github/workflows/codeql.yml |
| 61 | `static_analysis_common_vulnerabilities` | SUGGESTED | Met | CodeQL's security queries do taint tracking for common Python vulnerabilities, and ruff's `S` family covers the bandit checks. | https://github.com/guardana/guardana/blob/main/.github/workflows/codeql.yml |
| 62 | `static_analysis_fixed` | MUST | Met | No medium-or-higher alert is open; the two security alerts ever raised were triaged and dismissed with written reasons (a false positive and a test-only assertion). | https://github.com/guardana/guardana/blob/main/.github/workflows/codeql.yml |
| 63 | `static_analysis_often` | SUGGESTED | Met | Static analysis runs on every push and pull request, and CodeQL also weekly. | https://github.com/guardana/guardana/actions/workflows/codeql.yml |
| 64 | `dynamic_analysis` | SUGGESTED | Unmet | No fuzzer or other dynamic analysis tool is applied before a release. | — |
| 65 | `dynamic_analysis_unsafe` | SUGGESTED | N/A | Guardana is written entirely in Python, a memory-safe language. | https://github.com/guardana/guardana |
| 66 | `dynamic_analysis_enable_assertions` | SUGGESTED | Unmet | There is no assertion-heavy configuration for dynamic analysis; production code raises explicit exceptions instead of using `assert`. | — |
| 67 | `dynamic_analysis_fixed` | MUST | N/A | No dynamic analysis tool is run, so it has found no vulnerabilities. | — |

## Appendix: what `know_secure_design` and `know_common_errors` attest to

Both criteria are about a person: a primary developer who knows these principles and error
classes and one way to counter each. What follows is where the project applies them, so the
attestation rests on something checkable. Gaps are listed beside the mitigation, not hidden;
knowing a class and its mitigation is what the criterion asks, and the gaps are in
`BACKLOG.md` ("Found while preparing the OpenSSF badge").

### Secure design (Saltzer and Schroeder, as the criterion lists them)

| principle | where Guardana applies it |
|---|---|
| economy of mechanism | one rule engine runs in every place a verdict is produced (`docs/architecture.md`); the site has no JavaScript and a closed CSP (`site/_headers`) |
| fail-safe defaults | a check that cannot run is `inconclusive` or a finding, never a pass (`core/gate.py`, `docs/exit-codes.md`); the collector refuses to serve without a key store unless two switches are set (`server/security.py:35`); from 0.33 plugin trust defaults to `builtins` |
| complete mediation | every collector route that carries a finding goes through one `guard` dependency (`server/security.py:87`); every storage query is scoped to the key's project (`server/tenancy.py:77`) |
| open design | the engine, rules and threat model are public; keys, not obscurity, protect the collector (`docs/threat-model.md`) |
| separation of privilege | read and ingest are separate key scopes; the dashboard cookie authenticates reads only (`server/security.py:97`) |
| least privilege | GitHub workflows default to `contents: read` with job-scoped writes (`.github/workflows/*.yml`); a key can be pinned to one environment (`docs/usage-collector.md`) |
| least common mechanism | tenants share no query path without a scope (`server/tenancy.py`) |
| psychological acceptability | safe defaults with one flag to widen them (`--plugins`, `--allow-exec`, `--allow-side-effects`, `docs/safe-testing.md`) |
| limited attack surface, input validation | YAML through `safe_load` only; submissions validated and rejected with `422`; bounded readers and request bodies |

### Common error classes for this kind of software, and their mitigations

| class | mitigation | anchor | known gap |
|---|---|---|---|
| unsafe deserialization of scanned models | pickles are parsed statically with `pickletools.genops` and never unpickled | `rules/supply_chain/pickle_opcode.py:200`, `docs/threat-model.md:55` | only `.pkl/.pickle/.pt/.ckpt/.joblib/.dill` are opcode-scanned |
| code execution through YAML | every YAML load is `yaml.safe_load` | `core/rule/yaml_rule.py:215`, `core/profile/loader.py:278`, `core/pack/load.py:50` | — |
| executing untrusted plugin code | trust is decided per distribution before `ep.load()`; a refusal is a recorded error | `core/registry.py:279`, `core/plugins.py:47` | `pack validate`/`pack lock` import refused packs to read manifests (fix planned in 0.33) |
| OS command injection | the stdio MCP target runs an argv list, never a shell, and only with `--allow-exec`; no `shell=True` or `os.system` in the source | `core/target/_mcp_client.py:230`, `cli/_mcp_run.py:131` | — |
| path traversal and archive extraction | nothing is extracted to disk; zip members are read in memory; symlinked directories are not followed; devices and FIFOs are refused | `core/target/artifact.py:186`, `rules/supply_chain/_reading.py:28` | a symlinked file is read (bounded) |
| resource exhaustion from hostile inputs | reader caps (16 MiB scan, 512 MiB pickle, 64 MiB zip member), format limits, 30 s HTTP timeout and response caps | `rules/supply_chain/_reading.py:14`, `core/formats/limits.py:19`, `core/target/endpoint.py:16` | stdio MCP `readline()` uncapped; zip member count uncapped |
| SQL injection | psycopg placeholders everywhere; identifiers only from constants or an allowlist | `server/auth.py:198`, `server/postgres_store.py:350` | — |
| missing authentication or authorization, cross-tenant access | scoped API keys on every finding route; the tenant comes from the key; unscoped queries are refused | `server/security.py:87`, `server/tenancy.py:77` | — |
| credential storage and timing | 256-bit keys from `secrets`, stored as SHA-256, compared with `hmac.compare_digest` | `server/auth.py:113-125`, `:203` | an unknown key prefix returns before hashing |
| CSRF | the dashboard cookie is `HttpOnly`, `SameSite=Strict` and read-only; ingest accepts a bearer header only | `server/app.py:386`, `server/security.py:97` | `Secure` only when the app sees `https` |
| cross-site scripting | the dashboard escapes every submitted string before inserting it | `server/dashboard.py:179` | no CSP on the collector; no crafted-payload test |
| request flooding | body-size ceiling (`413`) and per-caller rate limit (`429`) | `server/app.py:316`, `server/limits.py:72` | the limiter is per process |
| secret leakage into reports | one redactor at every renderer and the HTTP reporter; turning it off is refused at load | `core/redaction.py:233`, `report/__init__.py:60` | pattern-based; `--write-trace` writes unredacted |
| fail-open verdicts (this domain's defining error) | stopped, unmeasured or declined runs are `indeterminate` (exit `2`); rule exceptions are errors | `core/gate.py:98`, `docs/exit-codes.md` | skips and inconclusive checks pass unless the profile or `--preset release` says otherwise |
| unintended egress | no telemetry; traffic only to the target, a configured judge or an opt-in reporter; MCP discovery refuses private and link-local hosts from a public target | `core/target/_mcp_http.py:101`, `:254` | redirects are followed without that guard by the endpoint client |
| TLS | no `verify=False` or custom context; the standard library's certificate checks apply | `core/target/endpoint.py:231` | plain `http://` targets are accepted by design |
| prompt injection against an LLM judge | an unparseable judge reply is a low-confidence fail, never a pass | `core/evaluator/llm_judge.py:199` | the transcript is not fenced in the judge prompt |
| terminal escape injection | — | `report/human.py:37` | not mitigated: model output is printed verbatim |
| supply chain of the project itself | actions pinned by SHA, least-privilege workflow permissions, trusted publishing, signed provenance for distributions, secret scanning with push protection | `.github/workflows/release.yml:29`, `:71` | image attestations unsigned (fix planned in 0.33); base images pinned by tag |

Paths are relative to `packages/guardana-*/src/guardana/`, except `docs/`, `site/` and `.github/`.

## Handoff

- Done: the sheet, verified on 2026-09-30.
- Next: the maintainer registers the project, sends the ID, fills the form from this sheet; once the badge
  reads "passing", the README gets it next to the CI badge, CHANGELOG gets an entry, and this file is
  deleted in that commit.
