"""A safety check for banned patterns people type in.

Python's regular expression engine runs inside one call and cannot be stopped, so one pattern that backtracks forever freezes every request of the
process, not only the one that used it. A pattern is therefore only accepted when it cannot do that:

- every repeat has a bound (`{1,40}`, not `+`, `*` or `{1,}`), and no bound is above MAX_BOUND;
- a repeat never sits inside another repeat, and a repeated part holds no choice (`a|b`), so the cost cannot multiply;
- no back references (`\\1`) and no conditional groups;
- the product of all repeat bounds stays under MAX_COST, so the work for each start position stays small.

The built in patterns pass this check. Anything that fails is refused when it is added, and skipped (and shown) when it is already stored.
"""

from __future__ import annotations

import re
from functools import lru_cache
from re import _constants as C  # noqa: PLC2701 - the standard library parser: the only way to read a pattern without running it
from re import _parser as P  # noqa: PLC2701

MAX_PATTERN_LENGTH = 200
MAX_BOUND = 300  # the largest number a repeat may go up to
MAX_COST = 5000  # the most steps one start position can cost: the product of the bounds of the repeats that follow each other
MAX_MATCHES = 200  # the most flags one pattern may raise in one text

_REPEATS = {C.MAX_REPEAT, C.MIN_REPEAT, C.POSSESSIVE_REPEAT}
_GROUP_REFS = {C.GROUPREF, C.GROUPREF_EXISTS}


class UnsafePattern(ValueError):
    """The message is plain words for the person who typed the pattern."""


def _cost(items, inside_repeat: bool) -> int:
    total = 1
    for op, av in items:
        if op in _REPEATS:
            low, high, sub = av
            if high == C.MAXREPEAT:
                raise UnsafePattern("Give every repeat an upper limit: write {1,40} instead of + or *, and {0,40} instead of *.")
            if high > MAX_BOUND:
                raise UnsafePattern(f"A repeat may go up to {MAX_BOUND} at most.")
            if high > 1 and inside_repeat:
                raise UnsafePattern("A repeat inside another repeat can take far too long. Simplify the pattern.")
            inner = _cost(sub, inside_repeat or high > 1)
            total *= max(high, 1) * inner
        elif op == C.BRANCH:
            if inside_repeat:
                raise UnsafePattern("A choice (a|b) inside a repeat can take far too long. Write the words as separate rules.")
            total *= max((_cost(branch, inside_repeat) for branch in av[1]), default=1)
        elif op == C.SUBPATTERN:
            total *= _cost(av[3], inside_repeat)
        elif op in (C.ASSERT, C.ASSERT_NOT):
            total *= _cost(av[1], inside_repeat)
        elif op == C.ATOMIC_GROUP:
            total *= _cost(av, inside_repeat)
        elif op in _GROUP_REFS:
            raise UnsafePattern("Back references (\\1) are not allowed.")
        if total > MAX_COST:
            raise UnsafePattern("The pattern is too wide: it could take too long on a long text. Use smaller limits or fewer repeats.")
    return total


@lru_cache(maxsize=512)
def problem(pattern: str) -> str | None:
    """Why a pattern may not be used, in plain words, or None when it is fine."""
    if len(pattern) > MAX_PATTERN_LENGTH:
        return f"Keep patterns under {MAX_PATTERN_LENGTH} characters."
    try:
        tree = P.parse(pattern)
    except re.error as exc:
        return "That pattern is not valid: " + str(exc)[:100]
    try:
        _cost(tree, False)
    except UnsafePattern as exc:
        return str(exc)
    except RecursionError:
        return "The pattern is nested too deeply."
    return None
