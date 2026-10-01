"""The chat exchanges a probe's rules complete, collected to be kept beside the saved run.

Kept exactly as each rule sent them, and redacted only when they are turned into recorded
exchanges, so the key that lets a regrade find an exchange is taken from what the rule
actually sent.
"""

import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace

from guardana.core.recording import (
    RecordedExchange,
    exchange_fits,
    exchange_size,
    messages_key,
)
from guardana.core.redaction import EvidenceRedactor, without_lone_surrogates
from guardana.core.target import ChatMessage
from guardana.core.trace.limits import MAX_RECORD_BYTES, MAX_TRACE_BYTES


@dataclass(frozen=True, slots=True)
class _Kept:
    """One exchange as it happened, before any redaction."""

    rule: str
    messages: tuple[ChatMessage, ...]
    reply: str


class ExchangeKeeper:
    """Collects every chat exchange a rule's view of an endpoint completes, in the order kept.

    Safe to share across threads: rules run concurrently, and every view of one endpoint
    keeps through the same keeper.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kept: list[_Kept] = []

    def keep(self, rule_id: str, messages: Sequence[ChatMessage], reply: str) -> None:
        """Keep one exchange: the messages `rule_id` passed to `chat`, and the reply text."""
        kept = _Kept(rule=rule_id, messages=tuple(messages), reply=reply)
        with self._lock:
            self._kept.append(kept)

    @property
    def count(self) -> int:
        """How many exchanges have been kept so far."""
        with self._lock:
            return len(self._kept)

    def recorded(self, redactor: EvidenceRedactor) -> tuple[RecordedExchange, ...]:
        """Return every kept exchange as a recorded one, inputs and replies redacted by span.

        `key` is taken from the messages as the rule sent them, before redaction. `altered`
        says the reply text is no longer what the target said: a span was redacted or a lone
        surrogate replaced.
        """
        with self._lock:
            kept = tuple(self._kept)
        return _within_a_readable_file(tuple(_recorded(exchange, redactor) for exchange in kept))


_OMITTED = "[omitted: the exchange is over the recording's size ceiling]"
"""What an exchange too long for the recording keeps in place of its text."""

_HEADER_ROOM = MAX_RECORD_BYTES
"""Bytes of the file ceiling left for the header, which names every planned rule."""


def _within_a_readable_file(
    recorded: tuple[RecordedExchange, ...],
) -> tuple[RecordedExchange, ...]:
    """Omit the largest exchanges' text until the recording fits the file ceiling readers apply.

    An omitted exchange keeps its rule and key and is marked altered, so a regrade finds
    the question and never grades it; a sidecar no reader accepts would lose all of them.
    """
    sizes = [exchange_size(exchange) for exchange in recorded]
    excess = sum(sizes) - (MAX_TRACE_BYTES - _HEADER_ROOM)
    if excess <= 0:
        return recorded
    trimmed = list(recorded)
    for index in sorted(range(len(trimmed)), key=lambda i: sizes[i], reverse=True):
        if excess <= 0:
            break
        omitted = _omit(trimmed[index])
        excess -= sizes[index] - exchange_size(omitted)
        trimmed[index] = omitted
    return tuple(trimmed)


def _omit(exchange: RecordedExchange) -> RecordedExchange:
    """Keep an exchange's rule and key, its text omitted and the reply marked altered."""
    return replace(
        exchange,
        input=tuple(replace(message, content=_OMITTED) for message in exchange.input),
        reply=_OMITTED,
        altered=True,
    )


def _recorded(kept: _Kept, redactor: EvidenceRedactor) -> RecordedExchange:
    """Turn one kept exchange into a recorded exchange under `redactor`.

    An exchange no reader would accept on one line is omitted the way an oversize file is.
    """
    reply = redactor.redact_spans(kept.reply)
    recorded = RecordedExchange(
        rule=kept.rule,
        input=tuple(
            replace(message, content=redactor.redact_spans(message.content))
            for message in kept.messages
        ),
        reply=reply,
        key=messages_key(_encodable(kept.messages)),
        altered=reply != kept.reply,
    )
    return recorded if exchange_fits(recorded) else _omit(recorded)


def _encodable(messages: tuple[ChatMessage, ...]) -> tuple[ChatMessage, ...]:
    """Return `messages` with lone surrogates replaced, the only form a digest can encode.

    A scenario quotes earlier replies back to the target, and a reply decoded from JSON can
    hold a lone surrogate; left in, it would make the digest raise and lose every exchange.
    """
    return tuple(
        replace(message, content=without_lone_surrogates(message.content)) for message in messages
    )
