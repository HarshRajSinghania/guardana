"""Reading a reply from a server this process started: bounded in size and in time.

The child is the code under test. One that writes a line without end, or never
writes at all, must cost a bounded amount of memory and a bounded wait, and end in
an error the run reports — never a scan that hangs or a reply read whole first.
"""

import sys
import threading

import pytest
from guardana.core.target import McpError
from guardana.core.target._mcp_client import StdioMcpTransport
from guardana.core.target._mcp_http import MAX_RESPONSE_BYTES

_REPLY = '{"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}\\n'
_GRACE_SECONDS = 15


def _child(source: str) -> list[str]:
    return [sys.executable, "-c", source]


def _request_in_background(transport: StdioMcpTransport) -> list[object]:
    """Make one request on a thread, so a read that never returns fails the test instead."""
    outcome: list[object] = []

    def ask() -> None:
        try:
            outcome.append(transport.request("tools/list", {}))
        except McpError as exc:
            outcome.append(exc)

    worker = threading.Thread(target=ask, daemon=True)
    worker.start()
    worker.join(_GRACE_SECONDS)
    assert not worker.is_alive(), "the read is still waiting on the child"
    return outcome


def test_two_replies_written_together_answer_two_requests() -> None:
    transport = StdioMcpTransport(
        _child(
            "import sys, time\n"
            "sys.stdin.readline()\n"
            f"sys.stdout.write('{_REPLY}{_REPLY}')\n"
            "sys.stdout.flush()\n"
            "time.sleep(30)\n"
        )
    )
    try:
        first = transport.request("tools/list", {})
        second = transport.request("tools/list", {})
    finally:
        transport.close()

    assert first == {"tools": []}
    assert second == {"tools": []}


def test_a_line_past_the_cap_is_refused_before_it_ends() -> None:
    transport = StdioMcpTransport(
        _child(
            "import sys, time\n"
            f"sys.stdout.write('x' * {2 * MAX_RESPONSE_BYTES})\n"
            "sys.stdout.flush()\n"
            "time.sleep(60)\n"
        )
    )
    try:
        outcome = _request_in_background(transport)
    finally:
        transport.close()

    assert len(outcome) == 1
    assert isinstance(outcome[0], McpError)
    assert "exceeds" in str(outcome[0])


def test_a_server_that_never_answers_is_an_error_after_the_deadline() -> None:
    transport = StdioMcpTransport(_child("import time\ntime.sleep(60)\n"), timeout=0.5)
    try:
        outcome = _request_in_background(transport)
    finally:
        transport.close()

    assert len(outcome) == 1
    assert isinstance(outcome[0], McpError)
    assert "0.5 seconds" in str(outcome[0])


def test_a_server_that_exits_without_answering_is_an_error() -> None:
    transport = StdioMcpTransport(_child("import sys\nsys.stdin.readline()\n"))
    try:
        with pytest.raises(McpError, match="closed its output"):
            transport.request("tools/list", {})
    finally:
        transport.close()


def test_after_a_failed_read_the_conversation_stays_failed() -> None:
    # The rest of an oversized line, or a late reply, would otherwise be read as
    # the answer to the next request. This child answers only once a second request
    # arrives, so a transport that carried on would read that answer.
    transport = StdioMcpTransport(
        _child(
            "import sys, time\n"
            "sys.stdin.readline()\n"
            "sys.stdin.readline()\n"
            f"sys.stdout.write('{_REPLY}')\n"
            "sys.stdout.flush()\n"
            "time.sleep(30)\n"
        ),
        timeout=0.3,
    )
    try:
        with pytest.raises(McpError, match="within"):
            transport.request("tools/list", {})
        with pytest.raises(McpError, match="within"):
            transport.request("tools/list", {})
    finally:
        transport.close()
