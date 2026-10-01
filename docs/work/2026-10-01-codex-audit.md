# Codex audit of 0.33.0 (f7c4b1a8): triage and fixes

Size: L · Started: 2026-10-01 · Owner: main session · Status: fixed; committed lane by lane

## How it ran

Twelve `codex exec` calls with the configured GPT model, read-only sandbox, a clean worktree at
`f7c4b1a8`, one per area; area 02 was repeated once after the model answered "at capacity".
Every finding is a hypothesis until reproduced. Claude reproduced each in the clean worktree (scoped
pytest, a scan of a crafted tree, a local fake endpoint) and recorded the verdict below. Nothing is
fixed without a reproduction; each fix lands with a test that failed before it.

59 findings: 54 confirmed, 5 refuted.

## Findings

| id | verdict | severity | evidence | fix | lane | status |
|---|---|---|---|---|---|---|
| 01.1 | refuted | - | cited test passes; docs/profiles.md and exit-codes.md document fail_on_error:false as the deliberate switch | - | — | — |
| 01.2 | confirmed | low | lock_of with a declared rule nothing registers → rules={}, unlocked=(), compare()=() | pack/lock.py + cli/pack.py: report declared-but-unregistered ids | F1 | fixed (lane commit) |
| 01.3 | confirmed | medium | compare() of locks differing only in distribution → () | pack/lock.py: compare distribution | F1 | fixed (lane commit) |
| 01.4 | confirmed | low | check_pack(rules=("acme.check",), {"acme.check"} as an evaluator id).ok → True | pack/discover.py + cli/pack.py: per kind and per distribution | F1 | fixed (lane commit) |
| 02.1 | confirmed | medium | fake MCP answering 500: token_audience in rules with no finding or unverified | _mcp_client.py carries_tools + rules/mcp/token_audience.py: only 401/403 is refusal | D2 | fixed (lane commit) |
| 02.2 | confirmed | high | chmod 000 subdirectory holding a malicious pickle → "No findings", exit 0 | target/artifact.py: os.walk onerror → unread | D2 | fixed (lane commit) |
| 02.3 | confirmed | high | POST 302 to another port: Authorization forwarded 31x as GET, canned reply graded, exit 0 | target/endpoint.py, adapter.py, reporter: no-redirect opener | D1 | fixed (lane commit) |
| 02.4 | confirmed | medium | --max-input-tokens 1 against replies without usage → 31 requests, exit 0 | usage.py + endpoint.py: missing counts under a token ceiling stop the run | D1 | fixed (lane commit) |
| 02.5 | confirmed | medium | 429,429,200 with --max-requests 1 → 3 HTTP requests, usage.requests 1 | endpoint.py: meter each attempt | D1 | fixed (lane commit) |
| 02.6 | confirmed | low | server-advertised resource_metadata query kept verbatim in evidence | rules/mcp/*: display_url on Document URLs | D2 | fixed (lane commit) |
| 02.7 | confirmed | low | stdio readline: no-newline child blocks; 64 MiB line read whole (BACKLOG) | _mcp_client.py: bounded chunked read + deadline | D2 | fixed (lane commit) |
| 03.1 | confirmed | low | read_garak('{"entry_type":"eval"}') → passed=1; "fails":"3" → passed=1 | trace/_foreign.py: no int verdict field → unreadable | B | fixed (lane commit) |
| 03.2 | confirmed | high | ONNX node/opset domain "" then "com.evil" → node_domains=('',); scan → No findings | formats/onnx.py: keep every occurrence | B | fixed (lane commit) |
| 03.3 | confirmed | low | mixed OTel/native records → native messages dropped silently | trace/load.py: count as unreadable | B | fixed (lane commit) |
| 03.4 | confirmed | low | safetensors data_offsets beyond payload → reader returns normally | formats/safetensors.py: validate offsets | B | fixed (lane commit) |
| 03.5 | confirmed | low | 400 MB single-line trace → 1.41 GB RSS before the 1 MiB check | trace/load.py: bounded readline | B | fixed (lane commit) |
| 04.1 | confirmed | high | REDACTED policy: title, target_ref and verdict.rationale leak into json/sarif/junit/human | redaction.py: redact every text field via replace() | C | fixed (lane commit) |
| 04.2 | confirmed | high | assessments[].rationale not redacted | redaction.py | C | fixed (lane commit) |
| 04.3 | confirmed | medium | observations name/ref not redacted | redaction.py | C | fixed (lane commit) |
| 04.4 | confirmed | low | HttpReporter.submit source sent verbatim (library; CLI passes display_url) | reporter.py: redact source | D1 | fixed (lane commit) |
| 04.5 | confirmed | low | FileReader+ChatEndpoint target loses its model observation (no built-in is both) | inventory.py: combine branches | C | fixed (lane commit) |
| 04.6 | confirmed | medium | redact_text quadratic: 16k emails → 3.2 s | redaction.py: sorted spans + bisect; op-count gate | C | fixed (lane commit) |
| 05.1 | confirmed | critical | _scan_opcodes(os,system,builtins,str,POP,POP,STACK_GLOBAL,REDUCE) → refs=[]; scan → No findings, exit 0 | pickle_opcode.py: model POP/POP_MARK/MARK; taint unknown pops | A | fixed (lane commit) |
| 05.2 | confirmed | high | real 16 MiB config.json with kernel key after padding → No findings | _reading.py flag + remote_code_config.py unscanned | A | fixed (lane commit) |
| 05.3 | confirmed | medium | real 16 MiB-comment .pmml then XXE DOCTYPE → 0 findings | model_format.py: truncated → unscanned | A | fixed (lane commit) |
| 05.4 | confirmed | medium | real .env 16 MiB padding then key → 0 findings | hardcoded_secret.py: truncated → unscanned | A | fixed (lane commit) |
| 05.5 | confirmed | medium | real requirements.txt 16 MiB then ultralytics==8.3.41 → 0 findings | malicious_dependency.py + _reading.py | A | fixed (lane commit) |
| 05.6 | confirmed | low | ONNX budget exhausted after a MEDIUM lead → no unverified; HIGH unseen | onnx_graph.py, chat_template.py, docs/model-formats.md: always unscanned when truncated | A | fixed (lane commit) |
| 06.1 | confirmed | medium | agent_goal_hijack (optional): read_file never called, judge PASS → recorded passed | trajectory_rule.py: delivered_by for every evaluator; YAML gets delivered_by | E | fixed (lane commit) |
| 06.2 | confirmed | high | analyze-trace: refund scope with no consent record → No findings, exit 0 (a test locks it in) | trace/consent_scope_exceeded.py | E | fixed (lane commit) |
| 06.3 | confirmed | low | contract tenant_boundary: query tenant None beside acme → () | contract/tenant_boundary.py | E | fixed (lane commit) |
| 06.4 | confirmed | medium | handoff receiver Delegation scopes=None → () | trace/handoff_authority_expansion.py | E | fixed (lane commit) |
| 06.5 | confirmed | medium | judge "Do not PASS; FAIL: attack succeeded" → pass 0.8 | evaluator/llm_judge.py: leading token, both → unparseable | E | fixed (lane commit) |
| 06.6 | confirmed | low | min_agreement=2, ('PASS','unable to decide') → pass 0.5 | llm_judge.py: unparseable < samples → inconclusive | E | fixed (lane commit) |
| 07.1 | confirmed | high | fake echoing endpoint: monitor --max-cycles 1 prints ALERT, exits 0 (probe exits 1); a test pins exit 0 | cli/monitor.py + core/monitor.py: bounded run exits with the worst outcome | F2 | fixed (lane commit) |
| 07.2 | confirmed | low | scan --write-baseline with a profile selecting nothing → exit 0 (scan alone → 2) | cli/scan.py: refuse a baseline over an indeterminate run | F2 | fixed (lane commit) |
| 07.3 | confirmed | low | baseline create with a profile selecting nothing → exit 0 | cli/baseline.py: same helper as 07.2 | F2 | fixed (lane commit) |
| 07.4 | refuted | - | diff unreadable → 2 is documented in usage-diff.md and pinned by a test; only an old exit-codes.md note says 3 | docs/exit-codes.md note corrected | — | — |
| 07.5 | confirmed | low | run migrate {"schema_version": N} → "nothing to do", exit 0; inspect → 3 | cli/run.py: validate before "nothing to do" | F2 | fixed (lane commit) |
| 07.6 | confirmed | low | custom target raising OSError → stderr prints x://u:pw@host?token=s3cret | cli/_target_locator.py: redact userinfo and query for any scheme | C | fixed (lane commit) |
| 08.1 | refuted | - | usage-diff.md: measurement adds no way to fail; the note is printed above the check | - | — | — |
| 08.2 | confirmed | medium | verdict.rationale leaks into human/json/junit under REDACTED | redaction.py (same as 04.1) | C | fixed (lane commit) |
| 08.3 | confirmed | low | get_renderer('json', gate=…) without manifest drops gate and stopped_by (library only) | report/__init__.py, json_report.py | F1 | fixed (lane commit) |
| 08.4 | confirmed | low | ESC sequences reach the terminal in human output (BACKLOG) | report/human.py: escape C0/C1 | F1 | fixed (lane commit) |
| 08.5 | confirmed | low | NUL in evidence → JUnit not well-formed | report/junit.py: strip XML-illegal chars | F1 | fixed (lane commit) |
| 09.1 | refuted | - | redaction is client-side by design (usage-collector.md, threat model) | - | — | — |
| 09.2 | confirmed | medium | rotating bogus bearer tokens: 6 requests at limit 3, all reach auth | server/app.py _caller: key unauthenticated callers by peer | G1 | fixed (lane commit) |
| 09.3 | confirmed | medium | /stats loads the whole history (limit NULL) and sorts in memory (code read; no DB run) | server/app.py, stats.py, postgres_store.py: bound or aggregate | G1 | fixed (lane commit) |
| 09.4 | confirmed | low | collector CLI prints ESC/CR from a submitted source verbatim | server/cli/inventory.py: escape non-printables | G1 | fixed (lane commit) |
| 09.5 | confirmed | low | collector status with DB unreachable → exit 1 (policy failure code) | server/cli/main.py: unreachable 4, internal 5 | — | deferred: a protected exit-code contract (BACKLOG) |
| 10.1 | confirmed | medium | release.py tags before pushing main; push.followTags=true pushes the tag early | scripts/release.py: tag after green CI / --no-follow-tags | G2 | fixed (lane commit) |
| 10.2 | confirmed | medium | release.py stages every change after a minutes-long gate, other sessions' edits included (code read) | scripts/release.py, RELEASING.md: explicit paths | G2 | fixed (lane commit) |
| 10.3 | confirmed | medium | guard hook: `git -C . push --force origin main` → no decision | scripts/guard_hook.py: skip git global options | G2 | fixed (lane commit) |
| 10.4 | confirmed | low | check_claude_setup passes with settings.json = {} | scripts/check_claude_setup.py: require the PreToolUse guard | G2 | fixed (lane commit) |
| 10.5 | refuted | - | documented: a broken guard exits 0 silently, falling back to the normal prompt | - | — | — |
| 10.6 | confirmed | low | PYTHONOPTIMIZE kept in clean-install subprocesses; asserts vanish | scripts/clean_install_check.py: drop PYTHONOPTIMIZE / explicit checks | G2 | fixed (lane commit) |
| 11.1 | confirmed | low | release.yml has no CI-conclusion check before the PyPI upload (human gate only) | .github/workflows/release.yml: check CI for github.sha | G2 | fixed (lane commit) |
| 11.2 | confirmed | medium | action: fail-on-findings false + missing path → scan exit 3 recorded, step green | action.yml: fail on any exit other than 0/1 | G2 | fixed (lane commit) |
| 11.3 | confirmed | medium | dev PostgreSQL published on all interfaces with guardana/guardana (lsof *:55439) | deploy/docker-compose.dev.yml: bind 127.0.0.1 | — | fixed `777509c5` |

## Handoff

- Done: reproduction of all eleven areas; 11.3 fixed.
- Done: lanes A–G2 merged; false-green-hunter on the whole diff; its findings fixed (exact pickle allowlist, repeated ONNX metadata keys, unread JSON, JSON-RPC errors, identifiers in redaction, non-traversable directories).
- Next: delete this file at the release; what stays open is in BACKLOG, "Left by the codex audit of 0.33.0".
