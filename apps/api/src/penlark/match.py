"""Voice match score. Pure code, deterministic, no model, no network.

For each dimension the text is compared with the profile: the distance in tolerance units (z) becomes a 0 to 100 dimension score,
exp(-0.5 * (z / 1.4)^2), so z = 1 is about 77, z = 2 about 36 and z = 3 about 11. The overall match is the weighted average.
A text under 25 words is scored but marked low confidence, because style numbers on a few words are noise.
"""

from __future__ import annotations

import math
import time

from penlark import dimensions as D
from penlark.fingerprint import _tv, _vec_dist
from penlark.textstats import split_sentences, measure

MIN_WORDS = 25


def _s(z: float) -> float:
    return 100.0 * math.exp(-0.5 * (z / 1.4) ** 2)


def score_measured(m, profile: dict) -> tuple[float, list[dict]]:
    rows, tot, wsum = [], 0.0, 0.0
    for k, (lab, _mean, *_r) in D.SCALAR.items():
        p = profile["dims"][k]
        z = (m.values[k] - p["centre"]) / p["tolerance"]
        sc = _s(z)
        rows.append({"key": k, "label": lab, "score": round(sc, 1), "value": round(m.values[k], 3), "centre": p["centre"], "z": round(z, 2), "direction": "low" if z < 0 else "high", "weight": p["weight"]})
        tot += sc * p["weight"]
        wsum += p["weight"]
    for k, dist in (("word_habits", _vec_dist(m.habits, profile["habits_centre"])), ("openers", _tv(m.openers, profile["openers_centre"]))):
        c = profile["vector_calibration"][k]
        z = max(0.0, dist - c["d0"]) / c["tolerance"]
        sc = _s(z)
        rows.append({"key": k, "label": D.label(k), "score": round(sc, 1), "value": round(dist, 4), "centre": c["d0"], "z": round(z, 2), "direction": "high", "weight": c["weight"]})
        tot += sc * c["weight"]
        wsum += c["weight"]
    return tot / wsum, rows


def advice(row: dict) -> str | None:
    if row["score"] >= 70:
        return None
    k = row["key"]
    if k in D.SCALAR:
        return D.SCALAR[k][6] if row["direction"] == "low" else D.SCALAR[k][7]
    return D.VECTOR[k][3]


def match(text: str, profile: dict, with_sentences: bool = True) -> dict:
    t0 = time.perf_counter()
    m = measure(text)
    if m.n_words == 0:
        return {"score": 0, "confidence": "none", "dimensions": [], "weakest": [], "pull_down": [], "n_words": 0, "ms": 0.0, "note": "Write or paste some text to see a match."}
    overall, rows = score_measured(m, profile)
    for r in rows:
        r["advice"] = advice(r)
    pull: list[dict] = []
    sents = split_sentences(text)
    if with_sentences and 2 <= len(sents) <= 80:
        for s, start in sents:
            rest = text[:start] + text[start + len(s):]
            if len(rest.split()) < 6:
                continue
            o2, _ = score_measured(measure(rest), profile)
            if o2 - overall >= 0.8:
                pull.append({"start": start, "end": start + len(s), "text": s, "delta": round(o2 - overall, 1)})
        pull.sort(key=lambda x: -x["delta"])
        pull = pull[:8]
    weakest = sorted(rows, key=lambda r: r["score"])[:3]
    return {"score": round(overall), "score_exact": round(overall, 2), "confidence": "ok" if m.n_words >= MIN_WORDS else "low", "dimensions": rows, "weakest": [{"key": r["key"], "label": r["label"], "score": r["score"], "advice": r["advice"]} for r in weakest if r["advice"]],
            "pull_down": pull, "n_words": m.n_words, "ms": round((time.perf_counter() - t0) * 1000, 2),
            "note": "" if m.n_words >= MIN_WORDS else "Under 25 words: the number is rough."}


def raw_score(text: str, profile: dict) -> float:
    return score_measured(measure(text), profile)[0]
