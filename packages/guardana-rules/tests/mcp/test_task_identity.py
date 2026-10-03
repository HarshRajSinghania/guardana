"""What a caller presenting no credential is shown by `tasks/list`, and what the ids give away."""

import json
from collections.abc import Sequence

import pytest
from _offline import refuse_name_lookups  # noqa: F401 — an autouse fixture
from guardana.core.rule import NotOffered, RuleContext
from guardana.core.rule.fixture import FixtureOutcome
from guardana.core.rule.verify import FixtureVerdict, verify_rule
from guardana.core.severity import Severity
from guardana.core.target import McpServerTarget, TaskAnswer, TaskOffer
from guardana.core.target._mcp_http import RawReply
from guardana.core.testing import ScriptedMcpServer
from guardana.rules.mcp import McpTaskIdentityRule
from mcp_fixtures import CREDENTIAL, ROUTABLE, TOOLS, findings, guarded, outcomes, summaries

RULE = McpTaskIdentityRule()
_COUNTING = ["task-1", "task-2", "task-3"]
_RANDOM = [
    "7f3a1c04-1b2d-4e5f-8a9b-0c1d2e3f4a5b",
    "b19e2d55-6c7f-4a01-9d3e-2f8b7c6a5d40",
]
_MODERN = "2026-07-28"
_LEGACY = "2025-11-25"


def _open(**overrides: object) -> ScriptedMcpServer:
    settings: dict[str, object] = {"tools": TOOLS, "session_ids": ["a" * 32]}
    settings.update(overrides)
    return ScriptedMcpServer(ROUTABLE, **settings)  # type: ignore[arg-type]


def _target(server: ScriptedMcpServer, credential: str | None = None) -> McpServerTarget:
    return McpServerTarget(
        server.url, credential=credential, sender=server, discovery_sender=server
    )


def _everything_said(reported: Sequence[object]) -> str:
    return json.dumps([repr(finding) for finding in reported])


def test_an_open_server_listing_counting_ids_to_anyone_is_two_highs() -> None:
    reported = findings(RULE, _open(tasks=_COUNTING, task_declaration="listing"))

    assert [f.severity for f in reported] == [Severity.HIGH, Severity.HIGH]
    assert outcomes(reported) == [None, None]
    assert "lists 3 task(s) to a caller who presented no credential" in summaries(reported)[0]
    assert "task ids are a counter" in summaries(reported)[1]
    for task_id in _COUNTING:
        assert task_id not in _everything_said(reported)


def test_random_ids_listed_anonymously_are_one_high_about_the_listing() -> None:
    reported = findings(RULE, _open(tasks=_RANDOM))

    assert [f.severity for f in reported] == [Severity.HIGH]
    assert "lists 2 task(s)" in summaries(reported)[0]


def test_one_listed_id_cannot_show_a_structure() -> None:
    reported = findings(RULE, _open(tasks=["1"]))

    assert len(reported) == 1


def test_a_gated_server_listing_tasks_anonymously_is_one_high_and_says_nothing_of_ids() -> None:
    # Ids on a server with an authorization context need not be random: the context
    # binds the task. Only the listing itself is somebody else's tasks.
    server = guarded(tasks=_COUNTING, tasks_unguarded=True)

    reported = findings(RULE, server, credential=CREDENTIAL)

    assert [f.severity for f in reported] == [Severity.HIGH]
    assert "lists 3 task(s)" in summaries(reported)[0]


def test_an_owner_bound_gated_server_refusing_the_anonymous_listing_is_silent() -> None:
    server = guarded(tasks=_RANDOM, tasks_owner_bound=True, task_declaration="listing")

    assert findings(RULE, server, credential=CREDENTIAL) == []


def test_an_empty_anonymous_listing_on_a_gated_server_is_the_conforming_answer() -> None:
    server = guarded(tasks=_RANDOM, tasks_owner_bound=True, tasks_unguarded=True)

    assert findings(RULE, server, credential=CREDENTIAL) == []


def test_an_empty_anonymous_listing_on_an_open_server_cannot_grade_the_ids() -> None:
    reported = findings(RULE, _open(tasks=[], task_declaration="listing"))

    assert outcomes(reported) == ["inconclusive"]
    assert "cannot be graded" in summaries(reported)[0]


