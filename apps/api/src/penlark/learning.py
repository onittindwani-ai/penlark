"""Performance import and the learning loop. It describes what the posts that did best have in common. It never says why, and it never says what to do.

For each trait it compares the posts that have the trait with those that do not, on engagement rate, shows both group sizes and a permutation test p value
(fixed seed, so the same data always gives the same answer). A trait with fewer than MIN_GROUP posts in either group is reported as "too few to say", however large the gap looks.
"""

from __future__ import annotations

import csv
import io
import math
import random
import re
import statistics

from penlark.textstats import measure, opener_kind, split_sentences, words

MIN_GROUP = 8
MAX_COUNT = 2_000_000_000  # the largest count the database column holds
MAX_POSTS = 1500  # the newest posts only: the permutation test is the slow part
FIELDS = ("post_ref", "platform", "posted_on", "impressions", "likes", "comments", "shares", "clicks", "text")
ALIASES = {"post_ref": ("post id", "id", "post_id", "url", "permalink"), "platform": ("platform", "network", "channel"), "posted_on": ("date", "published", "posted", "created", "posted_on", "time"), "impressions": ("impressions", "views", "reach", "impr"),
           "likes": ("likes", "reactions", "like_count"), "comments": ("comments", "replies", "comment_count"), "shares": ("shares", "reposts", "retweets"), "clicks": ("clicks", "link clicks", "url clicks"), "text": ("text", "content", "post", "caption", "commentary")}


CSV_CELL_TOO_LONG = "A cell in that file is longer than 128 KB, or the file is not a plain CSV. Check the export, or paste the numbers in smaller pieces."


class ImportError_(ValueError):
    pass


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    low = {h.strip().lower(): h for h in headers}
    out = {}
    for f, names in ALIASES.items():
        for n in names:
            if n in low:
                out[f] = low[n]
                break
    return out


def parse_csv(data: str, mapping: dict[str, str] | None = None) -> tuple[list[dict], list[str]]:
    rd = csv.DictReader(io.StringIO(data))
    try:
        fields = rd.fieldnames
    except csv.Error as exc:
        raise ImportError_(CSV_CELL_TOO_LONG) from exc
    if not fields:
        raise ImportError_("The file has no header row.")
    m = mapping or suggest_mapping(rd.fieldnames)
    missing = [f for f in ("impressions", "text") if f not in m]
    if missing:
        raise ImportError_("Map these columns first: " + ", ".join(missing) + ".")
    rows, problems = [], []
    try:
        yield_rows = list(enumerate(rd, start=2))
    except csv.Error as exc:  # a cell over the reader's limit (128 KB), or a stray NUL
        raise ImportError_(CSV_CELL_TOO_LONG) from exc
    for i, row in yield_rows:
        def num(f: str) -> int:
            v = (row.get(m.get(f, ""), "") or "0").replace(",", "").strip()
            try:
                x = float(v)
            except ValueError:
                raise ValueError(f"row {i}: {f} is not a number") from None
            if not math.isfinite(x):  # "inf", "nan" and "1e999" are text a spreadsheet can hold, but not a count
                raise ValueError(f"row {i}: {f} is not a number")
            if x > MAX_COUNT:
                raise ValueError(f"row {i}: {f} is too large")
            return max(0, int(x))
        try:
            r = {f: num(f) for f in ("impressions", "likes", "comments", "shares", "clicks")}
        except ValueError as exc:
            problems.append(str(exc))
            continue
        txt = (row.get(m["text"]) or "").strip()
        if not txt or r["impressions"] <= 0:
            problems.append(f"row {i}: needs text and impressions above zero")
            continue
        rows.append({**r, "text": txt, "post_ref": (row.get(m.get("post_ref", ""), "") or f"row-{i}")[:200], "platform": (row.get(m.get("platform", ""), "") or "unknown")[:30].lower(), "posted_on": (row.get(m.get("posted_on", ""), "") or "")[:10]})
    return rows, problems


