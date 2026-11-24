"""A/B experiments with an honest significance note. Two proportions, a two sided z test, a plain verdict. Small samples are called small."""

from __future__ import annotations

import math


def _p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def analyse(a_n: int, a_hits: int, b_n: int, b_hits: int, min_n: int = 100) -> dict:
    if min(a_n, b_n) <= 0 or a_hits > a_n or b_hits > b_n or min(a_hits, b_hits) < 0:
        return {"verdict": "invalid", "note": "Check the numbers: hits cannot exceed views and views must be above zero."}
    pa, pb = a_hits / a_n, b_hits / b_n
    pool = (a_hits + b_hits) / (a_n + b_n)
    se = math.sqrt(pool * (1 - pool) * (1 / a_n + 1 / b_n))
    z = (pb - pa) / se if se else 0.0
    p = _p(z) if se else 1.0
    se_diff = math.sqrt(pa * (1 - pa) / a_n + pb * (1 - pb) / b_n)
    lo, hi = (pb - pa) - 1.96 * se_diff, (pb - pa) + 1.96 * se_diff
    small = min(a_n, b_n) < min_n or min(a_hits, b_hits) < 5
    if small:
        verdict, note = "too_small", f"Too few to call. You need roughly {min_n} views per variant and at least 5 hits in each before a gap means much. Keep it running."
    elif p < 0.05:
        verdict, note = "difference", f"A difference that is unlikely to be chance alone (p {p:.3f}). It is one test: repeat it before you rely on it. It does not say why."
    else:
        verdict, note = "no_difference", f"No clear difference (p {p:.2f}). The data cannot tell the two apart yet."
    return {"a_rate": round(pa * 100, 2), "b_rate": round(pb * 100, 2), "difference_points": round((pb - pa) * 100, 2), "ci_low": round(lo * 100, 2), "ci_high": round(hi * 100, 2), "p": round(p, 4), "verdict": verdict, "note": note}
