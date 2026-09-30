import re
from collections.abc import Mapping
from typing import ClassVar

from guardana.core.evaluator._turns import which_turn
from guardana.core.evaluator.base import Evaluator, Expectation, Outcome, Verdict
from guardana.core.exchange import Exchange

# `re` has no match timeout, so the reply length is the only lever on how long an
# author's backtracking pattern can run.
MAX_REPLY_CHARS = 64 * 1024


class RegexEvaluator(Evaluator):
    """Grades a reply by whether `pattern` occurs anywhere in it (`re.search`).

    `must_match` (default true) passes a reply the pattern is found in; false
    passes a reply it is not found in. The pattern must compile, which is checked
    before any reply is read. Confidence 1.0: a match is a fact.

    A reply longer than `MAX_REPLY_CHARS` is inconclusive, never truncated. There
    is no time bound, so nested unbounded quantifiers are the author's to avoid
    (possessive quantifiers or atomic groups, Python 3.11+).

    `must_match: true` describes the answer and reads the final reply. `must_match:
    false` names what must never be said and reads every reply under grade, each
    within the same bound.
    """

    id = "regex"
    deterministic: ClassVar[bool] = True
    judge_calls_per_verdict: ClassVar[int] = 0
    expects: ClassVar[Mapping[str, bool]] = {"pattern": True, "must_match": False}

    @classmethod
    def check_fields(cls, expectation: Expectation) -> str | None:
        """Return why `pattern` or `must_match` is unusable, or None."""
        pattern = expectation.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return f"evaluator {cls.id!r}: 'expect.pattern' must be a non-empty string"
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"evaluator {cls.id!r}: 'expect.pattern' does not compile: {exc}"
        if not isinstance(expectation.get("must_match", True), bool):
            return f"evaluator {cls.id!r}: 'expect.must_match' must be true or false"
        return None

    def evaluate(self, exchange: Exchange, expectation: Expectation) -> Verdict:
        """Pass when finding the pattern is what `must_match` asked for."""
        problem = self.check_fields(expectation)
        if problem is not None:
            return Verdict("inconclusive", 0.0, problem, self.id)
        pattern = str(expectation.get("pattern"))
        if expectation.get("must_match", True) is not True:
            return self._never_said(exchange, pattern)
        reply = exchange.reply_text
        if reply is None:
            return Verdict("inconclusive", 0.0, "No model reply to search.", self.id)
        if len(reply) > MAX_REPLY_CHARS:
            return self._too_long("reply", len(reply))
        found = re.search(pattern, reply) is not None
        said = "found" if found else "not found"
        outcome: Outcome = "pass" if found else "fail"
        return Verdict(outcome, 1.0, f"pattern {said} in the reply (must_match=True).", self.id)

    def _never_said(self, exchange: Exchange, pattern: str) -> Verdict:
        """Fail on the first reply under grade the pattern occurs in; pass only if none."""
        replies = exchange.graded_replies
        too_long: tuple[int, int] | None = None
        for position, text in enumerate(replies, start=1):
            if not text.strip():
                continue
            if len(text) > MAX_REPLY_CHARS:
                too_long = too_long or (position, len(text))
                continue
            if re.search(pattern, text) is not None:
                where = which_turn(position, len(replies), alone="the reply")
                return Verdict(
                    "fail", 1.0, f"pattern found in {where} (must_match=False).", self.id
                )
        if too_long is not None:
            position, length = too_long
            return self._too_long(which_turn(position, len(replies), alone="reply"), length)
        if exchange.reply_text is None:
            return Verdict("inconclusive", 0.0, "No model reply to search.", self.id)
        return Verdict("pass", 1.0, "pattern not found in the reply (must_match=False).", self.id)

    def _too_long(self, what: str, length: int) -> Verdict:
        return Verdict(
            "inconclusive",
            0.0,
            f"{what} is {length} characters, over the {MAX_REPLY_CHARS}-character "
            "bound the pattern is searched within; not graded.",
            self.id,
        )