def rate(r: dict) -> float:
    return (r["likes"] + r["comments"] + r["shares"]) / max(1, r["impressions"])


def features(text: str) -> dict[str, bool]:
    m = measure(text)
    ss = split_sentences(text)
    first = ss[0][0] if ss else ""
    return {
        "opens_with_question": opener_kind(first) == "question",
        "number_in_first_line": bool(re.search(r"\d", first)),
        "has_number": m.values["numbers"] > 0,
        "long_post_over_150_words": m.n_words > 150,
        "short_post_under_60_words": m.n_words < 60,
        "one_line_paragraphs": m.values["one_line_paragraphs"] >= 0.5,
        "asks_reader_a_question": "?" in text,
        "uses_emoji": bool(re.search(r"[☀-➿\U0001F300-\U0001FAFF]", text)),
        "uses_you": m.values["you_address"] > 3,
        "contains_link": "http" in text.lower(),
        "mentions_a_client": bool(re.search(r"\b(client|customer)\b", text, re.I)),
    }


def _perm_p(a: list[float], b: list[float], n: int = 2000, seed: int = 7) -> float:
    rng = random.Random(seed)
    obs = abs(statistics.mean(a) - statistics.mean(b))
    pool, k, hits = a + b, len(a), 0
    for _ in range(n):
        rng.shuffle(pool)
        if abs(statistics.mean(pool[:k]) - statistics.mean(pool[k:])) >= obs:
            hits += 1
    return (hits + 1) / (n + 1)


def learn(posts: list[dict]) -> dict:
    """posts: dicts with text, impressions, likes, comments, shares. Returns trait comparisons and plain notes."""
    rated = [(features(p["text"]), rate(p)) for p in posts]
    out = []
    for trait in next(iter(rated))[0] if rated else []:
        a = [r for f, r in rated if f[trait]]
        b = [r for f, r in rated if not f[trait]]
        row = {"trait": trait, "with_n": len(a), "without_n": len(b)}
        if len(a) < MIN_GROUP or len(b) < MIN_GROUP:
            row.update({"status": "too_few", "with_rate": None, "without_rate": None, "lift_percent": None, "p": None, "note": (f"No post has this trait and {len(b)} do not." if len(a) == 0 else f"Only {len(a)} post has this trait and {len(b)} do not." if len(a) == 1 else f"Only {len(a)} posts have this trait and {len(b)} do not.") + f" Fewer than {MIN_GROUP} in either group is too few to say anything."})
        else:
            ma, mb = statistics.mean(a), statistics.mean(b)
            p = _perm_p(a, b, n=2000 if len(a) + len(b) <= 300 else 600)
            lift = (ma - mb) / mb * 100 if mb else 0.0
            row.update({"status": "pending", "with_rate": round(ma * 100, 2), "without_rate": round(mb * 100, 2), "lift_percent": round(lift, 1), "p": round(p, 4),
                        "note": ""})
        out.append(row)
    tested = [r for r in out if r["status"] == "pending"]
    alpha = 0.05 / max(1, len(tested))  # Bonferroni: the more traits are tried, the stricter each test
    for r in tested:
        sig = r["p"] < alpha and abs(r["lift_percent"]) >= 10
        r["status"] = "pattern" if sig else "no_clear_pattern"
        r["note"] = (f"A clear difference in this data: posts with it averaged {r['with_rate']}% against {r['without_rate']}%. This describes past posts. It does not show the trait caused it." if sig else "No difference that stands out from chance in this data.")
    order = {"pattern": 0, "no_clear_pattern": 1, "too_few": 2}
    out.sort(key=lambda r: (order[r["status"]], -abs(r["lift_percent"] or 0)))
    n = len(posts)
    return {"n_posts": n, "traits": out, "tests_run": len(tested), "alpha": round(alpha, 4),
            "warnings": ["With " + str(n) + " posts and several traits tested, one or two can look like patterns by luck. Treat a pattern as a lead to test with an experiment, not a rule." if n < 100 else "Several traits were tested, so one may look like a pattern by luck. Confirm a lead with an experiment."]}
