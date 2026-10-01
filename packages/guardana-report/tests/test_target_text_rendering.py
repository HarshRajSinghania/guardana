"""Text a target controls reaches every output as inert data, never as markup or a command.

A model reply, a trace attribute or a file name becomes a finding's evidence, title or
reference verbatim. In a terminal its escape sequences can erase the warning above them;
in JUnit a NUL makes the whole document unparseable, so the CI test view shows nothing.
"""

from xml.etree.ElementTree import fromstring

import pytest
from guardana.core.evaluator.base import Verdict
from guardana.core.report import CheckError, Evidence, Finding, ScanResult
from guardana.core.severity import Severity
from guardana.report import JUnitRenderer, get_renderer

_HOSTILE = "reply\x1b[2J\x1b[H\x07\x00\x9b31m\x7f\rFAKE\nline"
"""Clear screen, cursor home, bell, NUL, a C1 CSI, DEL, a carriage return and a newline."""


def _finding(text: str) -> Finding:
    return Finding(
        f"acme.{text}", Severity.HIGH, f"title {text}", (), f"ref {text}", Evidence(text)
    )


def _result(text: str) -> ScanResult:
    unverified = Finding(
        "acme.u",
        Severity.LOW,
        f"u {text}",
        (),
        text,
        Evidence(text),
        Verdict("inconclusive", 0.0, text, "guard"),
    )
    error = CheckError(source=f"acme.e{text}", stage="run", reason=text)
    return ScanResult((_finding(text),), ("acme.r",), (), unverified=(unverified,), errors=(error,))


def _control_characters(text: str) -> list[str]:
    return [c for c in text if c != "\n" and (ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F)]


def test_the_terminal_report_carries_no_control_character_from_the_target() -> None:
    rendered = get_renderer("human").render(_result(_HOSTILE))

    assert _control_characters(rendered) == []
    assert "\\x1b[2J" in rendered, "the sequence is shown escaped, not dropped"


def test_a_newline_from_the_target_cannot_forge_a_report_line() -> None:
    rendered = get_renderer("human").render(_result(_HOSTILE))

    assert not any(line.startswith("line") for line in rendered.splitlines())
    assert "\\nline" in rendered


def test_the_terminal_report_keeps_its_own_layout() -> None:
    rendered = get_renderer("human").render(_result("plain"))

    assert "\n    plain  (ref plain)\n" in rendered


def test_the_junit_document_stays_well_formed_over_xml_illegal_characters() -> None:
    document = fromstring(get_renderer("junit").render(_result(_HOSTILE)))  # noqa: S314 — our own output

    failure = document.find("testcase/failure")
    assert failure is not None
    assert failure.text is not None
    assert failure.text.startswith("reply")
    assert "\x00" not in failure.text


@pytest.mark.parametrize("character", ["\x00", "\x08", "\x1b", "\ufffe", "\ud800"])
def test_every_xml_illegal_character_is_replaced_in_junit(character: str) -> None:
    # The renderer itself, so a lone surrogate reaches it rather than the redactor first.
    rendered = JUnitRenderer().render(_result(f"a{character}b"))

    document = fromstring(rendered.encode("utf-8"))  # noqa: S314 — our own output
    assert document.find("testcase/failure") is not None
    assert character not in rendered


def test_junit_keeps_the_whitespace_xml_allows() -> None:
    document = fromstring(get_renderer("junit").render(_result("a\tb\nc")))  # noqa: S314 — our own output

    failure = document.find("testcase/failure")
    assert failure is not None
    assert failure.text == "a\tb\nc"