def test_a_server_declaring_no_tasks_and_not_knowing_the_method_does_not_offer_them() -> None:
    with pytest.raises(NotOffered) as raised:
        findings(RULE, _open())

    assert raised.value.missing == ("tasks",)


def test_a_declared_listing_answered_as_an_unknown_method_is_inconclusive() -> None:
    reported = findings(RULE, _open(task_declaration="listing"))

    assert outcomes(reported) == ["inconclusive"]
    assert "declares tasks.list" in summaries(reported)[0]


def test_tasks_declared_without_a_listing_are_inconclusive() -> None:
    reported = findings(RULE, _open(task_declaration="unlisted"))

    assert outcomes(reported) == ["inconclusive"]
    assert "only to a tools/call" in summaries(reported)[0]


def test_the_modern_tasks_extension_is_asked_over_the_modern_wire_and_is_inconclusive() -> None:
    server = _open(protocol_versions=[_MODERN], task_declaration="extension")

    reported = findings(RULE, server)

    assert outcomes(reported) == ["inconclusive"]
    assert "only to a tools/call" in summaries(reported)[0]
    listing = [body for body in server.bodies if body.get("method") == "tasks/list"]
    assert len(listing) == 1
    assert "_meta" in listing[0]["params"]


def test_a_dual_era_server_is_asked_over_the_legacy_wire_in_an_anonymous_session() -> None:
    server = _open(
        protocol_versions=[_MODERN, _LEGACY],
        discovers=[_MODERN],
        tasks=_COUNTING,
        session_ids=["anonymous-session-" + "f" * 20],
    )
    target = _target(server, credential=None)

    reported = list(RULE.run(target, RuleContext()))

    assert len(reported) == 2
    sent = [headers for _, _, headers in server.requests]
    listing = [h for h in sent if h.get("Mcp-Method") is None and "Mcp-Session-Id" in h]
    assert listing, "the listing was not sent inside a handshake-era session"
    assert all("Authorization" not in h for h in listing)
    assert target.authorization().tasks.answer is TaskAnswer.ANSWERED


def test_a_status_that_is_neither_a_listing_nor_a_refusal_is_inconclusive_and_quoted() -> None:
    server = _open(tasks=_COUNTING)

    def throttled(url: str, **kwargs: object) -> RawReply:
        body = kwargs.get("body")
        if isinstance(body, bytes) and b'"tasks/list"' in body:
            return RawReply(status=429, headers={}, body=b"slow down")
        return server(url, **kwargs)  # type: ignore[arg-type]

    target = McpServerTarget(server.url, sender=throttled, discovery_sender=server)

    reported = list(RULE.run(target, RuleContext()))

    assert outcomes(reported) == ["inconclusive"]
    assert "HTTP 429" in summaries(reported)[0]
    assert "slow down" not in summaries(reported)[0]


def test_a_server_sharing_no_revision_is_inconclusive_and_sent_no_listing() -> None:
    server = _open(protocol_versions=["2099-01-01"], tasks=_COUNTING)

    reported = findings(RULE, server)

    assert outcomes(reported) == ["inconclusive"]
    assert not [body for body in server.bodies if body.get("method") == "tasks/list"]


def test_every_listed_task_id_is_withheld_from_what_the_run_writes() -> None:
    target = _target(_open(tasks=_RANDOM))

    list(RULE.run(target, RuleContext()))

    assert set(_RANDOM) <= set(target.sent_secrets())


def test_the_offer_is_read_only_for_an_unknown_method() -> None:
    answered = _target(_open(tasks=[], task_declaration="listing")).authorization().tasks
    unknown = _target(_open(task_declaration="listing")).authorization().tasks

    assert answered.offer is None
    assert unknown.offer is TaskOffer.LISTING


def test_the_rule_classifies_its_own_samples() -> None:
    verified = verify_rule(RULE, RuleContext())

    assert verified.is_proven, verified
    outcomes_seen = {
        result.expected for result in verified.results if result.verdict is FixtureVerdict.PASSED
    }
    assert {
        FixtureOutcome.FINDING,
        FixtureOutcome.CLEAN,
        FixtureOutcome.INCONCLUSIVE,
        FixtureOutcome.NOT_OFFERED,
    } <= outcomes_seen
