"""Posting rhythm: how many posts a week each platform should have, and how many are planned.

The target comes from the CADENCE setting, for example `linkedin:2,x:2` (two posts a week on LinkedIn and two on X). It is a plan and a nudge on the
calendar, never a rule that blocks anything. Weeks run Monday to Sunday. A planned, exported or sent item counts; a failed one does not.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta

PLATFORMS = ("linkedin", "x", "instagram", "facebook", "threads", "youtube", "newsletter", "email")
COUNTED = {"planned", "exported", "sent"}
MAX_PER_WEEK = 21


def parse(spec: str) -> dict[str, int]:
    """`linkedin:2,x:2` becomes {"linkedin": 2, "x": 2}. An empty text means no target. Anything else wrong raises ValueError."""
    out: dict[str, int] = {}
    for part in (p.strip() for p in (spec or "").split(",")):
        if not part:
            continue
        name, sep, num = part.partition(":")
        name = name.strip().lower()
        if not sep or name not in PLATFORMS:
            raise ValueError(f"CADENCE entry '{part}' must look like linkedin:2 with a platform from {', '.join(PLATFORMS)}.")
        if name in out:
            raise ValueError(f"CADENCE names {name} twice.")
        try:
            n = int(num.strip())
        except ValueError as exc:
            raise ValueError(f"CADENCE count for {name} must be a whole number.") from exc
        if not 0 <= n <= MAX_PER_WEEK:
            raise ValueError(f"CADENCE count for {name} must be from 0 to {MAX_PER_WEEK}.")
        out[name] = n
    return out


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def status(rows: Iterable[tuple[str, str, str]], today: date, targets: dict[str, int], weeks: int = 4) -> list[dict]:
    """For each of `weeks` weeks from this one: per platform, the planned count against the target. `rows` are (platform, run_on, status)."""
    counts: dict[tuple[date, str], int] = {}
    for platform, run_on, st in rows:
        if st not in COUNTED:
            continue
        try:
            d = datetime.strptime(run_on, "%Y-%m-%d").date()
        except ValueError:
            continue
        key = (week_start(d), platform)
        counts[key] = counts.get(key, 0) + 1
    first = week_start(today)
    out = []
    for i in range(max(1, min(weeks, 12))):
        start = first + timedelta(days=7 * i)
        per = {p: {"planned": counts.get((start, p), 0), "target": t, "gap": max(0, t - counts.get((start, p), 0))} for p, t in targets.items()}
        out.append({"week_start": start.isoformat(), "week_end": (start + timedelta(days=6)).isoformat(), "platforms": per, "on_track": all(v["gap"] == 0 for v in per.values())})
    return out
